#!/usr/bin/env python
"""
Import a local manual budget snapshot into Supabase.

The snapshot file is intentionally local-only so private budget values
do not need to live in git.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from migrate_firebase_to_supabase import ensure_legacy_card_accounts
from sync_to_supabase import SupabaseRestClient, append_local_log, env_value, eq, fetch_owner_profile, load_dotenv, utc_now


DEFAULT_SNAPSHOT_PATH = ".local/manual_snapshot.json"
DEFAULT_LOG_PATH = ".local/migrations/manual-snapshot-import.jsonl"
DEFAULT_OWNER_EMAIL = "nasosps@outlook.com"
DEFAULT_SCHEMA = "public"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a local manual budget snapshot into Supabase.")
    parser.add_argument("--input", default=DEFAULT_SNAPSHOT_PATH, help="Path to the local manual snapshot JSON file")
    parser.add_argument("--owner-email", default=None, help="Owner email in Supabase")
    return parser.parse_args()


def load_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Manual snapshot file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def replace_cashflow(client: SupabaseRestClient, user_id: str, items: list[dict[str, Any]]) -> int:
    client.update("cashflow_items", {"user_id": eq(user_id)}, {"is_active": False}, returning=False)
    if not items:
        return 0
    payload = [
        {
            "user_id": user_id,
            "kind": item["kind"],
            "title": item["title"],
            "amount": item["amount"],
            "source": item.get("source", "manual_snapshot"),
            "notes": item.get("notes", ""),
            "is_active": True,
        }
        for item in items
    ]
    client.insert("cashflow_items", payload, returning=False)
    return len(payload)


def replace_car_loan(client: SupabaseRestClient, user_id: str, car_loan: dict[str, Any] | None) -> int:
    client.update("car_loans", {"user_id": eq(user_id)}, {"is_active": False}, returning=False)
    if not car_loan:
        return 0
    client.insert(
        "car_loans",
        {
            "user_id": user_id,
            "label": car_loan["label"],
            "lender": car_loan.get("lender", "Manual Snapshot"),
            "start_date": car_loan["start_date"],
            "total_months": car_loan["total_months"],
            "monthly_payment": car_loan["monthly_payment"],
            "down_payment": car_loan.get("down_payment", 0),
            "balloon": car_loan.get("balloon", 0),
            "is_active": True,
        },
        returning=False,
    )
    return 1


def replace_installments(client: SupabaseRestClient, user_id: str, plans: list[dict[str, Any]]) -> int:
    client.update("installment_plans", {"user_id": eq(user_id), "status": eq("active")}, {"status": "cancelled"}, returning=False)
    if not plans:
        return 0

    card_map = ensure_legacy_card_accounts(client, user_id)
    payload = []
    for plan in plans:
        bank_key = plan["bank_key"]
        payload.append(
            {
                "user_id": user_id,
                "card_account_id": card_map.get(bank_key),
                "title": plan["title"],
                "total_amount": plan["total_amount"],
                "total_months": plan["total_months"],
                "monthly_payment": plan["monthly_payment"],
                "start_date": plan["start_date"],
                "status": "active",
                "notes": plan.get("notes", f"legacy_bank:{bank_key}"),
            }
        )
    client.insert("installment_plans", payload, returning=False)
    return len(payload)


def main() -> int:
    args = parse_args()
    env_map = load_dotenv(Path(".env"))
    owner_email = (args.owner_email or env_value(env_map, "HOME_BUDGET_OWNER_EMAIL", DEFAULT_OWNER_EMAIL)).lower()
    schema = env_value(env_map, "SUPABASE_SCHEMA", DEFAULT_SCHEMA)
    supabase_url = env_value(env_map, "SUPABASE_URL", required=True).rstrip("/")
    service_role_key = env_value(env_map, "SUPABASE_SERVICE_ROLE_KEY", required=True)

    snapshot_path = Path(args.input)
    snapshot = load_snapshot(snapshot_path)
    client = SupabaseRestClient(supabase_url, service_role_key, schema)
    owner_profile = fetch_owner_profile(client, owner_email)
    user_id = owner_profile["id"]

    cashflow_count = replace_cashflow(client, user_id, snapshot.get("cashflow_items", []))
    car_loan_count = replace_car_loan(client, user_id, snapshot.get("car_loan"))
    installments_count = replace_installments(client, user_id, snapshot.get("installment_plans", []))

    log_record = {
        "timestamp": utc_now(),
        "status": "completed",
        "source_snapshot": str(snapshot_path),
        "cashflow_count": cashflow_count,
        "car_loan_count": car_loan_count,
        "installments_count": installments_count,
        "snapshot_source": snapshot.get("source"),
    }
    append_local_log(Path(DEFAULT_LOG_PATH), log_record)
    print("Manual snapshot import completed.")
    print(json.dumps(log_record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
