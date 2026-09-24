#!/usr/bin/env python3
"""Check the published complete-child recurrence on retained controls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.contiguous import contiguous_policy  # noqa: E402
from src.event_checker import check_events  # noqa: E402
from src.generators import separation_instance  # noqa: E402
from src.optimizer import PreparationAwareOptimizer  # noqa: E402
from src.pipeline import write_json  # noqa: E402
from src.reference_eq6 import reference_eq6  # noqa: E402


def _case(t: int, x: int, r: int, name: str) -> dict[str, object]:
    instance = separation_instance(t, x, r, name=name, group="reference-equation")
    optimum = PreparationAwareOptimizer(instance, exact=True).solve()
    event_check = check_events(instance, optimum.events)
    contiguous = contiguous_policy(instance)[0]
    literal = reference_eq6(instance)
    expected_optimum = 11 * x + r
    expected_equation = expected_optimum + 2 * t
    valid = (
        optimum.cost is not None
        and optimum.cost.io == expected_optimum
        and event_check.valid
        and event_check.cost == optimum.cost
        and contiguous is not None
        and contiguous.io == expected_equation
        and literal.io == expected_equation
    )
    return {
        "name": name,
        "parameters": {"t": t, "x": x, "r": r, "capacity": 4 * x},
        "expected": {"preparation_aware_io": expected_optimum, "eq6_io": expected_equation},
        "observed": {
            "preparation_aware_io": None if optimum.cost is None else optimum.cost.io,
            "complete_child_policy_io": None if contiguous is None else contiguous.io,
            "literal_eq6": literal.to_json(),
            "event_witness_valid": event_check.valid,
            "event_witness_peak": event_check.peak,
        },
        "valid": valid,
    }


def build_report() -> dict[str, object]:
    cases = [_case(1, 8, 1, "concrete-89-91")]
    for t in (1, 2, 4, 8):
        cases.append(_case(t, 2 * t, t, f"family-t{t}"))
    return {
        "schema": 1,
        "equation": "Bhattacharjee et al. (SPAA 2025), Eq. (6) plus Eq. (7) root store",
        "doi": "10.1145/3694906.3743342",
        "cases": cases,
        "passes": sum(bool(case["valid"]) for case in cases),
        "valid": all(bool(case["valid"]) for case in cases),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = REPO / output
    report = build_report()
    write_json(output, report)
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
