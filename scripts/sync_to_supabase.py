#!/usr/bin/env python
"""
Sync parsed local import JSON files into Supabase.

This script is intentionally local-first:
- Reads normalized JSON from `.local/imports/parsed/`
- Uses the service role key from `.env`
- Writes a local sync log under `.local/sync/`

It is safe to rerun. Transactions and import files are upserted by unique keys.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_SCHEMA = "public"
DEFAULT_OWNER_EMAIL = "nasosps@outlook.com"
DEFAULT_IMPORT_DIR = ".local/imports/parsed"
DEFAULT_SYNC_LOG = ".local/sync/sync-log.jsonl"
DEFAULT_IMPORT_BUCKET = "home-budget-imports"
CHUNK_SIZE = 250


@dataclass
class Config:
    supabase_url: str
    service_role_key: str
    schema: str
    owner_email: str
    import_bucket: str
    input_dir: Path
    sync_log_path: Path
    dry_run: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync parsed Home Budget imports to Supabase.")
    parser.add_argument("--input-dir", default=None, help="Directory with parsed JSON files")
    parser.add_argument("--sync-log", default=None, help="Path to the local sync log JSONL file")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print actions without writing to Supabase")
    return parser.parse_args()


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def env_value(env_map: dict[str, str], key: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(key, env_map.get(key, default))
    if required and (value is None or value == ""):
        raise SystemExit(f"Missing required setting: {key}. Fill it in .env first.")
    return value or ""


def load_config(args: argparse.Namespace) -> Config:
    env_map = load_dotenv(Path(".env"))
    require_remote = not args.dry_run
    return Config(
        supabase_url=env_value(env_map, "SUPABASE_URL", default="", required=require_remote).rstrip("/"),
        service_role_key=env_value(env_map, "SUPABASE_SERVICE_ROLE_KEY", default="", required=require_remote),
        schema=env_value(env_map, "SUPABASE_SCHEMA", DEFAULT_SCHEMA),
        owner_email=env_value(env_map, "HOME_BUDGET_OWNER_EMAIL", DEFAULT_OWNER_EMAIL).lower(),
        import_bucket=env_value(env_map, "HOME_BUDGET_IMPORT_BUCKET", DEFAULT_IMPORT_BUCKET),
        input_dir=Path(args.input_dir or env_value(env_map, "HOME_BUDGET_LOCAL_IMPORT_DIR", DEFAULT_IMPORT_DIR)),
        sync_log_path=Path(args.sync_log or DEFAULT_SYNC_LOG),
        dry_run=args.dry_run,
    )


class SupabaseRestClient:
    def __init__(self, base_url: str, api_key: str, schema: str) -> None:
        self.base_url = f"{base_url}/rest/v1"
        self.api_key = api_key
        self.schema = schema

    def request(
        self,
        method: str,
        table: str,
        *,
        query: dict[str, str] | None = None,
        payload: Any | None = None,
        prefer: str | None = None,
    ) -> Any:
        url = f"{self.base_url}/{table}"
        if query:
            url = f"{url}?{urlencode(query)}"

        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Accept-Profile": self.schema,
        }
        if method in {"POST", "PATCH", "PUT", "DELETE"}:
            headers["Content-Profile"] = self.schema
        if prefer:
            headers["Prefer"] = prefer

        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        request = Request(url=url, data=data, headers=headers, method=method)
        try:
            with urlopen(request) as response:
                body = response.read()
                if not body:
                    return None
                return json.loads(body.decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {method} {table} failed with {exc.code}: {body}") from exc

    def select(self, table: str, filters: dict[str, str], *, columns: str = "*", limit: int | None = None) -> list[dict[str, Any]]:
        query = dict(filters)
        query["select"] = columns
        if limit is not None:
            query["limit"] = str(limit)
        data = self.request("GET", table, query=query)
        return data or []

    def insert(self, table: str, payload: dict[str, Any] | list[dict[str, Any]], *, returning: bool = True) -> Any:
        prefer = "return=representation" if returning else "return=minimal"
        return self.request("POST", table, payload=payload, prefer=prefer)

    def upsert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        on_conflict: str,
        returning: bool = True,
    ) -> Any:
        prefer_parts = ["resolution=merge-duplicates", "return=representation" if returning else "return=minimal"]
        return self.request(
            "POST",
            table,
            query={"on_conflict": on_conflict},
            payload=payload,
            prefer=",".join(prefer_parts),
        )

    def update(self, table: str, filters: dict[str, str], payload: dict[str, Any], *, returning: bool = False) -> Any:
        prefer = "return=representation" if returning else "return=minimal"
        return self.request("PATCH", table, query=filters, payload=payload, prefer=prefer)


def eq(value: Any) -> str:
    return f"eq.{value}"


def load_parsed_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        raise SystemExit(f"Parsed input directory does not exist: {input_dir}")
    files = sorted(input_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No parsed JSON files found in: {input_dir}")
    return files


def append_local_log(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def humanize_bank_name(source_bank: str) -> str:
    if source_bank == "alpha_bank":
        return "Alpha Bank"
    return source_bank.replace("_", " ").title()


def import_file_kind_for_parsed(parsed_kind: str) -> str:
    allowed = {"bank_account_pdf", "card_statement_pdf", "manual_csv", "other"}
    return parsed_kind if parsed_kind in allowed else "other"


def fetch_owner_profile(client: SupabaseRestClient, owner_email: str) -> dict[str, Any]:
    rows = client.select(
        "profiles",
        {"email": eq(owner_email)},
        columns="id,email,is_owner",
        limit=1,
    )
    if not rows:
        raise SystemExit(
            f"Owner profile not found in Supabase. Sign in once with {owner_email}, then run "
            f"`update {client.schema}.profiles set is_owner = true where email = lower('{owner_email}');`"
        )
    row = rows[0]
    if not row.get("is_owner"):
        raise SystemExit(
            f"Owner profile exists but is_owner is false. Run: "
            f"`update {client.schema}.profiles set is_owner = true where email = lower('{owner_email}');`"
        )
    return row


def get_or_create_bank_account(client: SupabaseRestClient, user_id: str, parsed: dict[str, Any]) -> str:
    iban_masked = parsed["iban_masked"]
    rows = client.select(
        "bank_accounts",
        {
            "user_id": eq(user_id),
            "iban_masked": eq(iban_masked),
        },
        columns="id,label,iban_masked",
        limit=1,
    )
    if rows:
        return rows[0]["id"]

    label = f"{humanize_bank_name(parsed['source_bank'])} {iban_masked}"
    created = client.insert(
        "bank_accounts",
        {
            "user_id": user_id,
            "bank_name": humanize_bank_name(parsed["source_bank"]),
            "label": label,
            "iban_masked": iban_masked,
            "is_active": True,
        },
        returning=True,
    )
    return created[0]["id"]


def get_or_create_card_account(client: SupabaseRestClient, user_id: str, parsed: dict[str, Any]) -> str:
    rows: list[dict[str, Any]] = []
    if parsed.get("card_last4"):
        rows = client.select(
            "card_accounts",
            {
                "user_id": eq(user_id),
                "last4": eq(parsed["card_last4"]),
            },
            columns="id,label,last4",
            limit=1,
        )
    if not rows:
        rows = client.select(
            "card_accounts",
            {
                "user_id": eq(user_id),
                "label": eq(parsed["card_label"]),
                "last4": eq(parsed["card_last4"]),
            },
            columns="id,label,last4",
            limit=1,
        )
    if rows:
        return rows[0]["id"]

    created = client.insert(
        "card_accounts",
        {
            "user_id": user_id,
            "issuer": humanize_bank_name(parsed["source_bank"]),
            "label": parsed["card_label"],
            "last4": parsed["card_last4"],
            "card_number_masked": parsed["card_number_masked"],
            "is_active": True,
        },
        returning=True,
    )
    return created[0]["id"]


def upsert_import_file(client: SupabaseRestClient, user_id: str, parsed: dict[str, Any], source_path: Path) -> dict[str, Any]:
    payload = {
        "user_id": user_id,
        "original_name": parsed["file_name"],
        "storage_path": None,
        "sha256": parsed["sha256"],
        "file_kind": import_file_kind_for_parsed(parsed["kind"]),
        "parser_key": "local.alpha_pdf.v1",
        "statement_from": parsed.get("statement_from"),
        "statement_to": parsed.get("statement_to"),
        "last_status": "processing",
        "raw_metadata": {
            "parsed_kind": parsed.get("kind"),
            "source_bank": parsed.get("source_bank"),
            "local_parsed_file": str(source_path),
            "transaction_count": len(parsed.get("transactions", [])),
            "iban_masked": parsed.get("iban_masked"),
            "card_label": parsed.get("card_label"),
            "card_last4": parsed.get("card_last4"),
            "ending_balance": parsed.get("ending_balance"),
            "previous_balance": parsed.get("previous_balance"),
            "statement_issued_on": parsed.get("statement_issued_on"),
            "payment_due_on": parsed.get("payment_due_on"),
            "credit_limit": parsed.get("credit_limit"),
            "cash_limit": parsed.get("cash_limit"),
            "new_balance": parsed.get("new_balance"),
            "minimum_payment": parsed.get("minimum_payment"),
        },
    }
    result = client.upsert(
        "import_files",
        [payload],
        on_conflict="user_id,sha256",
        returning=True,
    )
    return result[0]


def create_import_job(client: SupabaseRestClient, user_id: str, import_file_id: str) -> dict[str, Any]:
    result = client.insert(
        "import_jobs",
        {
            "user_id": user_id,
            "import_file_id": import_file_id,
            "status": "processing",
            "summary": {},
            "started_at": utc_now(),
        },
        returning=True,
    )
    return result[0]


def chunked(items: list[dict[str, Any]], size: int = CHUNK_SIZE) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def upsert_bank_transactions(
    client: SupabaseRestClient,
    *,
    user_id: str,
    import_file_id: str,
    bank_account_id: str,
    transactions: list[dict[str, Any]],
) -> None:
    rows = [
        {
            "user_id": user_id,
            "bank_account_id": bank_account_id,
            "import_file_id": import_file_id,
            "entry_index": item.get("entry_index"),
            "posted_on": item["posted_on"],
            "effective_on": item.get("effective_on"),
            "description": item["description"],
            "amount": item["amount"],
            "direction": item["direction"],
            "transaction_ref": item.get("transaction_ref"),
            "location_code": item.get("location_code"),
            "fingerprint": item["fingerprint"],
            "raw_payload": item,
        }
        for item in transactions
    ]
    for batch in chunked(rows):
        client.upsert(
            "bank_transactions",
            batch,
            on_conflict="user_id,fingerprint",
            returning=False,
        )


def upsert_card_transactions(
    client: SupabaseRestClient,
    *,
    user_id: str,
    import_file_id: str,
    card_account_id: str,
    transactions: list[dict[str, Any]],
) -> None:
    rows = [
        {
            "user_id": user_id,
            "card_account_id": card_account_id,
            "import_file_id": import_file_id,
            "entry_index": item.get("entry_index"),
            "posted_on": item["posted_on"],
            "merchant": item["merchant"],
            "posted_time": item.get("posted_time"),
            "amount": item["amount"],
            "direction": item["direction"],
            "transaction_type": item.get("transaction_type", ""),
            "status_text": item.get("status_text", ""),
            "category": item.get("category", ""),
            "fingerprint": item["fingerprint"],
            "raw_payload": item,
        }
        for item in transactions
    ]
    for batch in chunked(rows):
        client.upsert(
            "card_transactions",
            batch,
            on_conflict="user_id,fingerprint",
            returning=False,
        )


def finalize_import_success(
    client: SupabaseRestClient,
    *,
    import_file_id: str,
    import_job_id: str,
    summary: dict[str, Any],
) -> None:
    client.update(
        "import_files",
        {"id": eq(import_file_id)},
        {
            "last_status": "applied",
            "raw_metadata": summary,
        },
        returning=False,
    )
    client.update(
        "import_jobs",
        {"id": eq(import_job_id)},
        {
            "status": "applied",
            "summary": summary,
            "finished_at": utc_now(),
        },
        returning=False,
    )


def finalize_import_failure(
    client: SupabaseRestClient,
    *,
    import_file_id: str | None,
    import_job_id: str | None,
    error_text: str,
) -> None:
    if import_file_id:
        client.update(
            "import_files",
            {"id": eq(import_file_id)},
            {"last_status": "failed"},
            returning=False,
        )
    if import_job_id:
        client.update(
            "import_jobs",
            {"id": eq(import_job_id)},
            {
                "status": "failed",
                "error_text": error_text,
                "finished_at": utc_now(),
            },
            returning=False,
        )


def sync_file(client: SupabaseRestClient, user_id: str, parsed_path: Path, dry_run: bool) -> dict[str, Any]:
    parsed = load_json(parsed_path)
    kind = parsed["kind"]
    transaction_count = len(parsed.get("transactions", []))

    if dry_run:
        return {
            "file_name": parsed["file_name"],
            "kind": kind,
            "transaction_count": transaction_count,
            "status": "dry_run",
        }

    import_file = upsert_import_file(client, user_id, parsed, parsed_path)
    import_job = create_import_job(client, user_id, import_file["id"])

    try:
        if kind == "bank_account_pdf":
            account_id = get_or_create_bank_account(client, user_id, parsed)
            upsert_bank_transactions(
                client,
                user_id=user_id,
                import_file_id=import_file["id"],
                bank_account_id=account_id,
                transactions=parsed["transactions"],
            )
            account_type = "bank_account"
        elif kind == "card_statement_pdf":
            account_id = get_or_create_card_account(client, user_id, parsed)
            upsert_card_transactions(
                client,
                user_id=user_id,
                import_file_id=import_file["id"],
                card_account_id=account_id,
                transactions=parsed["transactions"],
            )
            account_type = "card_account"
        elif kind == "card_account_summary_pdf":
            account_id = get_or_create_card_account(client, user_id, parsed)
            account_type = "card_account_summary"
        else:
            raise RuntimeError(f"Unsupported parsed kind: {kind}")

        summary = {
            "synced_at": utc_now(),
            "file_name": parsed["file_name"],
            "kind": kind,
            "account_type": account_type,
            "account_id": account_id,
            "transaction_count": transaction_count,
            "statement_from": parsed.get("statement_from"),
            "statement_to": parsed.get("statement_to"),
            "statement_issued_on": parsed.get("statement_issued_on"),
            "payment_due_on": parsed.get("payment_due_on"),
            "new_balance": parsed.get("new_balance"),
            "minimum_payment": parsed.get("minimum_payment"),
            "parser_key": "local.alpha_pdf.v1",
        }
        finalize_import_success(
            client,
            import_file_id=import_file["id"],
            import_job_id=import_job["id"],
            summary=summary,
        )
        return {
            "file_name": parsed["file_name"],
            "kind": kind,
            "transaction_count": transaction_count,
            "status": "applied",
            "import_file_id": import_file["id"],
            "import_job_id": import_job["id"],
        }
    except Exception as exc:
        finalize_import_failure(
            client,
            import_file_id=import_file["id"],
            import_job_id=import_job["id"],
            error_text=str(exc),
        )
        raise


def main() -> int:
    args = parse_args()
    config = load_config(args)
    parsed_files = load_parsed_files(config.input_dir)

    print(f"Using schema: {config.schema}")
    print(f"Owner email: {config.owner_email}")
    print(f"Parsed files: {len(parsed_files)}")

    if config.dry_run:
        print("Dry run mode: Supabase writes are disabled.")
        client = None
        owner_profile = {"id": "dry-run"}
    else:
        client = SupabaseRestClient(config.supabase_url, config.service_role_key, config.schema)
        owner_profile = fetch_owner_profile(client, config.owner_email)
        print(f"Owner profile resolved: {owner_profile['email']} ({owner_profile['id']})")

    applied = 0
    failed = 0

    for parsed_path in parsed_files:
        try:
            result = sync_file(client, owner_profile["id"], parsed_path, config.dry_run) if client else sync_file(None, owner_profile["id"], parsed_path, True)
            applied += 1
            append_local_log(
                config.sync_log_path,
                {
                    "timestamp": utc_now(),
                    "status": result["status"],
                    "file_name": result["file_name"],
                    "kind": result["kind"],
                    "transaction_count": result["transaction_count"],
                    "import_file_id": result.get("import_file_id"),
                    "import_job_id": result.get("import_job_id"),
                },
            )
            print(f"{result['status'].upper()}: {result['file_name']} ({result['transaction_count']} rows)")
        except Exception as exc:
            failed += 1
            append_local_log(
                config.sync_log_path,
                {
                    "timestamp": utc_now(),
                    "status": "failed",
                    "file_name": parsed_path.name,
                    "error": str(exc),
                },
            )
            print(f"FAILED: {parsed_path.name} -> {exc}")

    print(f"Finished. Success: {applied}, Failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
