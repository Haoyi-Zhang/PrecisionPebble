#!/usr/bin/env python3
"""Deterministic consistency audit for the manuscript bibliography and its source ledger."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

ENTRY_START = re.compile(r"@(?P<kind>[A-Za-z]+)\s*\{\s*(?P<key>[^,\s]+)\s*,", re.MULTILINE)
FIELD = re.compile(r"(?P<name>[A-Za-z][A-Za-z0-9_-]*)\s*=\s*(?P<value>\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)\s*,?", re.DOTALL)
CITE = re.compile(r"\\(?:cite|citep|citet|citeauthor|citeyear|nocite)\*?(?:\[[^\]]*\])?\{([^}]*)\}")


def _entry_blocks(text: str) -> list[tuple[str, str, str]]:
    blocks: list[tuple[str, str, str]] = []
    for match in ENTRY_START.finditer(text):
        depth = 1
        index = match.end()
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        if depth:
            raise ValueError(f"unterminated BibTeX entry {match.group('key')}")
        blocks.append((match.group("kind").lower(), match.group("key"), text[match.end(): index - 1]))
    return blocks


def parse_bibtex(text: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for kind, key, body in _entry_blocks(text):
        if key in result:
            raise ValueError(f"duplicate BibTeX key {key}")
        fields: dict[str, str] = {}
        for match in FIELD.finditer(body):
            value = match.group("value").strip()
            if (value.startswith("{") and value.endswith("}")) or (value.startswith('"') and value.endswith('"')):
                value = value[1:-1]
            fields[match.group("name").lower()] = " ".join(value.split())
        result[key] = {"kind": kind, "fields": fields}
    return result


def cited_keys(tex: str) -> set[str]:
    keys: set[str] = set()
    for group in CITE.findall(tex):
        for key in group.split(","):
            stripped = key.strip()
            if stripped and stripped != "*":
                keys.add(stripped)
    return keys


def _normalize_doi(value: str) -> str:
    value = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value.rstrip("/.")


def _normalize_title(value: str) -> str:
    value = value.replace("{", "").replace("}", "")
    value = value.replace("--", "-")
    return " ".join(value.split()).casefold()


def _canonical_identifier(fields: dict[str, str]) -> tuple[str, str]:
    if fields.get("doi"):
        return "doi", _normalize_doi(fields["doi"])
    if fields.get("url"):
        value = fields["url"].strip()
        if "doi.org/" in value.lower():
            return "doi", _normalize_doi(value)
        return "url", value.rstrip("/")
    if fields.get("eprint"):
        prefix = fields.get("archiveprefix", "").casefold()
        value = fields["eprint"].strip()
        return ("arxiv", value.casefold()) if prefix == "arxiv" else ("eprint", value.casefold())
    if fields.get("isbn"):
        return "isbn", re.sub(r"[^0-9xX]", "", fields["isbn"]).casefold()
    return "", ""


def _canonical_ledger_identifier(value: str) -> tuple[str, str]:
    value = value.strip()
    lower = value.casefold()
    if lower.startswith(("10.", "doi:", "https://doi.org/", "http://doi.org/")):
        return "doi", _normalize_doi(value)
    if lower.startswith("arxiv:"):
        return "arxiv", value.split(":", 1)[1].strip().casefold()
    if lower.startswith(("http://", "https://")):
        return "url", value.rstrip("/")
    compact = re.sub(r"[^0-9xX]", "", value)
    if len(compact) in {10, 13}:
        return "isbn", compact.casefold()
    return "literal", lower


def _verification_rows(path: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    errors: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "key", "year", "title", "identifier", "manuscript_role",
            "verification_basis", "checked_on", "status", "notes",
        }
        missing_columns = sorted(required - set(reader.fieldnames or []))
        if missing_columns:
            return {}, [f"verification ledger missing columns: {missing_columns}"]
        rows: dict[str, dict[str, str]] = {}
        for number, row in enumerate(reader, start=2):
            key = (row.get("key") or "").strip()
            if not key:
                errors.append(f"verification ledger row {number}: empty key")
                continue
            if key in rows:
                errors.append(f"verification ledger duplicate key {key}")
                continue
            rows[key] = {name: (value or "").strip() for name, value in row.items()}
    return rows, errors


def audit(tex_path: Path, bib_path: Path, minimum: int, verification_path: Path | None = None) -> dict[str, Any]:
    tex = tex_path.read_text(encoding="utf-8")
    bib = parse_bibtex(bib_path.read_text(encoding="utf-8"))
    cited = cited_keys(tex)
    keys = set(bib)
    errors: list[str] = []

    missing = sorted(cited - keys)
    unused = sorted(keys - cited)
    if missing:
        errors.append(f"missing cited keys: {missing}")
    if unused:
        errors.append(f"uncited bibliography entries: {unused}")
    if len(keys) < minimum:
        errors.append(f"bibliography has {len(keys)} entries; minimum is {minimum}")

    dois: dict[str, str] = {}
    for key, entry in sorted(bib.items()):
        fields = entry["fields"]
        for required in ("author", "title", "year"):
            if not fields.get(required):
                errors.append(f"{key}: missing {required}")
        if entry["kind"] not in {"book", "inbook"} and not any(fields.get(name) for name in ("doi", "url", "eprint")):
            errors.append(f"{key}: missing DOI, URL, or eprint identifier")
        doi = _normalize_doi(fields.get("doi", ""))
        if doi:
            if doi in dois:
                errors.append(f"duplicate DOI {doi}: {dois[doi]} and {key}")
            else:
                dois[doi] = key

    verification_count = 0
    missing_verification: list[str] = []
    extra_verification: list[str] = []
    verification_mismatches: list[str] = []
    verification_name = None
    if verification_path is not None:
        verification_name = verification_path.name
        ledger, ledger_errors = _verification_rows(verification_path)
        errors.extend(ledger_errors)
        verification_count = len(ledger)
        ledger_keys = set(ledger)
        missing_verification = sorted(keys - ledger_keys)
        extra_verification = sorted(ledger_keys - keys)
        if missing_verification:
            errors.append(f"bibliography keys missing from verification ledger: {missing_verification}")
        if extra_verification:
            errors.append(f"verification ledger keys absent from bibliography: {extra_verification}")
        today = dt.date.today()
        for key in sorted(keys & ledger_keys):
            fields = bib[key]["fields"]
            row = ledger[key]
            if row["year"] != fields.get("year", ""):
                verification_mismatches.append(f"{key}: year {row['year']!r} != {fields.get('year', '')!r}")
            if _normalize_title(row["title"]) != _normalize_title(fields.get("title", "")):
                verification_mismatches.append(f"{key}: title mismatch")
            bib_id = _canonical_identifier(fields)
            ledger_id = _canonical_ledger_identifier(row["identifier"])
            if bib_id != ledger_id:
                verification_mismatches.append(f"{key}: identifier {row['identifier']!r} != {bib_id[1]!r}")
            if row["status"].casefold() != "retained and cited":
                verification_mismatches.append(f"{key}: status is not 'retained and cited'")
            if not row["manuscript_role"]:
                verification_mismatches.append(f"{key}: empty manuscript_role")
            if not row["verification_basis"]:
                verification_mismatches.append(f"{key}: empty verification_basis")
            try:
                checked = dt.date.fromisoformat(row["checked_on"])
                if checked > today:
                    verification_mismatches.append(f"{key}: checked_on is in the future")
            except ValueError:
                verification_mismatches.append(f"{key}: invalid checked_on date {row['checked_on']!r}")
        errors.extend(f"verification mismatch: {item}" for item in verification_mismatches)

    return {
        "schema": 2,
        "tex": tex_path.name,
        "bib": bib_path.name,
        "verification_csv": verification_name,
        "minimum_entries": minimum,
        "entry_count": len(keys),
        "cited_key_count": len(cited),
        "identified_entries": sum(
            1
            for entry in bib.values()
            if any(entry["fields"].get(name) for name in ("doi", "url", "eprint", "isbn"))
        ),
        "verification_row_count": verification_count,
        "missing_citations": missing,
        "unused_entries": unused,
        "missing_verification_keys": missing_verification,
        "extra_verification_keys": extra_verification,
        "verification_mismatches": verification_mismatches,
        "errors": errors,
        "valid": not errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tex", default="../paper/main.tex")
    parser.add_argument("--bib", default="../paper/references.bib")
    parser.add_argument("--verification")
    parser.add_argument("--minimum", type=int, default=30)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]

    def resolve(value: str | None) -> Path | None:
        if value is None:
            return None
        path = Path(value)
        return path if path.is_absolute() else (repo / path).resolve()

    tex_path = resolve(args.tex)
    bib_path = resolve(args.bib)
    verification_path = resolve(args.verification)
    output = resolve(args.output)
    assert tex_path is not None and bib_path is not None and output is not None

    report = audit(tex_path, bib_path, args.minimum, verification_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
