from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .bellman_checker import check_certificate
from .contiguous import contiguous_policy
from .cost import cost_to_json
from .event_checker import check_events
from .generators import fixed64_projection
from .model import load_instance
from .optimizer import PreparationAwareOptimizer
from .oracle import configuration_oracle
from .semantic import check_integer_semantics


def evaluate_case(repo: Path, record: dict[str, Any], *, oracle_state_cap: int = 50_000, oracle_cpu_cap: float = 15.0) -> dict[str, Any]:
    started = time.process_time()
    instance = load_instance(repo / "instances" / record["file"])
    errors: list[str] = []

    optimizer = PreparationAwareOptimizer(instance, exact=bool(record["exact"]))
    solution = optimizer.solve()
    event_check = check_events(instance, solution.events)
    if solution.cost is None:
        if solution.events:
            errors.append("infeasible solution unexpectedly emitted events")
    else:
        if not event_check.valid:
            errors.append(f"event checker rejected optimizer witness: {event_check.error}")
        elif event_check.cost != solution.cost:
            errors.append(f"optimizer/event cost mismatch: {solution.cost} != {event_check.cost}")

    certificate_check: dict[str, Any] | None = None
    if record["certificate"]:
        certificate_check = check_certificate(instance, solution.certificate)
        if not certificate_check["valid"]:
            errors.append(f"Bellman certificate rejected: {certificate_check['error']}")
        elif certificate_check["terminal_cost"] != cost_to_json(solution.cost):
            errors.append("certificate terminal cost disagrees with optimizer")

    contiguous_cost, contiguous_state = contiguous_policy(instance)

    oracle_result = None
    oracle_event_check = None
    if record["oracle"]:
        oracle_result = configuration_oracle(instance, state_cap=oracle_state_cap, cpu_cap=oracle_cpu_cap)
        if oracle_result.status != "complete":
            errors.append(f"configuration oracle stopped at {oracle_result.status}")
        if oracle_result.cost is not None:
            oracle_event_check = check_events(instance, oracle_result.events)
            if not oracle_event_check.valid:
                errors.append(f"oracle witness rejected: {oracle_event_check.error}")
            elif oracle_event_check.cost != oracle_result.cost:
                errors.append("oracle/event cost mismatch")
        if record["exact"] and oracle_result.status == "complete" and oracle_result.cost != solution.cost:
            errors.append(f"exact recurrence/oracle mismatch: {solution.cost} != {oracle_result.cost}")

    semantic = {"applicable": False, "valid": True, "patterns": []}
    fixed64: dict[str, Any] | None = None
    if record["semantic"]:
        if solution.cost is not None:
            semantic = check_integer_semantics(instance, solution.events)
            if not semantic["valid"]:
                errors.append("integer semantic checker rejected a typed schedule")
        fixed_instance = fixed64_projection(instance)
        fixed_solution = PreparationAwareOptimizer(fixed_instance, exact=True).solve()
        fixed_event_check = check_events(fixed_instance, fixed_solution.events)
        fixed_semantic = {"applicable": False, "valid": True, "patterns": []}
        if fixed_solution.cost is not None:
            if not fixed_event_check.valid or fixed_event_check.cost != fixed_solution.cost:
                errors.append("fixed-64 witness check failed")
            fixed_semantic = check_integer_semantics(fixed_instance, fixed_solution.events)
            if not fixed_semantic["valid"]:
                errors.append("integer semantic checker rejected a fixed-64 schedule")
        fixed64 = {
            "cost": cost_to_json(fixed_solution.cost),
            "root_state": fixed_solution.root_state,
            "events": fixed_solution.events,
            "event_check": fixed_event_check.to_json(),
            "semantic": fixed_semantic,
            "optimizer_states": len(fixed_solution.certificate["states"]),
        }

    metadata = instance.metadata
    family = metadata.get("family")
    if family == "separation":
        expected_prepared = int(metadata["expected_prepared_io"])
        expected_contiguous = int(metadata["expected_contiguous_io"])
        if solution.cost is None or solution.cost.io != expected_prepared:
            errors.append(f"separation prepared value is not {expected_prepared}")
        if contiguous_cost is None or contiguous_cost.io != expected_contiguous:
            errors.append(f"separation contiguous value is not {expected_contiguous}")
    if family == "expansive-valley":
        expected = (
            int(metadata["expected_oracle_io"]),
            int(metadata["expected_prepared_policy_io"]),
            int(metadata["expected_contiguous_io"]),
        )
        observed = (
            None if oracle_result is None or oracle_result.cost is None else oracle_result.cost.io,
            None if solution.cost is None else solution.cost.io,
            None if contiguous_cost is None else contiguous_cost.io,
        )
        if observed != expected:
            errors.append(f"valley discriminator {observed} != {expected}")
    if family == "partition-floor" and oracle_result is not None and oracle_result.status == "complete":
        floor = int(metadata["compulsory_floor"])
        if bool(metadata["has_partition"]):
            if oracle_result.cost is None or oracle_result.cost.io != floor:
                errors.append(f"yes floor instance did not attain {floor}")
        else:
            if oracle_result.cost is None or oracle_result.cost.io <= floor:
                errors.append(f"no floor instance did not exceed {floor}")

    optimizer_states = len(solution.certificate["states"])
    certificate_alternatives = 0 if certificate_check is None else int(certificate_check["checked_alternatives"])
    oracle_states = 0 if oracle_result is None else int(oracle_result.discovered_states)
    event_units = len(solution.events)
    semantic_units = 0
    if semantic["applicable"]:
        semantic_units = len(semantic["patterns"]) * max(1, len(instance.internal))
    fixed_units = 0 if fixed64 is None else int(fixed64["optimizer_states"])
    charged_units = optimizer_states + certificate_alternatives + oracle_states + event_units + semantic_units + fixed_units

    elapsed = time.process_time() - started
    result = {
        "schema": 1,
        "name": instance.name,
        "group": instance.group,
        "instance_file": record["file"],
        "status": "checked" if not errors else "failed",
        "errors": errors,
        "instance": {
            "nodes": len(instance.nodes),
            "capacity": instance.capacity,
            "recipes": instance.recipe_count,
            "contractive": instance.contractive,
            "max_degree": instance.max_degree,
            "metadata": instance.metadata,
        },
        "prepared": {
            "exact_mode": bool(record["exact"]),
            "cost": cost_to_json(solution.cost),
            "root_state": solution.root_state,
            "spill_edges": [list(edge) for edge in solution.spill_edges],
            "events": solution.events,
            "event_check": event_check.to_json(),
            "certificate": solution.certificate if record["certificate"] else None,
            "certificate_check": certificate_check,
        },
        "contiguous": {"cost": cost_to_json(contiguous_cost), "root_state": contiguous_state},
        "oracle": None if oracle_result is None else oracle_result.to_json(),
        "oracle_event_check": None if oracle_event_check is None else oracle_event_check.to_json(),
        "fixed64": fixed64,
        "semantic": semantic,
        "metrics": {
            "optimizer_states": optimizer_states,
            "certificate_alternatives": certificate_alternatives,
            "oracle_states": oracle_states,
            "event_units": event_units,
            "semantic_units": semantic_units,
            "fixed64_optimizer_states": fixed_units,
            "charged_units": charged_units,
            "cpu_seconds": elapsed,
        },
    }
    return result


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=False)
        handle.write("\n")
    temporary.replace(path)
