from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

STATES = (8, 16, 32, 64)


@dataclass(frozen=True)
class Recipe:
    name: str
    inputs: tuple[int, ...]
    output: int
    work: Fraction
    semantic: dict[str, Any]

    @staticmethod
    def from_json(raw: dict[str, Any]) -> "Recipe":
        num, den = raw.get("work", [0, 1])
        if int(den) <= 0:
            raise ValueError("recipe work denominator must be positive")
        work = Fraction(int(num), int(den))
        if work < 0:
            raise ValueError("recipe work must be nonnegative")
        return Recipe(
            name=str(raw["name"]),
            inputs=tuple(int(item) for item in raw["inputs"]),
            output=int(raw["output"]),
            work=work,
            semantic=dict(raw.get("semantic", {})),
        )

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
    kind = str(raw["kind"])
    if kind not in {"source", "op"}:
        raise ValueError(f"node {node_id!r} has invalid kind {kind!r}")
    weights = {int(state): int(value) for state, value in raw["weights"].items()}
    if set(weights) != set(states):
        raise ValueError(f"node {node_id!r} must define every declared state allocation")
    if any(value <= 0 for value in weights.values()):
        raise ValueError(f"node {node_id!r} has a nonpositive allocation")
    if kind == "source":
        source_states = tuple(int(state) for state in raw["source_states"])
        if not source_states:
            raise ValueError(f"source {node_id!r} has no initial representation")
        operands: tuple[str, ...] = ()
        recipes: tuple[Recipe, ...] = ()
        interval_raw = raw.get("interval")
        interval = None if interval_raw is None else (int(interval_raw[0]), int(interval_raw[1]))
        if interval is not None and interval[0] > interval[1]:
            raise ValueError(f"source {node_id!r} has an invalid interval")
    else:
        operands = tuple(str(item) for item in raw["operands"])
        if not operands:
            raise ValueError(f"operator {node_id!r} must have at least one operand")
        source_states = ()
        recipes = tuple(Recipe.from_json(recipe) for recipe in raw["recipes"])
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
        semantic=dict(raw.get("semantic", {})),
    )


def load_instance(path: str | Path) -> Instance:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    states = tuple(int(state) for state in raw["states"])
    if states != STATES:
        raise ValueError(f"the retained artifact requires states {STATES}, got {states}")
    nodes = {str(node_id): _parse_node(str(node_id), node, states) for node_id, node in raw["nodes"].items()}
    instance = Instance(
        schema=int(raw["schema"]),
        name=str(raw["name"]),
        group=str(raw["group"]),
        capacity=int(raw["capacity"]),
        states=states,
        root=str(raw["root"]),
        root_states=tuple(int(state) for state in raw["root_states"]),
        nodes=nodes,
        metadata=dict(raw.get("metadata", {})),
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
    raw = {
        "schema": 1,
        "name": name,
        "group": group,
        "capacity": capacity,
        "states": list(STATES),
        "root": root,
        "root_states": list(root_states),
        "nodes": nodes,
        "metadata": metadata or {},
    }
    parsed = Instance(
        schema=1,
        name=name,
        group=group,
        capacity=capacity,
        states=STATES,
        root=root,
        root_states=tuple(int(value) for value in root_states),
        nodes={node_id: _parse_node(node_id, node, STATES) for node_id, node in nodes.items()},
        metadata=dict(metadata or {}),
    )
    validate_instance(parsed)
    return parsed
