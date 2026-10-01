from __future__ import annotations

import json
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

STATES = (8, 16, 32, 64)
_CANONICAL_NONNEGATIVE_INT = re.compile(r"0|[1-9][0-9]*")


def require_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    """Return a JSON integer without accepting bools or truncating floats."""

    if type(value) is not int:  # bool is deliberately rejected.
        raise ValueError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        qualifier = "positive" if minimum == 1 else f"at least {minimum}"
        raise ValueError(f"{label} must be {qualifier}")
    return value


def require_int_sequence(value: Any, label: str, *, minimum: int | None = None) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return tuple(require_int(item, f"{label}[{index}]", minimum=minimum) for index, item in enumerate(value))


def require_fraction_pair(value: Any, label: str, *, nonnegative: bool = False) -> Fraction:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must be a two-integer JSON array")
    numerator = require_int(value[0], f"{label} numerator")
    denominator = require_int(value[1], f"{label} denominator", minimum=1)
    result = Fraction(numerator, denominator)
    if nonnegative and result < 0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def require_state_key(value: Any, label: str) -> int:
    if not isinstance(value, str) or _CANONICAL_NONNEGATIVE_INT.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical integer string")
    return int(value)


@dataclass(frozen=True)
class Recipe:
    name: str
    inputs: tuple[int, ...]
    output: int
    work: Fraction
    semantic: dict[str, Any]

    @staticmethod
    def from_json(raw: dict[str, Any]) -> "Recipe":
        if not isinstance(raw, dict):
            raise ValueError("recipe must be a JSON object")
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("recipe name must be a nonempty string")
        inputs = require_int_sequence(raw.get("inputs"), f"recipe {name!r} inputs", minimum=1)
        output = require_int(raw.get("output"), f"recipe {name!r} output", minimum=1)
        work = require_fraction_pair(raw.get("work", [0, 1]), f"recipe {name!r} work", nonnegative=True)
        semantic = raw.get("semantic", {})
        if not isinstance(semantic, dict):
            raise ValueError(f"recipe {name!r} semantic field must be an object")
        return Recipe(name=name, inputs=inputs, output=output, work=work, semantic=dict(semantic))

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "inputs": list(self.inputs),
            "output": self.output,
            "work": [self.work.numerator, self.work.denominator],
            "semantic": self.semantic,
        }


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    operands: tuple[str, ...]
    weights: dict[int, int]
    source_states: tuple[int, ...]
    recipes: tuple[Recipe, ...]
    interval: tuple[int, int] | None
    semantic: dict[str, Any]

    def weight(self, state: int) -> int:
        try:
            return self.weights[state]
        except KeyError as exc:
            raise ValueError(f"node {self.id!r} has no allocation for state {state}") from exc


@dataclass(frozen=True)
class Instance:
    schema: int
    name: str
    group: str
    capacity: int
    states: tuple[int, ...]
    root: str
    root_states: tuple[int, ...]
    nodes: dict[str, Node]
    metadata: dict[str, Any]

    def node(self, node_id: str) -> Node:
        return self.nodes[node_id]

    @property
    def order(self) -> tuple[str, ...]:
        """Postorder, deterministic in operand order."""
        result: list[str] = []
        seen: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in seen:
                return
            seen.add(node_id)
            for child in self.nodes[node_id].operands:
                visit(child)
            result.append(node_id)

        visit(self.root)
        return tuple(result)

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(node_id for node_id in self.order if self.nodes[node_id].kind == "source")

    @property
    def internal(self) -> tuple[str, ...]:
        return tuple(node_id for node_id in self.order if self.nodes[node_id].kind == "op")

    def is_recipe_contractive(self, node_id: str, recipe: Recipe) -> bool:
        node = self.nodes[node_id]
        output_weight = node.weight(recipe.output)
        return all(output_weight <= self.nodes[child].weight(state) for child, state in zip(node.operands, recipe.inputs))

    @property
    def contractive(self) -> bool:
        return all(
            self.is_recipe_contractive(node_id, recipe)
            for node_id in self.internal
            for recipe in self.nodes[node_id].recipes
        )

    @property
    def max_degree(self) -> int:
        return max((len(node.operands) for node in self.nodes.values()), default=0)

    @property
    def recipe_count(self) -> int:
        return sum(len(node.recipes) for node in self.nodes.values())

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema": self.schema,
            "name": self.name,
            "group": self.group,
            "capacity": self.capacity,
            "states": list(self.states),
            "root": self.root,
            "root_states": list(self.root_states),
            "metadata": self.metadata,
            "nodes": {},
        }
        for node_id in self.order:
            node = self.nodes[node_id]
            raw: dict[str, Any] = {
                "kind": node.kind,
                "weights": {str(state): value for state, value in sorted(node.weights.items())},
                "semantic": node.semantic,
            }
            if node.kind == "source":
                raw["source_states"] = list(node.source_states)
                if node.interval is not None:
                    raw["interval"] = list(node.interval)
            else:
                raw["operands"] = list(node.operands)
                raw["recipes"] = [recipe.to_json() for recipe in node.recipes]
            data["nodes"][node_id] = raw
        return data


def _parse_node(node_id: str, raw: dict[str, Any], states: tuple[int, ...]) -> Node:
    if not isinstance(raw, dict):
        raise ValueError(f"node {node_id!r} must be a JSON object")
    kind = raw.get("kind")
    if kind not in {"source", "op"}:
        raise ValueError(f"node {node_id!r} has invalid kind {kind!r}")
    raw_weights = raw.get("weights")
    if not isinstance(raw_weights, dict):
        raise ValueError(f"node {node_id!r} weights must be an object")
    weights: dict[int, int] = {}
    for raw_state, raw_value in raw_weights.items():
        state = require_state_key(raw_state, f"node {node_id!r} allocation-state key")
        if state in weights:
            raise ValueError(f"node {node_id!r} repeats allocation state {state}")
        try:
            weights[state] = require_int(raw_value, f"node {node_id!r} allocation at state {state}", minimum=1)
        except ValueError as exc:
            if type(raw_value) is int and raw_value <= 0:
                raise ValueError(f"node {node_id!r} has nonpositive allocation at state {state}") from exc
            raise
    if set(weights) != set(states):
        raise ValueError(f"node {node_id!r} must define every declared state allocation")

    semantic = raw.get("semantic", {})
    if not isinstance(semantic, dict):
        raise ValueError(f"node {node_id!r} semantic field must be an object")

    if kind == "source":
        source_states = require_int_sequence(raw.get("source_states"), f"source {node_id!r} states", minimum=1)
        if not source_states:
            raise ValueError(f"source {node_id!r} has no initial representation")
        operands: tuple[str, ...] = ()
        recipes: tuple[Recipe, ...] = ()
        interval_raw = raw.get("interval")
        if interval_raw is None:
            interval = None
        else:
            interval_values = require_int_sequence(interval_raw, f"source {node_id!r} interval")
            if len(interval_values) != 2:
                raise ValueError(f"source {node_id!r} interval must have two integers")
            interval = (interval_values[0], interval_values[1])
        if interval is not None and interval[0] > interval[1]:
            raise ValueError(f"source {node_id!r} has an invalid interval")
    else:
        raw_operands = raw.get("operands")
        if not isinstance(raw_operands, list) or any(not isinstance(item, str) or not item for item in raw_operands):
            raise ValueError(f"operator {node_id!r} operands must be nonempty strings")
        operands = tuple(raw_operands)
        if not operands:
            raise ValueError(f"operator {node_id!r} must have at least one operand")
        source_states = ()
        raw_recipes = raw.get("recipes")
        if not isinstance(raw_recipes, list):
            raise ValueError(f"operator {node_id!r} recipes must be a JSON array")
        recipes = tuple(Recipe.from_json(recipe) for recipe in raw_recipes)
        if not recipes:
            raise ValueError(f"operator {node_id!r} has no recipes")
        interval = None
        if any(len(recipe.inputs) != len(operands) for recipe in recipes):
            raise ValueError(f"operator {node_id!r} has a recipe with the wrong arity")

    for state in source_states:
        if state not in states:
            raise ValueError(f"node {node_id!r} uses undeclared state {state}")
    for recipe in recipes:
        if recipe.output not in states or any(state not in states for state in recipe.inputs):
            raise ValueError(f"operator {node_id!r} uses an undeclared recipe state")
    return Node(
        id=node_id,
        kind=kind,
        operands=operands,
        weights=weights,
        source_states=source_states,
        recipes=recipes,
        interval=interval,
        semantic=dict(semantic),
    )


def load_instance(path: str | Path) -> Instance:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("instance must be a JSON object")
    states = require_int_sequence(raw.get("states"), "states", minimum=1)
    if states != STATES:
        raise ValueError(f"the retained artifact requires states {STATES}, got {states}")
    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, dict) or any(not isinstance(node_id, str) or not node_id for node_id in raw_nodes):
        raise ValueError("nodes must be an object with nonempty string keys")
    nodes = {node_id: _parse_node(node_id, node, states) for node_id, node in raw_nodes.items()}
    name = raw.get("name")
    group = raw.get("group")
    root = raw.get("root")
    if not isinstance(name, str) or not name:
        raise ValueError("instance name must be a nonempty string")
    if not isinstance(group, str) or not group:
        raise ValueError("instance group must be a nonempty string")
    if not isinstance(root, str) or not root:
        raise ValueError("root must be a nonempty string")
    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")
    instance = Instance(
        schema=require_int(raw.get("schema"), "schema", minimum=1),
        name=name,
        group=group,
        capacity=require_int(raw.get("capacity"), "capacity", minimum=1),
        states=states,
        root=root,
        root_states=require_int_sequence(raw.get("root_states"), "root_states", minimum=1),
        nodes=nodes,
        metadata=dict(metadata),
    )
    validate_instance(instance)
    return instance


def dump_instance(instance: Instance, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(instance.to_json(), handle, indent=2, sort_keys=False)
        handle.write("\n")


def validate_instance(instance: Instance) -> None:
    if instance.schema != 1:
        raise ValueError(f"unsupported schema {instance.schema}")
    if instance.capacity <= 0:
        raise ValueError("capacity must be positive")
    if instance.root not in instance.nodes:
        raise ValueError("root is not a node")
    if instance.nodes[instance.root].kind != "op":
        raise ValueError("the retained campaign requires an internal root")
    if not instance.root_states or any(state not in instance.states for state in instance.root_states):
        raise ValueError("invalid root states")

    consumers: dict[str, int] = {node_id: 0 for node_id in instance.nodes}
    for node in instance.nodes.values():
        for operand in node.operands:
            if operand not in instance.nodes:
                raise ValueError(f"operator {node.id!r} references missing operand {operand!r}")
            consumers[operand] += 1
    if consumers[instance.root] != 0:
        raise ValueError("root has a consumer")
    for node_id, count in consumers.items():
        if node_id != instance.root and count != 1:
            raise ValueError(f"node {node_id!r} must have exactly one consumer, got {count}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in visiting:
            raise ValueError("cycle detected")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in instance.nodes[node_id].operands:
            walk(child)
        visiting.remove(node_id)
        visited.add(node_id)

    walk(instance.root)
    if visited != set(instance.nodes):
        extra = sorted(set(instance.nodes) - visited)
        raise ValueError(f"disconnected nodes: {extra}")

    recipe_names: set[tuple[str, str]] = set()
    for node_id in instance.internal:
        node = instance.nodes[node_id]
        for recipe in node.recipes:
            key = (node_id, recipe.name)
            if key in recipe_names:
                raise ValueError(f"duplicate recipe name {key}")
            recipe_names.add(key)
            node.weight(recipe.output)
            for child, state in zip(node.operands, recipe.inputs):
                instance.nodes[child].weight(state)


def make_instance(
    *,
    name: str,
    group: str,
    capacity: int,
    root: str,
    root_states: Iterable[int],
    nodes: dict[str, dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> Instance:
    capacity_value = require_int(capacity, "capacity", minimum=1)
    root_state_values = tuple(require_int(value, "root state", minimum=1) for value in root_states)
    parsed = Instance(
        schema=1,
        name=name,
        group=group,
        capacity=capacity_value,
        states=STATES,
        root=root,
        root_states=root_state_values,
        nodes={node_id: _parse_node(node_id, node, STATES) for node_id, node in nodes.items()},
        metadata=dict(metadata or {}),
    )
    validate_instance(parsed)
    return parsed
