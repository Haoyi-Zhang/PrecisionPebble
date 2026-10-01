from __future__ import annotations

from typing import Any

from .bellman_checker import check_certificate
from .cost import Cost, cost_from_json, cost_to_json
from .event_checker import EventCheck, check_events
from .model import Instance


def check_solution_claim(
    instance: Instance,
    claimed_cost_json: Any,
    events: list[dict[str, Any]],
    certificate: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate a claimed terminal cost against executable evidence.

    A finite claim must equal the cost recomputed from the normalized event trace.
    When a Bellman certificate is supplied, its separately recomputed terminal
    cost must agree as well. An infeasibility claim may carry no execution trace and
    must be accompanied by an infeasible certificate when a certificate is supplied.
    """

    errors: list[str] = []
    claimed: Cost | None = None
    try:
        claimed = cost_from_json(claimed_cost_json)
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"malformed claimed cost: {exc}")

    event_check: EventCheck | None = None
    if claimed is None:
        if claimed_cost_json is not None:
            # Parsing failed above; do not reinterpret malformed data as infeasible.
            pass
        elif events:
            errors.append("infeasibility claim unexpectedly carries events")
    else:
        event_check = check_events(instance, events)
        if not event_check.valid:
            errors.append(f"event trace rejected: {event_check.error}")
        elif event_check.cost != claimed:
            errors.append(
                f"claimed/event cost mismatch: claimed={cost_to_json(claimed)}, "
                f"recomputed={event_check.cost.to_json()}"
            )

    certificate_check: dict[str, Any] | None = None
    if certificate is not None:
        certificate_check = check_certificate(instance, certificate)
        if not certificate_check["valid"]:
            errors.append(f"Bellman certificate rejected: {certificate_check['error']}")
        elif certificate_check["terminal_cost"] != claimed_cost_json:
            errors.append(
                "claimed/certificate terminal-cost mismatch: "
                f"claimed={claimed_cost_json}, recomputed={certificate_check['terminal_cost']}"
            )

    return {
        "valid": not errors,
        "errors": errors,
        "claimed_cost": claimed_cost_json,
        "event_check": None if event_check is None else event_check.to_json(),
        "certificate_check": certificate_check,
    }
