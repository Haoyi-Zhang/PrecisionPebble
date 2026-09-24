#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from src.pipeline import write_json  # noqa: E402

GROUP_ORDER = ["small", "extended", "separation", "control", "hardness", "scaling", "integer"]


def load_results(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("complete"):
        raise SystemExit("summary requires a complete campaign")
    cases = [json.loads(item.read_text(encoding="utf-8")) for item in sorted((path / "cases").glob("*.json"))]
    if len(cases) != manifest["expected_cases"] or any(case["status"] != "checked" for case in cases):
        raise SystemExit("campaign records are missing or failed")
    return cases, manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    results_path = Path(args.results)
    output = Path(args.output)
    if not results_path.is_absolute():
        results_path = REPO / results_path
    if not output.is_absolute():
        output = REPO / output
    output.mkdir(parents=True, exist_ok=True)
    cases, manifest = load_results(results_path)

    coverage = []
    for group in GROUP_ORDER:
        selected = [case for case in cases if case["group"] == group]
        coverage.append(
            {
                "group": group,
                "cases": len(selected),
                "max_nodes": max(case["instance"]["nodes"] for case in selected),
                "oracles": sum(case["oracle"] is not None for case in selected),
                "certificates": sum(case["prepared"]["certificate_check"] is not None for case in selected),
                "charged_units": sum(case["metrics"]["charged_units"] for case in selected),
            }
        )

    integer_cases = [case for case in cases if case["group"] == "integer"]
    typed_feasible = sum(case["prepared"]["cost"] is not None for case in integer_cases)
    fixed_feasible = sum(case["fixed64"]["cost"] is not None for case in integer_cases)
    jointly_feasible = [case for case in integer_cases if case["prepared"]["cost"] and case["fixed64"]["cost"]]
    integer_summary = {
        "total": len(integer_cases),
        "typed_feasible": typed_feasible,
        "fixed64_feasible": fixed_feasible,
        "typed_only": sum(case["prepared"]["cost"] is not None and case["fixed64"]["cost"] is None for case in integer_cases),
        "infeasible_both": sum(case["prepared"]["cost"] is None and case["fixed64"]["cost"] is None for case in integer_cases),
        "typed_lower_io_joint": sum(case["prepared"]["cost"]["io"] < case["fixed64"]["cost"]["io"] for case in jointly_feasible),
        "jointly_feasible": len(jointly_feasible),
        "preparation_lower_than_contiguous": sum(
            bool(case["prepared"]["cost"] and case["contiguous"]["cost"] and case["prepared"]["cost"]["io"] < case["contiguous"]["cost"]["io"])
            for case in integer_cases
        ),
        "typed_semantic_patterns": sum(len(case["semantic"]["patterns"]) for case in integer_cases if case["semantic"]["valid"]),
        "fixed64_semantic_patterns": sum(len(case["fixed64"]["semantic"]["patterns"]) for case in integer_cases if case["fixed64"]["semantic"]["valid"]),
    }

    target_points = []
    for family in ("sum", "dot", "abs"):
        for multiplier in (17, 24, 32):
            name = f"integer-{family}-g8-a7-b{multiplier}"
            case = next(item for item in cases if item["name"] == name)
            target_points.append(
                {
                    "family": family,
                    "capacity": case["instance"]["capacity"],
                    "typed_io": None if case["prepared"]["cost"] is None else case["prepared"]["cost"]["io"],
                    "fixed64_io": None if case["fixed64"]["cost"] is None else case["fixed64"]["cost"]["io"],
                    "contiguous_io": None if case["contiguous"]["cost"] is None else case["contiguous"]["cost"]["io"],
                }
            )

    summary = {
        "schema": 1,
        "campaign": {
            "cases": len(cases),
            "oracles": sum(case["oracle"] is not None for case in cases),
            "oracle_complete": sum(case["oracle"] is not None and case["oracle"]["status"] == "complete" for case in cases),
            "contractive_oracle_agreements": sum(
                case["oracle"] is not None
                and case["prepared"]["exact_mode"]
                and case["oracle"]["cost"] == case["prepared"]["cost"]
                for case in cases
            ),
            "certificates": sum(case["prepared"]["certificate_check"] is not None for case in cases),
            "charged_units": sum(case["metrics"]["charged_units"] for case in cases),
            "optimizer_states": sum(case["metrics"]["optimizer_states"] for case in cases),
            "certificate_alternatives": sum(case["metrics"]["certificate_alternatives"] for case in cases),
            "oracle_states": sum(case["metrics"]["oracle_states"] for case in cases),
            "max_optimizer_states": max(case["metrics"]["optimizer_states"] for case in cases),
            "max_oracle_states": max(case["metrics"]["oracle_states"] for case in cases),
            "max_nodes": max(case["instance"]["nodes"] for case in cases),
            "max_recipes": max(case["instance"]["recipes"] for case in cases),
            "max_capacity": max(case["instance"]["capacity"] for case in cases),
            "case_cpu_seconds": sum(case["metrics"]["cpu_seconds"] for case in cases),
            "manifest": manifest,
        },
        "coverage": coverage,
        "integer": integer_summary,
        "integer_figure_points": target_points,
        "scaling": {
            "feasible": sum(case["prepared"]["cost"] is not None for case in cases if case["group"] == "scaling"),
            "infeasible": sum(case["prepared"]["cost"] is None for case in cases if case["group"] == "scaling"),
        },
        "preparation_improvements_by_group": {
            group: sum(
                bool(case["prepared"]["cost"] and case["contiguous"]["cost"] and case["prepared"]["cost"]["io"] < case["contiguous"]["cost"]["io"])
                for case in cases
                if case["group"] == group
            )
            for group in GROUP_ORDER
        },
    }
    write_json(output / "summary.json", summary)

    with (output / "coverage.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(coverage[0]))
        writer.writeheader()
        writer.writerows(coverage)
    with (output / "integer-figure.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(target_points[0]))
        writer.writeheader()
        writer.writerows(target_points)
    with (output / "integer-cases.csv").open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["name", "family", "groups", "bound", "capacity", "typed_io", "fixed64_io", "contiguous_io", "typed_feasible", "fixed64_feasible"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case in integer_cases:
            meta = case["instance"]["metadata"]
            writer.writerow(
                {
                    "name": case["name"],
                    "family": meta["operator_family"],
                    "groups": meta["groups"],
                    "bound": meta["bound"],
                    "capacity": case["instance"]["capacity"],
                    "typed_io": "" if case["prepared"]["cost"] is None else case["prepared"]["cost"]["io"],
                    "fixed64_io": "" if case["fixed64"]["cost"] is None else case["fixed64"]["cost"]["io"],
                    "contiguous_io": "" if case["contiguous"]["cost"] is None else case["contiguous"]["cost"]["io"],
                    "typed_feasible": case["prepared"]["cost"] is not None,
                    "fixed64_feasible": case["fixed64"]["cost"] is not None,
                }
            )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
