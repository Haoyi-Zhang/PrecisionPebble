#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from src.campaign import validate_complete_campaign  # noqa: E402
from src.pipeline import write_json  # noqa: E402

IGNORED_KEYS = {
    "cpu_seconds",
    "case_body_cpu_seconds",
    "max_rss_kib",
    "invocation_process_cpu_seconds",
    "cumulative_case_body_cpu_seconds",
    "total_invocation_process_cpu_seconds",
    "invocations",
}


def logical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: logical(item) for key, item in value.items() if key not in IGNORED_KEYS}
    if isinstance(value, list):
        return [logical(item) for item in value]
    return value


def compare_campaigns(repo: Path, reference: Path, replay: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        same_directory = reference.resolve() == replay.resolve()
    except OSError:
        same_directory = False
    if same_directory:
        errors.append("reference and replay resolve to the same directory")

    reference_validation = validate_complete_campaign(repo, reference)
    replay_validation = validate_complete_campaign(repo, replay)
    errors.extend(f"reference: {message}" for message in reference_validation.errors)
    errors.extend(f"replay: {message}" for message in replay_validation.errors)

    mismatches: list[str] = []
    if not errors:
        if len(reference_validation.cases) != len(replay_validation.cases):
            errors.append("validated campaign lengths differ")
        else:
            for left, right in zip(reference_validation.cases, replay_validation.cases):
                left_name = left.get("record_identity", {}).get("name", left.get("name", "<unknown>"))
                right_name = right.get("record_identity", {}).get("name", right.get("name", "<unknown>"))
                if left_name != right_name:
                    mismatches.append(f"identity:{left_name!r}!={right_name!r}")
                elif logical(left) != logical(right):
                    mismatches.append(str(left_name))
                if len(mismatches) >= 20:
                    break

    all_errors = errors + mismatches
    return {
        "schema": 2,
        "reference_cases": len(reference_validation.cases),
        "replay_cases": len(replay_validation.cases),
        "logical_match": not all_errors,
        "validation_errors": errors,
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--replay", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    reference = Path(args.reference)
    replay = Path(args.replay)
    output = Path(args.output)
    if not reference.is_absolute():
        reference = REPO / reference
    if not replay.is_absolute():
        replay = REPO / replay
    if not output.is_absolute():
        output = REPO / output
    report = compare_campaigns(REPO, reference, replay)
    write_json(output, report)
    print(json.dumps(report, indent=2))
    return 0 if report["logical_match"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
