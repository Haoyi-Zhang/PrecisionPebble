from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .claim_checker import check_solution_claim
from .contiguous import evaluate_contiguous_policy
from .cost import cost_to_json
from .event_checker import check_events
from .generators import fixed64_projection
from .model import load_instance
from .optimizer import PreparationAwareOptimizer
from .oracle import configuration_oracle
from .semantic import check_integer_semantics


def _semantic_node_evaluations(instance, semantic: dict[str, Any]) -> int:
    if not semantic.get("applicable"):
        return 0
    return len(semantic.get("patterns", [])) * max(1, len(instance.internal))


def evaluate_case(
    repo: Path,
    record: dict[str, Any],
    *,
    oracle_state_cap: int = 50_000,
    oracle_cpu_cap: float = 15.0,
) -> dict[str, Any]:
    started = time.process_time()
    instance = load_instance(repo / "instances" / record["file"])
    errors: list[str] = []

    optimizer = PreparationAwareOptimizer(instance, exact=bool(record["exact"]))
    solution = optimizer.solve()
    claimed_cost = cost_to_json(solution.cost)
    retained_certificate = solution.certificate if record["certificate"] else None
    solution_claim = check_solution_claim(instance, claimed_cost, solution.events, retained_certificate)
    if not solution_claim["valid"]:
        errors.extend(f"prepared claim: {message}" for message in solution_claim["errors"])
    event_check = solution_claim["event_check"]
    certificate_check = solution_claim["certificate_check"]

    contiguous_result = evaluate_contiguous_policy(instance)
    contiguous_cost = contiguous_result.cost
    contiguous_state = contiguous_result.root_state

    oracle_result = None
    oracle_event_check = None
    if record["oracle"]:
        oracle_result = configuration_oracle(instance, state_cap=oracle_state_cap, cpu_cap=oracle_cpu_cap)
        if oracle_result.status != "complete":
            errors.append(f"configuration oracle stopped at {oracle_result.status}")
        if oracle_result.cost is not None:
            checked_oracle_events = check_events(instance, oracle_result.events)
            oracle_event_check = checked_oracle_events.to_json()
            if not checked_oracle_events.valid:
                errors.append(f"oracle witness rejected: {checked_oracle_events.error}")
            elif checked_oracle_events.cost != oracle_result.cost:
                errors.append("oracle/event cost mismatch")
        if record["exact"] and oracle_result.status == "complete" and oracle_result.cost != solution.cost:
            errors.append(f"exact recurrence/oracle mismatch: {solution.cost} != {oracle_result.cost}")

    semantic = {"applicable": False, "valid": True, "patterns": []}
    fixed64: dict[str, Any] | None = None
    fixed_instance = None
    if record["semantic"]:
        if solution.cost is not None:
            semantic = check_integer_semantics(instance, solution.events)
            if not semantic["valid"]:
                errors.append("integer semantic checker rejected a typed schedule")
        fixed_instance = fixed64_projection(instance)
        fixed_solution = PreparationAwareOptimizer(fixed_instance, exact=True).solve()
        fixed_claim = check_solution_claim(
            fixed_instance,
            cost_to_json(fixed_solution.cost),
            fixed_solution.events,
            fixed_solution.certificate if fixed_solution.cost is None else None,
        )
        if not fixed_claim["valid"]:
            errors.extend(f"fixed-64 claim: {message}" for message in fixed_claim["errors"])
        fixed_semantic = {"applicable": False, "valid": True, "patterns": []}
        if fixed_solution.cost is not None:
            fixed_semantic = check_integer_semantics(fixed_instance, fixed_solution.events)
            if not fixed_semantic["valid"]:
                errors.append("integer semantic checker rejected a fixed-64 schedule")
        fixed64 = {
            "cost": cost_to_json(fixed_solution.cost),
            "root_state": fixed_solution.root_state,
            "events": fixed_solution.events,
            "event_check": fixed_claim["event_check"],
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
    oracle_discovered_states = 0 if oracle_result is None else int(oracle_result.discovered_states)
    oracle_expanded_states = 0 if oracle_result is None else int(oracle_result.expanded_states)
    prepared_event_replay_steps = 0 if event_check is None else len(event_check["trace"])
    oracle_event_replay_steps = 0 if oracle_event_check is None else len(oracle_event_check["trace"])
    typed_semantic_node_evaluations = _semantic_node_evaluations(instance, semantic)
    fixed64_optimizer_states = 0 if fixed64 is None else int(fixed64["optimizer_states"])
    fixed64_event_replay_steps = 0 if fixed64 is None or fixed64["event_check"] is None else len(fixed64["event_check"]["trace"])
    fixed64_semantic_node_evaluations = 0
    if fixed64 is not None and fixed_instance is not None:
        fixed64_semantic_node_evaluations = _semantic_node_evaluations(fixed_instance, fixed64["semantic"])

    audit_components = {
        "prepared_optimizer_states": optimizer_states,
        "prepared_certificate_alternatives": certificate_alternatives,
        "prepared_event_replay_steps": prepared_event_replay_steps,
        "contiguous_states": contiguous_result.evaluated_states,
        "contiguous_alternatives": contiguous_result.enumerated_alternatives,
        "oracle_expanded_states": oracle_expanded_states,
        "oracle_event_replay_steps": oracle_event_replay_steps,
        "typed_semantic_node_evaluations": typed_semantic_node_evaluations,
        "fixed64_optimizer_states": fixed64_optimizer_states,
        "fixed64_event_replay_steps": fixed64_event_replay_steps,
        "fixed64_semantic_node_evaluations": fixed64_semantic_node_evaluations,
    }
    audit_units = sum(audit_components.values())

    elapsed = time.process_time() - started
    result = {
        "schema": 2,
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
            "cost": claimed_cost,
            "root_state": solution.root_state,
            "spill_edges": [list(edge) for edge in solution.spill_edges],
            "events": solution.events,
            "event_check": event_check,
            "certificate": retained_certificate,
            "certificate_check": certificate_check,
            "claim_check": solution_claim,
        },
        "contiguous": {
            "cost": cost_to_json(contiguous_cost),
            "root_state": contiguous_state,
            "evaluated_states": contiguous_result.evaluated_states,
            "enumerated_alternatives": contiguous_result.enumerated_alternatives,
        },
        "oracle": None if oracle_result is None else oracle_result.to_json(),
        "oracle_event_check": oracle_event_check,
        "fixed64": fixed64,
        "semantic": semantic,
        "metrics": {
            "optimizer_states": optimizer_states,
            "certificate_alternatives": certificate_alternatives,
            "oracle_states": oracle_discovered_states,
            "oracle_expanded_states": oracle_expanded_states,
            "audit_unit_components": audit_components,
            "audit_units": audit_units,
            "case_body_cpu_seconds": elapsed,
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
