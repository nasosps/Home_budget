#!/usr/bin/env python
"""
Local parser for Alpha Bank PDF exports.

Purpose:
- Keep raw bank PDFs local
- Parse statements into normalized JSON
- Leave a durable local import manifest under .local/imports/

This script does not upload anything yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable

import fitz
import pdfplumber


CARD_HEADER_RE = re.compile(
    r"^(?P<number>\d{16}) Από (?P<date_from>\d{2}/\d{2}/\d{4}) Έως (?P<date_to>\d{2}/\d{2}/\d{4})$"
)
ACCOUNT_HEADER_RE = re.compile(
    r"^\d+\s+Αποτελέσματα Κινήσεις Λογαριασμού:\s+(?P<iban>\S+)\s+(?P<date_from>\d{1,2}/\d{1,2}/\d{4})\s+-\s+(?P<date_to>\d{1,2}/\d{1,2}/\d{4})$"
)
ACCOUNT_ROW_RE = re.compile(
    r"^(?P<row>\d+)\s+"
    r"(?P<posted_on>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<location_code>\d{2})\s+"
    r"(?P<effective_on>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<transaction_ref>\d{18})\s+"
    r"(?P<amount>[\d.,]+)\s+"
    r"(?P<sign>[ΠΧ])$"
)
DATE_LINE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
TIME_LINE_RE = re.compile(
    r"^(?P<time>\d{2}:\d{2})(?:\s+(?P<body>.*?))?(?:\s+(?P<amount>-?[\d.,]+))?$"
)
AMOUNT_ONLY_RE = re.compile(r"^-?[\d.,]+$")
LABEL_AND_AMOUNT_RE = re.compile(r"^(?P<label>.+?)\s+(?P<amount>-?[\d.,]+)$")
PRINTED_AT_RE = re.compile(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}$")
CARD_NUMBER_OCR_RE = re.compile(r"\b(\d{4}\s?\d{4}\s?\d{4}\s?\d{4})\b")
DATE_ANY_RE = re.compile(r"\b(\d{1,2}/\s*\d{1,2}/\d{4})\b")
EURO_AMOUNT_OCR_RE = re.compile(r"€\s*([\d.,]+)")

PENDING_TEXT = "Σε επεξεργασία"

CARD_IGNORED_PREFIXES = (
    "ALPHA ΤΡΑΠΕΖΑ Α.Ε.",
    "Σταδίου 40",
    "102 52 Αθήνα",
    "Α.Φ.Μ. 996807331",
    "Συναλλαγές e-Banking",
    "Κινήσεις Κάρτας",
    "Είμαστε δίπλα σας",
    "Μπορείτε να επικοινωνείτε μαζί μας",
    "Σελίδα ",
    "Ημερομηνία Εκτύπωσης",
)
ACCOUNT_IGNORED_PREFIXES = (
    "Α/Α Ημ/νία Αιτιολογία",
    "Χρήστης:",
)


@dataclass
class ParsedFile:
    file_name: str
    sha256: str
    kind: str
    output_path: str
    transaction_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse Alpha Bank PDFs from a local folder.")
    parser.add_argument("--input-dir", default="bank_files", help="Folder containing PDF exports")
    parser.add_argument("--output-dir", default=".local/imports", help="Folder for parsed JSON output")
    return parser.parse_args()


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_decimal(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


def parse_date(value: str) -> str:
    return datetime.strptime(value, "%d/%m/%Y").date().isoformat()


def parse_flexible_date(value: str) -> str:
    cleaned = value.replace(" ", "")
    return datetime.strptime(cleaned, "%d/%m/%Y").date().isoformat()


def fingerprint(*parts: object) -> str:
    payload = "|".join("" if part is None else str(part).strip() for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_lines(path: Path) -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines.extend(line.strip() for line in text.splitlines() if line.strip())
    return lines


def split_label_and_amount(text: str) -> tuple[str, str | None]:
    stripped = text.strip()
    if AMOUNT_ONLY_RE.fullmatch(stripped):
        return "", stripped
    match = LABEL_AND_AMOUNT_RE.match(stripped)
    if match:
        return match.group("label").strip(), match.group("amount")
    return stripped, None


def classify_statement(lines: Iterable[str]) -> str:
    text = "\n".join(lines)
    if "Κινήσεις Κάρτας" in text:
        return "card_statement_pdf"
    if "Κινήσεις Λογαριασμού" in text:
        return "bank_account_pdf"
    return "other"


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if ord(char) < 128).lower()


def normalize_card_label_from_ocr(lines: list[str], card_last4: str) -> str:
    if card_last4 == "1001":
        return "Energy Mastercard"
    if card_last4 == "1004":
        return "Alpha Bank MasterCard"

    for line in lines[:10]:
        compact = normalize_space(line)
        lowered = compact.lower()
        if "mastercard" not in lowered:
            continue
        if "energy" in lowered:
            return "Energy Mastercard"
        if "bonus" in lowered:
            return "Alpha Bonus Mastercard"
        return compact.replace("”", "").strip()

    return f"Alpha Bank Mastercard {card_last4}"


def ocr_first_page(path: Path) -> str | None:
    if shutil.which("tesseract") is None:
        return None

    with tempfile.TemporaryDirectory() as temp_dir:
        image_path = Path(temp_dir) / "page.png"
        output_base = Path(temp_dir) / "ocr"

        document = fitz.open(path)
        try:
            page = document.load_page(0)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            pixmap.save(image_path)
        finally:
            document.close()

        completed = subprocess.run(
            ["tesseract", str(image_path), str(output_base), "-l", "eng", "--psm", "6"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return None

        text_path = output_base.with_suffix(".txt")
        if not text_path.exists():
            return None
        return text_path.read_text(encoding="utf-8", errors="replace")


def extract_first_numeric_amount(lines: list[str], *hints: str) -> float | None:
    lowered_hints = tuple(ascii_fold(hint) for hint in hints)
    for line in lines:
        lowered = ascii_fold(line)
        if lowered_hints and not any(hint in lowered for hint in lowered_hints):
            continue
        matches = re.findall(r"(\d[\d.,]*)", line)
        if matches:
            return float(parse_decimal(matches[-1]))
    return None


def parse_card_account_summary(path: Path, lines: list[str], sha256: str) -> dict | None:
    ocr_text = ocr_first_page(path)
    if not ocr_text:
        return None

    normalized_text = normalize_space(ocr_text)
    if "ALPHA BANK" not in normalized_text.upper():
        return None

    card_match = CARD_NUMBER_OCR_RE.search(normalized_text)
    raw_card_number = next((line.strip() for line in lines if re.fullmatch(r"\d{16}", line.strip())), "")
    if card_match:
        card_number = re.sub(r"\s+", "", card_match.group(1))
    elif raw_card_number:
        card_number = raw_card_number
    else:
        return None
    card_last4 = card_number[-4:]
    ocr_lines = [normalize_space(line) for line in ocr_text.splitlines() if normalize_space(line)]
    date_matches = DATE_ANY_RE.findall(normalized_text)
    amount_matches = EURO_AMOUNT_OCR_RE.findall(normalized_text)

    if len(date_matches) < 2 or len(amount_matches) < 3:
        return None

    statement_issued_on = parse_flexible_date(date_matches[0])
    payment_due_on = parse_flexible_date(date_matches[1])
    credit_limit = float(parse_decimal(amount_matches[0]))
    cash_limit = float(parse_decimal(amount_matches[1]))
    new_balance = extract_first_numeric_amount(ocr_lines, "neo y")
    if new_balance is None:
        new_balance = float(parse_decimal(amount_matches[2]))
    minimum_payment = float(parse_decimal(amount_matches[3])) if len(amount_matches) >= 4 else None
    if minimum_payment is None:
        minimum_payment = extract_first_numeric_amount(ocr_lines, "katab", "kava")
    if minimum_payment is None:
        return None

    return {
        "source_bank": "alpha_bank",
        "kind": "card_account_summary_pdf",
        "file_name": path.name,
        "sha256": sha256,
        "card_label": normalize_card_label_from_ocr(ocr_lines, card_last4),
        "card_number_masked": mask_card_number(card_number),
        "card_last4": card_last4,
        "statement_from": None,
        "statement_to": statement_issued_on,
        "statement_issued_on": statement_issued_on,
        "payment_due_on": payment_due_on,
        "credit_limit": credit_limit,
        "cash_limit": cash_limit,
        "new_balance": new_balance,
        "minimum_payment": minimum_payment,
        "transactions": [],
        "ocr_excerpt": normalized_text[:1200],
    }


def parse_card_statement(path: Path, lines: list[str], sha256: str) -> dict:
    card_label = ""
    card_number = ""
    statement_from = ""
    statement_to = ""

    for index, line in enumerate(lines):
        if line == "Κινήσεις Κάρτας" and index + 2 < len(lines):
            card_label = lines[index + 1]
            match = CARD_HEADER_RE.match(lines[index + 2])
            if match:
                card_number = match.group("number")
                statement_from = parse_date(match.group("date_from"))
                statement_to = parse_date(match.group("date_to"))
            break

    filtered: list[str] = []
    for line in lines:
        if any(line.startswith(prefix) for prefix in CARD_IGNORED_PREFIXES):
            continue
        if CARD_HEADER_RE.match(line):
            continue
        if PRINTED_AT_RE.match(line):
            continue
        filtered.append(line)

    transactions: list[dict] = []
    current_date: str | None = None
    buffer: list[str] = []

    def flush_buffer() -> None:
        if current_date is None or not buffer:
            return
        transactions.extend(parse_card_date_block(current_date, buffer, card_number))
        buffer.clear()

    for line in filtered:
        if DATE_LINE_RE.match(line):
            flush_buffer()
            current_date = parse_date(line)
            continue
        buffer.append(line)

    flush_buffer()

    for index, transaction in enumerate(transactions, start=1):
        transaction["entry_index"] = index

    return {
        "source_bank": "alpha_bank",
        "kind": "card_statement_pdf",
        "file_name": path.name,
        "sha256": sha256,
        "card_label": card_label,
        "card_number_masked": mask_card_number(card_number),
        "card_last4": card_number[-4:] if card_number else None,
        "statement_from": statement_from or None,
        "statement_to": statement_to or None,
        "transactions": transactions,
    }


def parse_card_date_block(posted_on: str, lines: list[str], card_number: str) -> list[dict]:
    entries: list[dict] = []
    index = 0

    while index < len(lines):
        if is_probable_merchant_line(lines, index):
            merchant_line = lines[index]
            time_line = lines[index + 1]
            index += 2

            detail_lines: list[str] = []
            while index < len(lines):
                if is_probable_merchant_line(lines, index):
                    break
                detail_lines.append(lines[index])
                index += 1

            entries.append(
                build_card_entry(
                    posted_on=posted_on,
                    merchant_line=merchant_line,
                    time_line=time_line,
                    detail_lines=detail_lines,
                    card_number=card_number,
                    entry_index=len(entries) + 1,
                )
            )
            continue

        index += 1

    return entries


def is_probable_merchant_line(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    line = lines[index]
    next_line = lines[index + 1]
    return not TIME_LINE_RE.match(line) and bool(TIME_LINE_RE.match(next_line))


def normalize_card_details(detail_lines: list[str]) -> tuple[str, str, list[str]]:
    clean_detail_lines = [line for line in detail_lines if not PRINTED_AT_RE.match(line)]
    category_parts: list[str] = []
    status_parts: list[str] = []

    for line in clean_detail_lines:
        if PENDING_TEXT in line:
            stripped = line.replace(PENDING_TEXT, "").strip()
            if stripped:
                category_parts.append(stripped)
            status_parts.append(PENDING_TEXT)
            continue
        category_parts.append(line)

    category = " | ".join(part for part in category_parts if part)
    status_text = " | ".join(part for part in status_parts if part)
    return category, status_text, clean_detail_lines


def build_card_entry(
    posted_on: str,
    merchant_line: str,
    time_line: str,
    detail_lines: list[str],
    card_number: str,
    entry_index: int,
) -> dict:
    time_match = TIME_LINE_RE.match(time_line)
    if not time_match:
        raise ValueError(f"Unexpected card time line: {time_line}")

    merchant_text, merchant_amount_text = split_label_and_amount(merchant_line)

    time_text = time_match.group("time")
    body_text = (time_match.group("body") or "").strip()
    time_amount_text = time_match.group("amount")

    if body_text:
        body_label, body_amount_text = split_label_and_amount(body_text)
        if time_amount_text is None and body_amount_text is not None:
            time_amount_text = body_amount_text
            body_text = body_label

    amount_text = time_amount_text or merchant_amount_text
    if amount_text is None:
        raise ValueError(f"Could not find amount for card entry: {merchant_line} / {time_line}")

    amount_value = parse_decimal(amount_text.replace("+", ""))
    direction = "debit" if amount_text.strip().startswith("-") else "credit"
    normalized_amount = abs(amount_value)

    category, status_text, clean_detail_lines = normalize_card_details(detail_lines)

    transaction_type = body_text
    if transaction_type == "" and "Πληρωμή" in merchant_text:
        transaction_type = "Πληρωμή"

    return {
        "entry_index": entry_index,
        "posted_on": posted_on,
        "posted_time": time_text,
        "merchant": merchant_text,
        "amount": float(normalized_amount),
        "direction": direction,
        "transaction_type": transaction_type,
        "category": category,
        "status_text": status_text,
        "detail_lines": clean_detail_lines,
        "fingerprint": fingerprint("card", card_number[-4:], posted_on, time_text, merchant_text, normalized_amount, direction),
        "raw_text": {
            "merchant_line": merchant_line,
            "time_line": time_line,
        },
    }


def parse_bank_account_statement(path: Path, lines: list[str], sha256: str) -> dict:
    header_match = next((ACCOUNT_HEADER_RE.match(line) for line in lines if ACCOUNT_HEADER_RE.match(line)), None)
    if not header_match:
        raise ValueError(f"Could not identify account statement header in {path.name}")

    ending_balance = None
    previous_balance = None
    for line in lines:
        if line.startswith("Νέο μεικτό υπόλοιπο EUR "):
            ending_balance = parse_balance_line(line)
        elif line.startswith("Προηγούμενο μεικτό υπόλοιπο EUR "):
            previous_balance = parse_balance_line(line)

    transactions: list[dict] = []
    for line in lines:
        if any(line.startswith(prefix) for prefix in ACCOUNT_IGNORED_PREFIXES):
            continue
        row_match = ACCOUNT_ROW_RE.match(line)
        if not row_match:
            continue

        amount = parse_decimal(row_match.group("amount"))
        sign = row_match.group("sign")
        direction = "credit" if sign == "Π" else "debit"

        transactions.append(
            {
                "entry_index": int(row_match.group("row")),
                "posted_on": parse_date(row_match.group("posted_on")),
                "effective_on": parse_date(row_match.group("effective_on")),
                "description": row_match.group("description").strip(),
                "location_code": row_match.group("location_code"),
                "transaction_ref": row_match.group("transaction_ref"),
                "amount": float(amount),
                "direction": direction,
                "fingerprint": fingerprint(
                    "bank",
                    header_match.group("iban")[-6:],
                    row_match.group("posted_on"),
                    row_match.group("transaction_ref"),
                    row_match.group("amount"),
                    sign,
                ),
            }
        )

    return {
        "source_bank": "alpha_bank",
        "kind": "bank_account_pdf",
        "file_name": path.name,
        "sha256": sha256,
        "iban_masked": mask_iban(header_match.group("iban")),
        "statement_from": parse_date(header_match.group("date_from")),
        "statement_to": parse_date(header_match.group("date_to")),
        "ending_balance": ending_balance,
        "previous_balance": previous_balance,
        "transactions": transactions,
    }


def parse_balance_line(line: str) -> dict:
    match = re.search(r"EUR\s+([\d.,]+)\s+([ΠΧ])$", line)
    if not match:
        raise ValueError(f"Could not parse balance line: {line}")
    amount = parse_decimal(match.group(1))
    sign = match.group(2)
    return {
        "amount": float(amount),
        "direction": "credit" if sign == "Π" else "debit",
    }


def mask_card_number(card_number: str) -> str | None:
    if not card_number:
        return None
    return f"{card_number[:4]} **** **** {card_number[-4:]}"


def mask_iban(iban: str) -> str:
    return f"{iban[:6]}...{iban[-4:]}"


def write_output(output_dir: Path, path: Path, data: dict) -> Path:
    parsed_dir = output_dir / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    output_path = parsed_dir / f"{path.stem}.json"
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def append_manifest(output_dir: Path, item: ParsedFile) -> None:
    manifest_path = output_dir / "import-manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "parser_version": "alpha_pdf_v1",
        "file_name": item.file_name,
        "sha256": item.sha256,
        "kind": item.kind,
        "output_path": item.output_path,
        "transaction_count": item.transaction_count,
    }
    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {input_dir}")
        return 0

    parsed_count = 0
    for path in pdf_files:
        lines = load_lines(path)
        sha256 = sha256_of_file(path)
        kind = classify_statement(lines)

        if kind == "card_statement_pdf":
            data = parse_card_statement(path, lines, sha256)
        elif kind == "bank_account_pdf":
            data = parse_bank_account_statement(path, lines, sha256)
        else:
            data = parse_card_account_summary(path, lines, sha256)
            if data is None:
                print(f"Skipping unsupported PDF format: {path.name}")
                continue
            kind = data["kind"]

        output_path = write_output(output_dir, path, data)
        append_manifest(
            output_dir,
            ParsedFile(
                file_name=path.name,
                sha256=sha256,
                kind=kind,
                output_path=str(output_path),
                transaction_count=len(data.get("transactions", [])),
            ),
        )
        parsed_count += 1
        print(f"Parsed {path.name} -> {output_path}")

    print(f"Completed. Parsed {parsed_count} PDF file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
