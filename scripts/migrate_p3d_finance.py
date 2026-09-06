from __future__ import annotations

import argparse
import json
import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import mysql.connector


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT.parents[2] / "VSCODE" / "P3D.GR" / ".env"
DEFAULT_SCHEMA = ROOT / "mysql" / "20260906_000002_p3d_finance.sql"
MIGRATION_KEY = "p3d-finance-v1-20260906"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def connect(config: dict[str, str]):
    host = config.get("HOME_BUDGET_DB_HOST") or config["POLAR55_CPANEL_HOST"]
    if host in {"localhost", "127.0.0.1"}:
        host = config["POLAR55_CPANEL_HOST"]
    return mysql.connector.connect(
        host=host,
        port=int(config.get("HOME_BUDGET_DB_PORT", "3306")),
        user=config["HOME_BUDGET_DB_USER"],
        password=config["HOME_BUDGET_DB_PASSWORD"],
        database=config["HOME_BUDGET_DB_NAME"],
        autocommit=False,
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
    )


def split_sql(sql: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        if line.lstrip().startswith("--"):
            continue
        buffer.append(line)
        joined = "\n".join(buffer).strip()
        if joined.endswith(";"):
            statements.append(joined[:-1])
            buffer = []
    tail = "\n".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def add_months(value: date, count: int) -> date:
    index = value.year * 12 + value.month - 1 + count
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def stable_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://p3d.gr/Home_budget/{name}"))


def upsert(cursor, table: str, row: dict[str, Any], update_columns: list[str] | None = None) -> None:
    columns = list(row)
    updates = update_columns or [column for column in columns if column not in {"id", "user_id", "legacy_cashflow_id", "legacy_installment_id", "created_at"}]
    placeholders = ", ".join(["%s"] * len(columns))
    assignments = ", ".join(f"`{column}` = VALUES(`{column}`)" for column in updates)
    sql = f"INSERT INTO `{table}` ({', '.join(f'`{column}`' for column in columns)}) VALUES ({placeholders})"
    if assignments:
        sql += f" ON DUPLICATE KEY UPDATE {assignments}"
    cursor.execute(sql, [row[column] for column in columns])


KNOWN_CASHFLOW = {
    ("income", Decimal("1450.00")): ("Μισθός Νάσου", "income", "Μισθός", "Νάσος", "fixed", 1),
    ("income", Decimal("410.00")): ("Μισθός Ελπίδας", "income", "Legacy εισόδημα", "Άλλος", "fixed", 0),
    ("income", Decimal("40.00")): ("Ακουστικό Μητέρας", "reimbursement", "Επιστροφή", "Μητέρα", "fixed", 0),
    ("income", Decimal("60.00")): ("Ρεύμα Μητέρας", "reimbursement", "Επιστροφή", "Μητέρα", "variable", 0),
    ("income", Decimal("66.50")): ("Τηλεόραση Νίκου", "reimbursement", "Επιστροφή", "Νίκος", "fixed", 0),
    ("income", Decimal("16.13")): ("Κινητό Νίκου", "reimbursement", "Επιστροφή", "Νίκος", "fixed", 0),
    ("expense", Decimal("250.00")): ("Δάνειο Αυτοκινήτου", "expense", "Αυτοκίνητο", "Νάσος", "fixed", 0),
    ("expense", Decimal("400.00")): ("Super Market", "expense", "Σπίτι", "unassigned", "variable", 1),
    ("expense", Decimal("120.00")): ("Καύσιμα", "expense", "Μετακινήσεις", "unassigned", "variable", 1),
    ("expense", Decimal("240.00")): ("Ψυχοθεραπείες", "expense", "Υγεία", "unassigned", "fixed", 1),
    ("expense", Decimal("160.00")): ("Ρεύμα", "expense", "Λογαριασμοί", "unassigned", "variable", 1),
    ("expense", Decimal("220.00")): ("Ρεύμα", "expense", "Λογαριασμοί", "unassigned", "variable", 1),
}


CANONICAL_INSTALLMENTS = [
    {"title": "SKROUTZ", "amount": Decimal("30.32"), "total": 6, "start": date(2026, 5, 1), "card": "Energy", "payer": "unassigned"},
    {"title": "TCL", "amount": Decimal("34.60"), "total": 24, "start": date(2024, 12, 1), "card": "Energy", "payer": "unassigned"},
    {"title": "Κινητό Νίκου", "amount": Decimal("16.12"), "total": 12, "start": date(2026, 1, 1), "card": "Energy", "payer": "unassigned"},
    {"title": "Air Condition Νάσου", "amount": Decimal("35.62"), "total": 12, "start": date(2026, 2, 1), "card": "Energy", "payer": "unassigned"},
    {"title": "Ακουστικό Μητέρας", "amount": Decimal("39.58"), "total": 24, "start": date(2025, 3, 1), "card": "Energy", "payer": "Μητέρα"},
    {"title": "Ασφάλεια KIA", "amount": Decimal("21.96"), "total": 12, "start": date(2026, 5, 1), "card": "Alpha", "payer": "unassigned"},
    {"title": "Κούνια Μωρού", "amount": Decimal("50.00"), "total": 12, "start": date(2026, 9, 1), "card": "Energy", "payer": "unassigned"},
    {"title": "Φούρνος Μητέρας", "amount": Decimal("20.00"), "total": 12, "start": date(2026, 9, 1), "card": "Energy", "payer": "unassigned"},
]


def pick_legacy_plan(rows: list[dict[str, Any]], spec: dict[str, Any], used: set[str]) -> dict[str, Any] | None:
    candidates = [
        row for row in rows
        if row["id"] not in used
        and Decimal(row["monthly_payment"]) == spec["amount"]
        and int(row["total_months"]) == spec["total"]
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda row: ("auto_reconcile" in str(row.get("notes", "")), row.get("created_at")))
    return candidates[0]


def migrate(cursor) -> dict[str, Any]:
    cursor.execute("SELECT id FROM users WHERE is_owner = 1 AND status = 'active' ORDER BY created_at LIMIT 1")
    owner = cursor.fetchone()
    if not owner:
        raise RuntimeError("Active owner was not found.")
    user_id = owner["id"]

    cursor.execute("SELECT * FROM cashflow_items WHERE user_id = %s ORDER BY created_at, id", (user_id,))
    cashflow = cursor.fetchall()
    recurring_counts = {"migrated": 0, "needs_review": 0}
    for legacy in cashflow:
        key = (legacy["kind"], Decimal(legacy["amount"]))
        known = KNOWN_CASHFLOW.get(key)
        if known:
            title, kind, category, payer, amount_type, active_default = known
            needs_review = int(payer == "unassigned")
            active = int(bool(legacy["is_active"]) and bool(active_default))
        else:
            title = legacy["title"] or "Legacy record"
            kind = legacy["kind"]
            category = "Legacy"
            payer = "unassigned"
            amount_type = "fixed"
            active = 0
            needs_review = 1
        upsert(cursor, "finance_recurring_items", {
            "id": legacy["id"], "user_id": user_id, "legacy_cashflow_id": legacy["id"],
            "kind": kind, "title": title, "amount": legacy["amount"], "category": category,
            "payer": payer, "recurrence": "monthly", "start_month": date(2026, 3, 1), "end_month": None,
            "payment_method": "", "amount_type": amount_type, "affects_my_budget": active_default if known else 0,
            "is_active": active, "needs_review": needs_review, "source": legacy["source"],
            "notes": legacy["notes"] or "",
        })
        recurring_counts["migrated"] += 1
        recurring_counts["needs_review"] += needs_review

    cursor.execute("SELECT id, issuer, label, last4 FROM card_accounts WHERE user_id = %s", (user_id,))
    cards = cursor.fetchall()
    energy_card = next((row for row in cards if row.get("last4") == "1001"), None)
    alpha_card = next((row for row in cards if row.get("last4") == "1004" and "Bonus" not in row.get("label", "")), None)
    card_by_short = {"Energy": energy_card, "Alpha": alpha_card}

    cursor.execute("SELECT * FROM installment_plans WHERE user_id = %s ORDER BY created_at, id", (user_id,))
    legacy_plans = cursor.fetchall()
    used: set[str] = set()
    canonical_ids: set[str] = set()
    missing: list[str] = []
    for spec in CANONICAL_INSTALLMENTS:
        legacy = pick_legacy_plan(legacy_plans, spec, used)
        if not legacy:
            missing.append(spec["title"])
            continue
        used.add(legacy["id"])
        canonical_ids.add(legacy["id"])
        card = card_by_short[spec["card"]]
        is_third_party = spec["payer"] not in {"unassigned", "Νάσος", "Κοινό"}
        upsert(cursor, "finance_installments", {
            "id": legacy["id"], "user_id": user_id, "legacy_installment_id": legacy["id"],
            "card_account_id": card["id"] if card else legacy["card_account_id"], "card_label": spec["card"],
            "title": spec["title"], "total_amount": spec["amount"] * spec["total"],
            "total_installments": spec["total"], "installment_amount": spec["amount"],
            "start_month": spec["start"], "end_month": add_months(spec["start"], spec["total"] - 1),
            "payer": spec["payer"], "charged_to": spec["card"], "affects_my_budget": 0 if is_third_party else 1,
            "reimbursement_expected": int(is_third_party), "reimbursement_amount": spec["amount"] if is_third_party else 0,
            "reimbursement_status": "pending" if is_third_party else "none", "status": "active", "is_active": 1,
            "needs_review": int(spec["payer"] == "unassigned"), "notes": legacy["notes"] or "",
        })

    for legacy in legacy_plans:
        if legacy["id"] in canonical_ids:
            continue
        total = max(1, int(legacy["total_months"]))
        start = legacy["start_date"]
        card = next((row for row in cards if row["id"] == legacy["card_account_id"]), None)
        card_label = "Energy" if card and card.get("last4") == "1001" else "Alpha" if card and card.get("last4") == "1004" else (card["label"] if card else "Χωρίς κάρτα")
        upsert(cursor, "finance_installments", {
            "id": legacy["id"], "user_id": user_id, "legacy_installment_id": legacy["id"],
            "card_account_id": legacy["card_account_id"], "card_label": card_label,
            "title": legacy["title"] or "Legacy δόση", "total_amount": legacy["total_amount"],
            "total_installments": total, "installment_amount": legacy["monthly_payment"],
            "start_month": start, "end_month": add_months(start, total - 1),
            "payer": "unassigned", "charged_to": card_label, "affects_my_budget": 0,
            "reimbursement_expected": 0, "reimbursement_amount": 0, "reimbursement_status": "none",
            "status": legacy["status"], "is_active": 0, "needs_review": 1,
            "notes": f"Preserved legacy row; excluded from active budget pending review. {legacy['notes'] or ''}".strip(),
        })

    cursor.execute("SELECT * FROM car_loans WHERE user_id = %s ORDER BY created_at LIMIT 1", (user_id,))
    car = cursor.fetchone()
    if car:
        cursor.execute(
            "UPDATE car_loans SET label=%s, start_date=%s, total_months=%s, monthly_payment=%s, down_payment=%s, balloon=%s, is_active=1 WHERE id=%s AND user_id=%s",
            ("Αυτοκίνητο", date(2023, 5, 1), 65, Decimal("250.00"), Decimal("1500.00"), Decimal("0.00"), car["id"], user_id),
        )

    upsert(cursor, "finance_savings_goals", {
        "id": stable_id("emergency-fund"), "user_id": user_id, "title": "Μαξιλάρι Ασφαλείας",
        "target_amount": Decimal("3000.00"), "current_balance": None, "target_date": None,
        "is_active": 1, "notes": "Το αρχικό υπόλοιπο παραμένει κενό μέχρι να καταχωρηθεί.",
    })
    upsert(cursor, "finance_scenarios", {
        "id": stable_id("housing-50-nikos"), "user_id": user_id,
        "title": "Παραμονή στο σπίτι – πληρωμή 50% στον Νίκο", "monthly_amount": Decimal("300.00"),
        "start_month": None, "end_month": None, "is_active": 0,
        "notes": "Συνολική εκτιμώμενη αξία ενοικίου 600€/μήνα. Ανενεργό σενάριο.",
    })
    upsert(cursor, "finance_settings", {
        "user_id": user_id, "printing_forecast_low": Decimal("80.00"),
        "printing_forecast_typical": Decimal("120.00"), "printing_forecast_good": Decimal("160.00"),
        "printing_savings_rate": Decimal("100.00"), "safe_spend_basis": "month_end",
    }, ["printing_forecast_low", "printing_forecast_typical", "printing_forecast_good"])

    summary = {
        "cashflow_found": len(cashflow), "recurring_migrated": recurring_counts["migrated"],
        "recurring_needs_review": recurring_counts["needs_review"], "legacy_installments_found": len(legacy_plans),
        "canonical_installments": len(canonical_ids), "preserved_review_installments": len(legacy_plans) - len(canonical_ids),
        "missing_canonical": missing, "car_loans": 1 if car else 0, "cards_found": len(cards),
    }
    upsert(cursor, "finance_migration_log", {
        "id": stable_id(MIGRATION_KEY), "user_id": user_id, "migration_key": MIGRATION_KEY,
        "summary": json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
    }, ["summary"])
    return summary


def preview(cursor) -> dict[str, Any]:
    cursor.execute("SELECT id FROM users WHERE is_owner = 1 AND status = 'active' ORDER BY created_at LIMIT 1")
    owner = cursor.fetchone()
    if not owner:
        raise RuntimeError("Active owner was not found.")
    user_id = owner["id"]
    cursor.execute("SELECT COUNT(*) AS count FROM cashflow_items WHERE user_id = %s", (user_id,))
    cashflow_count = int(cursor.fetchone()["count"])
    cursor.execute("SELECT * FROM installment_plans WHERE user_id = %s ORDER BY created_at, id", (user_id,))
    legacy_plans = cursor.fetchall()
    used: set[str] = set()
    missing: list[str] = []
    for spec in CANONICAL_INSTALLMENTS:
        row = pick_legacy_plan(legacy_plans, spec, used)
        if row:
            used.add(row["id"])
        else:
            missing.append(spec["title"])
    cursor.execute("SELECT COUNT(*) AS count FROM card_accounts WHERE user_id = %s", (user_id,))
    return {
        "cashflow_found": cashflow_count,
        "legacy_installments_found": len(legacy_plans),
        "canonical_installments_matched": len(used),
        "missing_canonical": missing,
        "cards_found": int(cursor.fetchone()["count"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply the non-destructive P3D Finance migration.")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    connection = connect(load_env(args.env))
    cursor = connection.cursor(dictionary=True)
    try:
        if args.dry_run:
            summary = preview(cursor)
            connection.rollback()
            already_applied = False
        else:
            for statement in split_sql(args.schema.read_text(encoding="utf-8")):
                cursor.execute(statement)
            cursor.execute(
                "SELECT summary FROM finance_migration_log WHERE migration_key = %s LIMIT 1",
                (MIGRATION_KEY,),
            )
            existing = cursor.fetchone()
            if existing:
                summary = json.loads(existing["summary"])
                already_applied = True
            else:
                summary = migrate(cursor)
                already_applied = False
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
    print(json.dumps({"dry_run": args.dry_run, "already_applied": already_applied, "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
