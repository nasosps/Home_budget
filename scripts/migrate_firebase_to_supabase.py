#!/usr/bin/env python
"""
One-off migration from the old Firebase-backed app into Supabase.

This helps move manual cashflow, car loan and installment data without
typing everything by hand.
"""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sync_to_supabase import (
    SupabaseRestClient,
    append_local_log,
    env_value,
    eq,
    fetch_owner_profile,
    load_dotenv,
    utc_now,
)


FIREBASE_API_KEY = "AIzaSyDV6btFSq5IeQlVq7YihlJOkaKam-MrsJQ"
FIREBASE_PROJECT_ID = "home-budget-gr"
DEFAULT_OWNER_EMAIL = "nasosps@outlook.com"
DEFAULT_SCHEMA = "public"
DEFAULT_LOG_PATH = ".local/migrations/firebase-to-supabase.jsonl"

LEGACY_CARD_PRESETS = {
    "energy": {"label": "Energy Mastercard", "issuer": "Alpha Bank", "last4": "1001"},
    "alpha": {"label": "Alpha Bank MasterCard", "issuer": "Alpha Bank", "last4": "1004"},
    "pancreta": {"label": "Pancreta", "issuer": "Pancreta Bank", "last4": None},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate old Firebase app data into Supabase.")
    parser.add_argument("--email", default=None, help="Firebase account email")
    parser.add_argument("--password", default=None, help="Firebase account password")
    parser.add_argument("--owner-email", default=None, help="Owner email in Supabase")
    parser.add_argument("--keep-existing", action="store_true", help="Do not replace existing Supabase manual rows")
    return parser.parse_args()


def firebase_post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Firebase request failed with {exc.code}: {body}") from exc


def firebase_get_document(path: str, id_token: str) -> dict[str, Any] | None:
    base_url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents"
    request = Request(
        f"{base_url}/{path}",
        headers={"Authorization": f"Bearer {id_token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return None
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Firestore GET {path} failed with {exc.code}: {body}") from exc


def firebase_list_documents(path: str, id_token: str, page_size: int = 1000) -> list[dict[str, Any]]:
    base_url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents"
    query = urlencode({"pageSize": str(page_size)})
    request = Request(
        f"{base_url}/{path}?{query}",
        headers={"Authorization": f"Bearer {id_token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("documents", [])
    except HTTPError as exc:
        if exc.code == 404:
            return []
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Firestore LIST {path} failed with {exc.code}: {body}") from exc


def decode_firestore_value(value: dict[str, Any]) -> Any:
    if "stringValue" in value:
        return value["stringValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "timestampValue" in value:
        return value["timestampValue"]
    if "nullValue" in value:
        return None
    if "arrayValue" in value:
        return [decode_firestore_value(item) for item in value.get("arrayValue", {}).get("values", [])]
    if "mapValue" in value:
        return {
            key: decode_firestore_value(item)
            for key, item in value.get("mapValue", {}).get("fields", {}).items()
        }
    return value


def decode_document(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None
    return {
        key: decode_firestore_value(value)
        for key, value in document.get("fields", {}).items()
    }


def infer_card_key(account: dict[str, Any]) -> str:
    haystack = f"{account.get('label', '')} {account.get('issuer', '')} {account.get('last4', '')}".lower()
    if "energy" in haystack or "1001" in haystack:
        return "energy"
    if "pancreta" in haystack or "pagkr" in haystack:
        return "pancreta"
    return "alpha"


def ensure_legacy_card_accounts(client: SupabaseRestClient, user_id: str) -> dict[str, str]:
    rows = client.select(
        "card_accounts",
        {"user_id": eq(user_id)},
        columns="id,label,last4,issuer,is_active",
    )
    active_rows = [row for row in rows if row.get("is_active", True)]
    card_map: dict[str, str] = {}
    for row in active_rows:
        key = infer_card_key(row)
        if key not in card_map:
            card_map[key] = row["id"]

    missing_payloads = []
    for key, preset in LEGACY_CARD_PRESETS.items():
        if key not in card_map:
            missing_payloads.append(
                {
                    "user_id": user_id,
                    "issuer": preset["issuer"],
                    "label": preset["label"],
                    "last4": preset["last4"],
                    "is_active": True,
                }
            )

    if missing_payloads:
        created = client.insert("card_accounts", missing_payloads, returning=True)
        for row in created:
            key = infer_card_key(row)
            if key not in card_map:
                card_map[key] = row["id"]

    return card_map


def replace_cashflow(client: SupabaseRestClient, user_id: str, budget_list: dict[str, Any], replace_existing: bool) -> int:
    income_rows = budget_list.get("income", []) if isinstance(budget_list, dict) else []
    expense_rows = budget_list.get("expenses", []) if isinstance(budget_list, dict) else []

    payload = []
    for item in income_rows:
        payload.append({"user_id": user_id, "kind": "income", "title": item.get("title", ""), "amount": item.get("amount", 0), "source": "firebase_migration", "notes": "", "is_active": True})
    for item in expense_rows:
        payload.append({"user_id": user_id, "kind": "expense", "title": item.get("title", ""), "amount": item.get("amount", 0), "source": "firebase_migration", "notes": "", "is_active": True})

    if not payload:
        return 0
    if replace_existing:
        client.update("cashflow_items", {"user_id": eq(user_id)}, {"is_active": False}, returning=False)
    client.insert("cashflow_items", payload, returning=False)
    return len(payload)


def replace_car_loan(client: SupabaseRestClient, user_id: str, car_loan: dict[str, Any] | None, replace_existing: bool) -> int:
    if not car_loan:
        return 0
    if replace_existing:
        client.update("car_loans", {"user_id": eq(user_id)}, {"is_active": False}, returning=False)
    client.insert(
        "car_loans",
        {
            "user_id": user_id,
            "label": "Αυτοκίνητο",
            "lender": "Firebase Migration",
            "start_date": car_loan.get("startDate"),
            "total_months": car_loan.get("totalMonths"),
            "monthly_payment": car_loan.get("monthlyPayment"),
            "down_payment": car_loan.get("downPayment", 0) or 0,
            "balloon": car_loan.get("balloon", 0) or 0,
            "is_active": True,
        },
        returning=False,
    )
    return 1


def replace_installments(
    client: SupabaseRestClient,
    user_id: str,
    installment_documents: list[dict[str, Any]],
    replace_existing: bool,
) -> int:
    decoded_rows = [decode_document(document) or {} for document in installment_documents]
    if not decoded_rows:
        return 0

    card_map = ensure_legacy_card_accounts(client, user_id)
    payload = []
    for row in decoded_rows:
        bank_key = row.get("bank", "alpha")
        payload.append(
            {
                "user_id": user_id,
                "card_account_id": card_map.get(bank_key),
                "title": row.get("title", ""),
                "total_amount": row.get("totalAmount", 0),
                "total_months": row.get("totalMonths", 0),
                "monthly_payment": row.get("monthlyPayment", 0),
                "start_date": row.get("startDate"),
                "status": "active",
                "notes": f"legacy_bank:{bank_key}",
            }
        )

    if replace_existing:
        client.update("installment_plans", {"user_id": eq(user_id), "status": eq("active")}, {"status": "cancelled"}, returning=False)
    client.insert("installment_plans", payload, returning=False)
    return len(payload)


def main() -> int:
    args = parse_args()
    env_map = load_dotenv(Path(".env"))
    owner_email = (args.owner_email or env_value(env_map, "HOME_BUDGET_OWNER_EMAIL", DEFAULT_OWNER_EMAIL)).lower()
    login_email = (args.email or owner_email).strip().lower()
    password = args.password or getpass.getpass("Firebase password: ")
    replace_existing = not args.keep_existing

    supabase_url = env_value(env_map, "SUPABASE_URL", required=True).rstrip("/")
    service_role_key = env_value(env_map, "SUPABASE_SERVICE_ROLE_KEY", required=True)
    schema = env_value(env_map, "SUPABASE_SCHEMA", DEFAULT_SCHEMA)

    auth_payload = firebase_post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}",
        {
            "email": login_email,
            "password": password,
            "returnSecureToken": True,
        },
    )

    id_token = auth_payload["idToken"]
    firebase_uid = auth_payload["localId"]

    user_document = decode_document(firebase_get_document(f"users/{firebase_uid}", id_token)) or {}
    car_loan_document = decode_document(firebase_get_document(f"users/{firebase_uid}/car_loan/details", id_token))
    installment_documents = firebase_list_documents(f"users/{firebase_uid}/installments", id_token)

    client = SupabaseRestClient(supabase_url, service_role_key, schema)
    owner_profile = fetch_owner_profile(client, owner_email)
    user_id = owner_profile["id"]

    cashflow_count = replace_cashflow(client, user_id, user_document.get("budgetList", {}), replace_existing)
    car_loan_count = replace_car_loan(client, user_id, car_loan_document, replace_existing)
    installment_count = replace_installments(client, user_id, installment_documents, replace_existing)

    summary = {
        "timestamp": utc_now(),
        "status": "completed",
        "firebase_uid": firebase_uid,
        "supabase_user_id": user_id,
        "replace_existing": replace_existing,
        "cashflow_items": cashflow_count,
        "car_loans": car_loan_count,
        "installment_plans": installment_count,
    }
    append_local_log(Path(DEFAULT_LOG_PATH), summary)

    print("Firebase migration completed.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
