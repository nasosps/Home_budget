#!/usr/bin/env python
"""
Watch the local bank_files folder and run the import pipeline automatically
when new or changed PDF files appear.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_INPUT_DIR = "bank_files"
DEFAULT_POLL_SECONDS = 5.0
DEFAULT_SETTLE_SECONDS = 15.0
DEFAULT_STATE_PATH = ".local/pipeline/watch-state.json"
DEFAULT_LOG_PATH = ".local/pipeline/watch-log.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch local bank PDFs and auto-run the import pipeline.")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help="Folder with raw bank PDFs")
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS, help="Polling interval in seconds")
    parser.add_argument("--settle-seconds", type=float, default=DEFAULT_SETTLE_SECONDS, help="How long a file must stay unchanged before processing")
    parser.add_argument("--state-path", default=DEFAULT_STATE_PATH, help="Local watcher state file")
    parser.add_argument("--log-path", default=DEFAULT_LOG_PATH, help="Local watcher log file")
    parser.add_argument("--dry-run", action="store_true", help="Pass dry-run through to the pipeline")
    parser.add_argument("--once", action="store_true", help="Check once and exit instead of watching continuously")
    return parser.parse_args()


def append_log(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_state(path: Path) -> dict[str, dict[str, int]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, snapshot: dict[str, dict[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def current_snapshot(input_dir: Path) -> dict[str, dict[str, int]]:
    snapshot: dict[str, dict[str, int]] = {}
    for pdf_path in sorted(input_dir.glob("*.pdf")):
        stat = pdf_path.stat()
        snapshot[pdf_path.name] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    return snapshot


def changed_ready_files(
    input_dir: Path,
    previous_state: dict[str, dict[str, int]],
    snapshot: dict[str, dict[str, int]],
    settle_seconds: float,
) -> list[str]:
    ready: list[str] = []
    now_ns = time.time_ns()
    settle_ns = int(settle_seconds * 1_000_000_000)

    for name, signature in snapshot.items():
        if previous_state.get(name) == signature:
            continue
        age_ns = now_ns - signature["mtime_ns"]
        if age_ns >= settle_ns:
            ready.append(name)
    return ready


def run_pipeline(script_dir: Path, dry_run: bool) -> None:
    command = [sys.executable, str(script_dir / "process_bank_files.py")]
    if dry_run:
        command.append("--dry-run")
    completed = subprocess.run(command, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Pipeline failed with exit code {completed.returncode}")


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    input_dir = Path(args.input_dir)
    state_path = Path(args.state_path)
    log_path = Path(args.log_path)

    print(f"Watching {input_dir.resolve()} for new PDFs...")

    try:
        while True:
            input_dir.mkdir(parents=True, exist_ok=True)
            state = load_state(state_path)
            snapshot = current_snapshot(input_dir)
            ready_files = changed_ready_files(input_dir, state, snapshot, args.settle_seconds)

            if ready_files:
                print(f"Detected ready PDF changes: {', '.join(ready_files)}")
                append_log(
                    log_path,
                    {
                        "timestamp": utc_now(),
                        "status": "detected",
                        "input_dir": str(input_dir),
                        "dry_run": args.dry_run,
                        "files": ready_files,
                    },
                )
                try:
                    run_pipeline(script_dir, args.dry_run)
                    save_state(state_path, snapshot)
                    append_log(
                        log_path,
                        {
                            "timestamp": utc_now(),
                            "status": "completed",
                            "input_dir": str(input_dir),
                            "dry_run": args.dry_run,
                            "files": ready_files,
                        },
                    )
                    print("Auto-import completed.")
                except Exception as exc:
                    append_log(
                        log_path,
                        {
                            "timestamp": utc_now(),
                            "status": "failed",
                            "input_dir": str(input_dir),
                            "dry_run": args.dry_run,
                            "files": ready_files,
                            "error": str(exc),
                        },
                    )
                    print(f"Auto-import failed: {exc}")

            elif args.once:
                print("No new ready PDF files detected.")

            if args.once:
                return 0

            time.sleep(max(args.poll_seconds, 1.0))
    except KeyboardInterrupt:
        print("Watcher stopped.")
        append_log(
            log_path,
            {
                "timestamp": utc_now(),
                "status": "stopped",
                "input_dir": str(input_dir),
                "dry_run": args.dry_run,
            },
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
