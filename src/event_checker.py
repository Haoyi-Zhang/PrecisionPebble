from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .cost import Cost
from .model import Instance, Recipe


@dataclass
class EventCheck:
    valid: bool
    cost: Cost
    peak: int
    error: str | None
    trace: list[dict[str, Any]]
    final_root_state: int | None

    def to_json(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "cost": self.cost.to_json(),
            "peak": self.peak,
            "error": self.error,
            "final_root_state": self.final_root_state,
            "trace": self.trace,
        }


def _recipe_by_name(instance: Instance, node_id: str, name: str) -> Recipe:
    matches = [recipe for recipe in instance.node(node_id).recipes if recipe.name == name]
    if len(matches) != 1:
        raise ValueError(f"node {node_id!r} has no unique recipe {name!r}")
    return matches[0]


def check_events(instance: Instance, events: list[dict[str, Any]]) -> EventCheck:
    red: dict[str, int] = {}
    blue: dict[str, int] = {}
    produced: dict[str, int] = {}
    source_loaded: set[str] = set()
    cost = Cost.zero()
    peak = 0
    trace: list[dict[str, Any]] = []

    def resident() -> int:
        return sum(instance.node(node_id).weight(state) for node_id, state in red.items())

    def fail(index: int, message: str) -> EventCheck:
        return EventCheck(False, cost, peak, f"event {index}: {message}", trace, blue.get(instance.root))

    for index, raw_event in enumerate(events):
        try:
            event_type = str(raw_event["event"])
            before = resident()
            added_io = 0
            added_work = Fraction(0, 1)
            event_peak = before
            if event_type == "load":
                node_id = str(raw_event["node"])
                state = int(raw_event["state"])
                node = instance.node(node_id)
                if node_id in red:
                    return fail(index, f"load of already resident value {node_id}")
                if node.kind == "source":
                    if node_id in source_loaded:
                        return fail(index, f"source {node_id} is loaded more than once")
                    if state not in node.source_states:
                        return fail(index, f"source {node_id} has no slow-memory state {state}")
                    source_loaded.add(node_id)
                    produced[node_id] = state
                else:
                    if blue.get(node_id) != state:
                        return fail(index, f"internal value {node_id} is not stored in state {state}")
                    if produced.get(node_id) != state:
                        return fail(index, f"stored identity for {node_id} is inconsistent")
                size = node.weight(state)
                event_peak = before + size
                if event_peak > instance.capacity:
                    return fail(index, f"load exceeds capacity: {event_peak}>{instance.capacity}")
                red[node_id] = state
                added_io = size
                cost = cost + Cost(size, Fraction(0, 1))
            elif event_type == "store":
                node_id = str(raw_event["node"])
                node = instance.node(node_id)
                if node.kind == "source":
                    return fail(index, f"source {node_id} need not be stored")
                if node_id not in red:
                    return fail(index, f"store of nonresident value {node_id}")
                state = red[node_id]
                if node_id in blue:
                    return fail(index, f"duplicate store of {node_id}")
                blue[node_id] = state
                size = node.weight(state)
                added_io = size
                cost = cost + Cost(size, Fraction(0, 1))
            elif event_type == "delete":
                node_id = str(raw_event["node"])
                if node_id not in red:
                    return fail(index, f"delete of nonresident value {node_id}")
                del red[node_id]
            elif event_type == "compute":
                node_id = str(raw_event["node"])
                node = instance.node(node_id)
                if node.kind != "op":
                    return fail(index, f"cannot compute source {node_id}")
                if node_id in produced:
                    return fail(index, f"operator {node_id} is recomputed")
                recipe = _recipe_by_name(instance, node_id, str(raw_event["recipe"]))
                if int(raw_event["output"]) != recipe.output:
                    return fail(index, f"event output disagrees with recipe for {node_id}")
                for child_id, required_state in zip(node.operands, recipe.inputs):
                    if red.get(child_id) != required_state:
                        return fail(
                            index,
                            f"recipe {recipe.name} for {node_id} requires {child_id}@{required_state}, "
                            f"found {red.get(child_id)}",
                        )
                output_size = node.weight(recipe.output)
                event_peak = before + output_size
                if event_peak > instance.capacity:
                    return fail(index, f"compute exceeds capacity: {event_peak}>{instance.capacity}")
                for child_id in node.operands:
                    del red[child_id]
                red[node_id] = recipe.output
                produced[node_id] = recipe.output
                added_work = recipe.work
                cost = cost + Cost(0, recipe.work)
            else:
                return fail(index, f"unknown event type {event_type!r}")

            after = resident()
            peak = max(peak, event_peak, after)
            trace.append(
                {
                    "index": index,
                    "event": dict(raw_event),
                    "resident_before": before,
                    "event_peak": event_peak,
                    "resident_after": after,
                    "added_io": added_io,
                    "added_work": [added_work.numerator, added_work.denominator],
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            return fail(index, str(exc))

    root_state = blue.get(instance.root)
    if root_state is None:
        return EventCheck(False, cost, peak, "root is not stored at termination", trace, None)
    if root_state not in instance.root_states:
        return EventCheck(False, cost, peak, "stored root state is not allowed", trace, root_state)
    if produced.get(instance.root) != root_state:
        return EventCheck(False, cost, peak, "stored root identity is inconsistent", trace, root_state)
    return EventCheck(True, cost, peak, None, trace, root_state)
