#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from src.pipeline import evaluate_case, write_json  # noqa: E402

ADDRESS_LIMIT = 3 * 1024 * 1024 * 1024
CAMPAIGN_UNIT_CAP = 600_000
CAMPAIGN_CPU_CAP = 2_700.0


def constrain_process() -> dict[str, object]:
    resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_LIMIT, ADDRESS_LIMIT))
    affinity = None
    if hasattr(os, "sched_getaffinity") and hasattr(os, "sched_setaffinity"):
        available = sorted(os.sched_getaffinity(0))
        if available:
            os.sched_setaffinity(0, {available[0]})
            affinity = [available[0]]
    return {"address_limit_bytes": ADDRESS_LIMIT, "affinity": affinity, "workers": 1}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded chunk of the frozen 364-case campaign")
    parser.add_argument("--output", required=True, help="output directory, relative to the repository or absolute")
    parser.add_argument("--chunk", type=int, default=64, help="maximum new cases in this invocation")
    parser.add_argument("--oracle-state-cap", type=int, default=50_000)
    parser.add_argument("--oracle-cpu-cap", type=float, default=15.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.chunk <= 0:
        raise SystemExit("--chunk must be positive")
    limits = constrain_process()
    output = Path(args.output)
    if not output.is_absolute():
        output = REPO / output
    output.mkdir(parents=True, exist_ok=True)
    cases_dir = output / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    index = json.loads((REPO / "instances" / "index.json").read_text(encoding="utf-8"))
    records = index["records"]
    completed: list[str] = []
    cumulative_units = 0
    cumulative_cpu = 0.0
    for record in records:
        result_path = cases_dir / f"{record['order']:03d}-{record['name']}.json"
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("status") != "checked" or result.get("name") != record["name"]:
                raise SystemExit(f"existing record is not a checked continuation: {result_path}")
            completed.append(record["name"])
            cumulative_units += int(result["metrics"]["charged_units"])
            cumulative_cpu += float(result["metrics"]["cpu_seconds"])

    pending = [record for record in records if record["name"] not in set(completed)]
    selected = pending[: args.chunk]
    invocation_start = time.process_time()
    for record in selected:
        result = evaluate_case(
            REPO,
            record,
            oracle_state_cap=args.oracle_state_cap,
            oracle_cpu_cap=args.oracle_cpu_cap,
        )
        result_path = cases_dir / f"{record['order']:03d}-{record['name']}.json"
        write_json(result_path, result)
        if result["status"] != "checked":
            print(json.dumps(result["errors"], indent=2), file=sys.stderr)
            return 2
        completed.append(record["name"])
        cumulative_units += int(result["metrics"]["charged_units"])
        cumulative_cpu += float(result["metrics"]["cpu_seconds"])
        if cumulative_units > CAMPAIGN_UNIT_CAP:
            raise SystemExit(f"campaign enumeration cap exceeded: {cumulative_units}>{CAMPAIGN_UNIT_CAP}")
        if cumulative_cpu > CAMPAIGN_CPU_CAP:
            raise SystemExit(f"campaign CPU cap exceeded: {cumulative_cpu}>{CAMPAIGN_CPU_CAP}")
        print(
            f"checked {record['order'] + 1:03d}/{len(records)} {record['name']} "
            f"units={result['metrics']['charged_units']} cpu={result['metrics']['cpu_seconds']:.4f}s"
        )

    usage = resource.getrusage(resource.RUSAGE_SELF)
    invocation_cpu = time.process_time() - invocation_start
    prior_manifest_path = output / "manifest.json"
    prior_invocations = []
    prior_peak = 0
    if prior_manifest_path.exists():
        prior_manifest = json.loads(prior_manifest_path.read_text(encoding="utf-8"))
        prior_invocations = list(prior_manifest.get("invocations", []))
        prior_peak = int(prior_manifest.get("max_rss_kib", 0))
    invocations = prior_invocations + [{
        "new_cases": len(selected),
        "cpu_seconds": invocation_cpu,
        "max_rss_kib": usage.ru_maxrss,
    }]
    manifest = {
        "schema": 1,
        "expected_cases": len(records),
        "checked_cases": len(completed),
        "complete": len(completed) == len(records),
        "cumulative_charged_units": cumulative_units,
        "cumulative_case_cpu_seconds": cumulative_cpu,
        "total_invocation_cpu_seconds": sum(float(item["cpu_seconds"]) for item in invocations),
        "max_rss_kib": max(prior_peak, usage.ru_maxrss),
        "invocations": invocations,
        "limits": {
            **limits,
            "campaign_unit_cap": CAMPAIGN_UNIT_CAP,
            "campaign_cpu_cap_seconds": CAMPAIGN_CPU_CAP,
            "oracle_state_cap": args.oracle_state_cap,
            "oracle_cpu_cap_seconds": args.oracle_cpu_cap,
        },
    }
    write_json(output / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
