from __future__ import annotations

import argparse
import gzip
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import mysql.connector


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT.parents[2] / "VSCODE" / "P3D.GR" / ".env"
DEFAULT_OUTPUT = ROOT / ".local" / "backups"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"encoding": "hex", "value": value.hex()}
    raise TypeError(f"Unsupported value: {type(value)!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a read-only gzip JSON backup of Home_budget MariaDB.")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_env(args.env)
    host = config.get("HOME_BUDGET_DB_HOST") or config["POLAR55_CPANEL_HOST"]
    if host in {"localhost", "127.0.0.1"}:
        host = config["POLAR55_CPANEL_HOST"]

    connection = mysql.connector.connect(
        host=host,
        port=int(config.get("HOME_BUDGET_DB_PORT", "3306")),
        user=config["HOME_BUDGET_DB_USER"],
        password=config["HOME_BUDGET_DB_PASSWORD"],
        database=config["HOME_BUDGET_DB_NAME"],
    )
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name",
        (config["HOME_BUDGET_DB_NAME"],),
    )
    tables = [next(iter(row.values())) for row in cursor.fetchall()]

    payload = {
        "format": "p3d-finance-mysql-backup-v1",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "database": config["HOME_BUDGET_DB_NAME"],
        "tables": {},
    }
    for table in tables:
        cursor.execute(f"SHOW CREATE TABLE `{table}`")
        create_row = cursor.fetchone()
        cursor.execute(f"SELECT * FROM `{table}`")
        payload["tables"][table] = {
            "create_sql": list(create_row.values())[-1],
            "rows": cursor.fetchall(),
        }

    cursor.close()
    connection.close()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.output_dir / f"home-budget-mysql-{stamp}.json.gz"
    with gzip.open(output, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=json_default)

    counts = {name: len(data["rows"]) for name, data in payload["tables"].items()}
    print(json.dumps({"backup": str(output), "tables": counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
