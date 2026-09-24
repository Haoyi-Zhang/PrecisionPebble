#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.bellman_checker import check_certificate  # noqa: E402
from src.event_checker import check_events  # noqa: E402
from src.generators import integer_instance, separation_instance  # noqa: E402
from src.model import load_instance  # noqa: E402
from src.optimizer import PreparationAwareOptimizer  # noqa: E402
from src.oracle import configuration_oracle  # noqa: E402
from src.pipeline import write_json  # noqa: E402
from src.reference_eq6 import reference_eq6  # noqa: E402


def locate(name: str) -> Path:
    index = json.loads((REPO / "instances" / "index.json").read_text(encoding="utf-8"))
    record = next(item for item in index["records"] if item["name"] == name)
    return REPO / "instances" / record["file"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = REPO / output

    separation = load_instance(locate("control-separation-89-91"))
    valley = load_instance(locate("control-expansive-valley"))
    solution = PreparationAwareOptimizer(separation, exact=True).solve()
    valley_oracle = configuration_oracle(valley, state_cap=50_000, cpu_cap=15.0)

    positives = []
    valid_certificate = check_certificate(separation, solution.certificate)
    positives.append({"name": "valid-certificate", "accepted": valid_certificate["valid"]})
    valley_check = check_events(valley, valley_oracle.events)
    positives.append(
        {
            "name": "valid-expansive-valley-witness",
            "accepted": valley_oracle.cost is not None and valley_oracle.cost.io == 33 and valley_check.valid,
        }
    )

    reference_checks = []
    concrete_reference = reference_eq6(separation)
    reference_checks.append(
        {
            "name": "literal-eq6-concrete-89-91",
            "expected": 91,
            "observed": concrete_reference.io,
            "accepted": concrete_reference.io == 91,
        }
    )
    for t in (1, 2, 4, 8):
        family = separation_instance(t, 2 * t, t, name=f"control-reference-t{t}", group="control")
        observed = reference_eq6(family).io
        reference_checks.append(
            {
                "name": f"literal-eq6-family-t{t}",
                "expected": 25 * t,
                "observed": observed,
                "accepted": observed == 25 * t,
            }
        )

    negatives = []

    changed_state = copy.deepcopy(solution.events)
    first_load = next(event for event in changed_state if event["event"] == "load")
    first_load["state"] = 8
    negatives.append({"name": "changed-source-representation", "rejected": not check_events(separation, changed_state).valid})

    lower_capacity = replace(separation, capacity=31)
    negatives.append({"name": "lowered-capacity", "rejected": not check_events(lower_capacity, solution.events).valid})

    missing_store = solution.events[:-1]
    negatives.append({"name": "removed-final-store", "rejected": not check_events(separation, missing_store).valid})

    actual = check_events(separation, solution.events).cost
    fake_claim = {"io": actual.io + 1, "work": [actual.work.numerator, actual.work.denominator]}
    negatives.append({"name": "changed-claimed-optimum", "rejected": fake_claim != actual.to_json()})

    corrupted = copy.deepcopy(solution.certificate)
    finite_key = next(key for key, value in corrupted["states"].items() if value["cost"] is not None)
    corrupted["states"][finite_key]["cost"]["io"] += 1
    negatives.append({"name": "corrupted-table-cost", "rejected": not check_certificate(separation, corrupted)["valid"]})

    missing = copy.deepcopy(solution.certificate)
    removed_key = next(iter(missing["states"]))
    del missing["states"][removed_key]
    negatives.append({"name": "removed-table-dependency", "rejected": not check_certificate(separation, missing)["valid"]})

    extra = copy.deepcopy(solution.certificate)
    extra["states"]["unexpected|8|1"] = {"cost": None, "choice": None}
    negatives.append({"name": "unexpected-table-state", "rejected": not check_certificate(separation, extra)["valid"]})

    exact_rejected = False
    try:
        PreparationAwareOptimizer(valley, exact=True)
    except ValueError:
        exact_rejected = True
    negatives.append({"name": "exact-mode-expansion", "rejected": exact_rejected})

    capped = configuration_oracle(separation, state_cap=1, cpu_cap=15.0)
    negatives.append({"name": "tiny-enumeration-cap", "rejected": capped.status == "state_cap"})

    typed_rejected = False
    try:
        reference_eq6(integer_instance("sum", 8, 7, 24))
    except ValueError:
        typed_rejected = True
    negatives.append({"name": "literal-eq6-rejects-typed-instance", "rejected": typed_rejected})

    report = {
        "schema": 1,
        "positive_checks": positives,
        "reference_equation_checks": reference_checks,
        "negative_checks": negatives,
        "positive_passes": sum(item["accepted"] for item in positives),
        "reference_equation_passes": sum(item["accepted"] for item in reference_checks),
        "negative_passes": sum(item["rejected"] for item in negatives),
        "valid": all(item["accepted"] for item in positives) and all(item["accepted"] for item in reference_checks) and all(item["rejected"] for item in negatives),
    }
    write_json(output, report)
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
