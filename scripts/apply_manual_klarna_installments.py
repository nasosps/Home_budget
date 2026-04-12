#!/usr/bin/env python
"""
Apply the 2026-04-12 manual Klarna installment additions into Supabase.

This is intentionally idempotent so the same four rows can be inserted on a
clean environment or normalized if they were entered manually before.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from migrate_firebase_to_supabase import ensure_legacy_card_accounts
from sync_to_supabase import (
    SupabaseRestClient,
    append_local_log,
    env_value,
    eq,
    fetch_owner_profile,
    load_dotenv,
    utc_now,
)


DEFAULT_OWNER_EMAIL = "nasosps@outlook.com"
DEFAULT_SCHEMA = "public"
DEFAULT_LOG_PATH = ".local/migrations/manual-klarna-installments.jsonl"

TARGET_PLANS = [
    {
        "title": "Skroutz - Klarna (60\u20ac)",
        "title_aliases": ["Skroutz - VISA 2008 (60 EUR)", "Skroutz - VISA 2008 (60\u20ac)"],
        "note_aliases": [
            "manual_autopay:visa_2008;merchant=skroutz;display_total=60;due1=2026-04-08;due2=2026-05-08;due3=2026-06-07",
        ],
        "notes": "klarna_skroutz",
        "start_date": "2026-03-01",
        "total_amount": 60.00,
        "total_months": 3,
        "monthly_payment": 20.00,
    },
    {
        "title": "Skroutz - Klarna (52\u20ac)",
        "title_aliases": ["Skroutz - VISA 2008 (52 EUR)", "Skroutz - VISA 2008 (52\u20ac)"],
        "note_aliases": [
            "manual_autopay:visa_2008;merchant=skroutz;display_total=52;due1=2026-04-10;due2=2026-05-10;due3=2026-06-09",
        ],
        "notes": "klarna_skroutz",
        "start_date": "2026-03-01",
        "total_amount": 52.23,
        "total_months": 3,
        "monthly_payment": 17.41,
    },
    {
        "title": "TEMU.COM - Klarna (37\u20ac)",
        "title_aliases": ["TEMU.COM - VISA 2008 (37 EUR)", "TEMU.COM - VISA 2008 (37\u20ac)"],
        "note_aliases": [
            "manual_autopay:visa_2008;merchant=temu.com;display_total=37;due1=2026-04-11;due2=2026-05-11;due3=2026-06-10",
        ],
        "notes": "klarna_temu",
        "start_date": "2026-03-01",
        "total_amount": 36.60,
        "total_months": 3,
        "monthly_payment": 12.20,
    },
    {
        "title": "TEMU.COM - Klarna (48\u20ac)",
        "title_aliases": ["TEMU.COM - VISA 2008 (48 EUR)", "TEMU.COM - VISA 2008 (48\u20ac)"],
        "note_aliases": [
            "manual_autopay:visa_2008;merchant=temu.com;display_total=48;due1=2026-04-12;due2=2026-05-12;due3=2026-06-11",
        ],
        "notes": "klarna_temu",
        "start_date": "2026-03-01",
        "total_amount": 48.15,
        "total_months": 3,
        "monthly_payment": 16.05,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply the manual Klarna installment additions into Supabase.")
    parser.add_argument("--owner-email", default=None, help="Owner email in Supabase")
    parser.add_argument("--log-path", default=DEFAULT_LOG_PATH, help="Local JSONL audit log path")
    return parser.parse_args()


def same_money(left: Any, right: Any) -> bool:
    return abs(float(left) - float(right)) < 0.005


def is_matching_row(row: dict[str, Any], plan: dict[str, Any]) -> bool:
    if row.get("title") == plan["title"]:
        return True
    if row.get("title") in plan["title_aliases"]:
        return True
    if row.get("notes") == plan["notes"]:
        return (
            row.get("start_date") == plan["start_date"]
            and same_money(row.get("monthly_payment", 0), plan["monthly_payment"])
            and same_money(row.get("total_amount", 0), plan["total_amount"])
        )
    if row.get("notes") in plan["note_aliases"]:
        return True
    return (
        row.get("start_date") == plan["start_date"]
        and int(row.get("total_months", 0)) == plan["total_months"]
        and same_money(row.get("monthly_payment", 0), plan["monthly_payment"])
        and same_money(row.get("total_amount", 0), plan["total_amount"])
    )


def normalized_payload(user_id: str, alpha_card_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "card_account_id": alpha_card_id,
        "title": plan["title"],
        "total_amount": plan["total_amount"],
        "total_months": plan["total_months"],
        "monthly_payment": plan["monthly_payment"],
        "start_date": plan["start_date"],
        "status": "active",
        "notes": plan["notes"],
    }


def apply_plans(client: SupabaseRestClient, user_id: str, alpha_card_id: str) -> tuple[list[str], list[str]]:
    rows = client.select(
        "installment_plans",
        {"user_id": eq(user_id), "status": eq("active")},
        columns="id,title,total_amount,total_months,monthly_payment,start_date,notes,card_account_id",
    )

    inserted: list[str] = []
    updated: list[str] = []

    for plan in TARGET_PLANS:
        payload = normalized_payload(user_id, alpha_card_id, plan)
        matching_rows = [row for row in rows if is_matching_row(row, plan)]

        if matching_rows:
            for row in matching_rows:
                client.update(
                    "installment_plans",
                    {"id": eq(row["id"]), "user_id": eq(user_id)},
                    {
                        "card_account_id": alpha_card_id,
                        "title": plan["title"],
                        "total_amount": plan["total_amount"],
                        "total_months": plan["total_months"],
                        "monthly_payment": plan["monthly_payment"],
                        "start_date": plan["start_date"],
                        "status": "active",
                        "notes": plan["notes"],
                    },
                    returning=False,
                )
            updated.append(plan["title"])
            continue

        client.insert("installment_plans", payload, returning=False)
        inserted.append(plan["title"])
        rows.append(payload)

    return inserted, updated


def main() -> int:
    args = parse_args()
    env_map = load_dotenv(Path(".env"))
    owner_email = (args.owner_email or env_value(env_map, "HOME_BUDGET_OWNER_EMAIL", DEFAULT_OWNER_EMAIL)).lower()
    schema = env_value(env_map, "SUPABASE_SCHEMA", DEFAULT_SCHEMA)
    supabase_url = env_value(env_map, "SUPABASE_URL", required=True).rstrip("/")
    service_role_key = env_value(env_map, "SUPABASE_SERVICE_ROLE_KEY", required=True)

    client = SupabaseRestClient(supabase_url, service_role_key, schema)
    owner_profile = fetch_owner_profile(client, owner_email)
    user_id = owner_profile["id"]
    card_map = ensure_legacy_card_accounts(client, user_id)
    alpha_card_id = card_map["alpha"]

    inserted, updated = apply_plans(client, user_id, alpha_card_id)

    append_local_log(
        Path(args.log_path),
        {
            "timestamp": utc_now(),
            "kind": "manual_klarna_installments",
            "owner_email": owner_email,
            "inserted": inserted,
            "updated": updated,
            "plan_count": len(TARGET_PLANS),
        },
    )

    print(f"Applied {len(TARGET_PLANS)} manual Klarna plans for {owner_email}.")
    print(f"Inserted: {len(inserted)}")
    print(f"Updated: {len(updated)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
