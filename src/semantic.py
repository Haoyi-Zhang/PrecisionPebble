from __future__ import annotations

import random
from typing import Any

from .model import Instance


def _fits_signed(value: int, width: int) -> bool:
    return -(2 ** (width - 1)) <= value <= 2 ** (width - 1) - 1


def _source_arrays(instance: Instance, pattern: str) -> dict[str, list[int]]:
    bound = int(instance.metadata["bound"])
    length = int(instance.metadata["source_length"])
    source_ids = sorted(instance.sources, key=lambda item: int(item[1:]))
    result: dict[str, list[int]] = {}
    rng = random.Random(9137)
    for source_index, source_id in enumerate(source_ids):
        if pattern == "zero":
            values = [0] * length
        elif pattern == "positive":
            values = [bound] * length
        elif pattern == "negative":
            values = [-bound] * length
        elif pattern == "alternating":
            values = [bound if (source_index * length + offset) % 2 == 0 else -bound for offset in range(length)]
        elif pattern == "pseudorandom-9137":
            values = [rng.randint(-bound, bound) for _ in range(length)]
        else:
            raise ValueError(f"unknown semantic pattern {pattern}")
        result[source_id] = values
    return result


def _apply(kind: str, left: list[int], right: list[int] | None = None) -> list[int]:
    if kind == "product":
        assert right is not None and len(left) == len(right)
        return [a * b for a, b in zip(left, right)]
    if kind == "absdiff":
        assert right is not None and len(left) == len(right)
        return [abs(a - b) for a, b in zip(left, right)]
    if kind == "reduce":
        assert right is not None and len(left) == len(right) and len(left) % 2 == 0
        return [
            left[index] + left[index + 1] + right[index] + right[index + 1]
            for index in range(0, len(left), 2)
        ]
    raise ValueError(f"unknown semantic operator {kind}")


def check_integer_semantics(instance: Instance, events: list[dict[str, Any]]) -> dict[str, Any]:
    if not str(instance.metadata.get("family", "")).startswith("integer-"):
        return {"applicable": False, "valid": True, "patterns": []}
    patterns = list(instance.metadata["semantic_patterns"])
    family = str(instance.metadata["operator_family"])
    pattern_results: list[dict[str, Any]] = []
    for pattern in patterns:
        sources = _source_arrays(instance, pattern)
        values: dict[str, list[int]] = dict(sources)
        states: dict[str, int] = {}
        error: str | None = None
        for event in events:
            event_type = event["event"]
            node_id = event["node"]
            if event_type == "load" and instance.node(node_id).kind == "source":
                states[node_id] = int(event["state"])
            elif event_type == "compute":
                node = instance.node(node_id)
                recipe_name = str(event["recipe"])
                recipe = next(recipe for recipe in node.recipes if recipe.name == recipe_name)
                operands = [values[child] for child in node.operands]
                kind = str(node.semantic.get("kind"))
                try:
                    result = _apply(kind, operands[0], operands[1] if len(operands) > 1 else None)
                except (AssertionError, ValueError) as exc:
                    error = f"{node_id}: {exc}"
                    break
                expected_length = int(node.semantic["length"])
                if len(result) != expected_length:
                    error = f"{node_id}: length {len(result)} != {expected_length}"
                    break
                lower, upper = (int(value) for value in node.semantic["interval"])
                if any(value < lower or value > upper for value in result):
                    error = f"{node_id}: propagated interval violation"
                    break
                if any(not _fits_signed(value, recipe.output) for value in result):
                    error = f"{node_id}: signed-width overflow at {recipe.output} bits"
                    break
                values[node_id] = result
                states[node_id] = recipe.output
        if error is None:
            source_ids = sorted(instance.sources, key=lambda item: int(item[1:]))
            if family == "sum":
                expected = sum(sum(sources[source_id]) for source_id in source_ids)
            elif family == "dot":
                expected = 0
                for pair in range(0, len(source_ids), 2):
                    expected += sum(a * b for a, b in zip(sources[source_ids[pair]], sources[source_ids[pair + 1]]))
            elif family == "abs":
                expected = 0
                for pair in range(0, len(source_ids), 2):
                    expected += sum(abs(a - b) for a, b in zip(sources[source_ids[pair]], sources[source_ids[pair + 1]]))
            else:
                error = f"unknown family {family}"
                expected = 0
            if error is None:
                root_value = values.get(instance.root)
                if root_value != [expected]:
                    error = f"root value {root_value} != direct specification {[expected]}"
        pattern_results.append({"pattern": pattern, "valid": error is None, "error": error})
    return {
        "applicable": True,
        "valid": all(item["valid"] for item in pattern_results),
        "patterns": pattern_results,
    }
