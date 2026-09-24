#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from src.pipeline import write_json  # noqa: E402

IGNORED_KEYS = {"cpu_seconds", "max_rss_kib", "invocation_cpu_seconds", "case_cpu_seconds", "cumulative_case_cpu_seconds", "total_invocation_cpu_seconds", "invocations"}


def logical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: logical(item) for key, item in value.items() if key not in IGNORED_KEYS}
    if isinstance(value, list):
        return [logical(item) for item in value]
    return value


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
    ref_files = sorted((reference / "cases").glob("*.json"))
    replay_files = sorted((replay / "cases").glob("*.json"))
    errors: list[str] = []
    if [item.name for item in ref_files] != [item.name for item in replay_files]:
        errors.append("case-file sets differ")
    else:
        for left_path, right_path in zip(ref_files, replay_files):
            left = logical(json.loads(left_path.read_text(encoding="utf-8")))
            right = logical(json.loads(right_path.read_text(encoding="utf-8")))
            if left != right:
                errors.append(left_path.name)
                if len(errors) >= 20:
                    break
    report = {
        "schema": 1,
        "reference_cases": len(ref_files),
        "replay_cases": len(replay_files),
        "logical_match": not errors,
        "mismatches": errors,
    }
    write_json(output, report)
    print(json.dumps(report, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
