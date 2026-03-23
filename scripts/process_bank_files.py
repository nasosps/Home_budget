#!/usr/bin/env python
"""
Run the full local bank import pipeline in one command.

Steps:
1. Parse raw PDFs from `bank_files/`
2. Sync normalized JSON into Supabase
3. Write a local run log
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


DEFAULT_INPUT_DIR = "bank_files"
DEFAULT_OUTPUT_DIR = ".local/imports"
DEFAULT_PIPELINE_LOG = ".local/pipeline/process-log.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse local bank PDFs and sync them to Supabase.")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help="Folder with raw bank PDFs")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Folder for parsed JSON output")
    parser.add_argument("--dry-run", action="store_true", help="Run the Supabase sync in dry-run mode")
    return parser.parse_args()


def append_local_log(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_step(name: str, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    print(f"[{name}] {' '.join(command)}")
    completed = subprocess.run(command, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {completed.returncode}")
    return completed


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    pipeline_log = Path(DEFAULT_PIPELINE_LOG)

    parse_command = [
        sys.executable,
        str(script_dir / "import_alpha_pdfs.py"),
        "--input-dir",
        args.input_dir,
        "--output-dir",
        args.output_dir,
    ]
    sync_command = [
        sys.executable,
        str(script_dir / "sync_to_supabase.py"),
    ]
    if args.dry_run:
        sync_command.append("--dry-run")

    started_at = utc_now()
    try:
        run_step("parse", parse_command)
        run_step("sync", sync_command)
        append_local_log(
            pipeline_log,
            {
                "timestamp": started_at,
                "status": "completed",
                "input_dir": args.input_dir,
                "output_dir": args.output_dir,
                "dry_run": args.dry_run,
            },
        )
        print("Pipeline finished successfully.")
        return 0
    except Exception as exc:
        append_local_log(
            pipeline_log,
            {
                "timestamp": started_at,
                "status": "failed",
                "input_dir": args.input_dir,
                "output_dir": args.output_dir,
                "dry_run": args.dry_run,
                "error": str(exc),
            },
        )
        print(f"Pipeline failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
