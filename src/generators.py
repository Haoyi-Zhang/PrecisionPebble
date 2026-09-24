from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from typing import Any, Iterable

from .model import STATES, Instance, make_instance

Shape = tuple["Shape", ...]


def _weights_constant(value: int) -> dict[str, int]:
    return {str(state): int(value) for state in STATES}


def _weights_length(length: int) -> dict[str, int]:
    return {str(state): length * (state // 8) for state in STATES}


def _weights_affine(h: int, a: int) -> dict[str, int]:
    return {str(state): h + a * (state // 8) for state in STATES}


def _recipe(name: str, inputs: Iterable[int], output: int, work: int | Fraction = 0, semantic: dict[str, Any] | None = None) -> dict[str, Any]:
    work_value = Fraction(work)
    return {
        "name": name,
        "inputs": list(inputs),
        "output": output,
        "work": [work_value.numerator, work_value.denominator],
        "semantic": semantic or {},
    }


def motzkin_shapes(size: int) -> list[Shape]:
    """All ordered rooted shapes with node arity 0, 1, or 2."""
    if size == 1:
        return [()]
    result: list[Shape] = []
    for child in motzkin_shapes(size - 1):
        result.append((child,))
    for left_size in range(1, size - 1):
        right_size = size - 1 - left_size
        for left in motzkin_shapes(left_size):
            for right in motzkin_shapes(right_size):
                result.append((left, right))
    return result


def canonical_shape(size: int, variant: int = 0) -> Shape:
    shapes = motzkin_shapes(size)
    return shapes[variant % len(shapes)]


def separation_instance(t: int, x: int | None = None, r: int | None = None, *, name: str | None = None, group: str = "separation") -> Instance:
    x = 2 * t if x is None else x
    r = t if r is None else r
    if t < 1 or x < 2 * t or not (1 <= r <= t):
        raise ValueError("separation parameters require t>=1, x>=2t, and 1<=r<=t")
    state = 64
    nodes: dict[str, dict[str, Any]] = {
        "sa": {"kind": "source", "weights": _weights_constant(4 * x - t), "source_states": [state]},
        "sb1": {"kind": "source", "weights": _weights_constant(x), "source_states": [state]},
        "sb2": {"kind": "source", "weights": _weights_constant(2 * x), "source_states": [state]},
        "sc1": {"kind": "source", "weights": _weights_constant(x), "source_states": [state]},
        "sc2": {"kind": "source", "weights": _weights_constant(x + t), "source_states": [state]},
        "A": {
            "kind": "op",
            "weights": _weights_constant(t),
            "operands": ["sa"],
            "recipes": [_recipe("shrink-A", [state], state)],
        },
        "b": {
            "kind": "op",
            "weights": _weights_constant(x),
            "operands": ["sb1", "sb2"],
            "recipes": [_recipe("combine-b", [state, state], state)],
        },
        "c": {
            "kind": "op",
            "weights": _weights_constant(x),
            "operands": ["sc1", "sc2"],
            "recipes": [_recipe("combine-c", [state, state], state)],
        },
        "d": {
            "kind": "op",
            "weights": _weights_constant(t),
            "operands": ["b", "c"],
            "recipes": [_recipe("reduce-d", [state, state], state)],
        },
        "z": {
            "kind": "op",
            "weights": _weights_constant(r),
            "operands": ["A", "d"],
            "recipes": [_recipe("root", [state, state], state)],
        },
    }
    return make_instance(
        name=name or f"separation-t{t}",
        group=group,
        capacity=4 * x,
        root="z",
        root_states=[state],
        nodes=nodes,
        metadata={
            "family": "separation",
            "t": t,
            "x": x,
            "r": r,
            "expected_prepared_io": 11 * x + r,
            "expected_contiguous_io": 11 * x + r + 2 * t,
            "compulsory_floor": 9 * x + r,
        },
    )


def valley_instance(*, name: str = "control-expansive-valley") -> Instance:
    state = 64
    nodes: dict[str, dict[str, Any]] = {}
    for side in ("l", "r"):
        nodes[f"s{side}"] = {"kind": "source", "weights": _weights_constant(16), "source_states": [state]}
        nodes[f"m{side}"] = {
            "kind": "op",
            "weights": _weights_constant(1),
            "operands": [f"s{side}"],
            "recipes": [_recipe(f"shrink-{side}", [state], state)],
        }
        nodes[f"f{side}"] = {
            "kind": "op",
            "weights": _weights_constant(8),
            "operands": [f"m{side}"],
            "recipes": [_recipe(f"expand-{side}", [state], state)],
        }
    nodes["z"] = {
        "kind": "op",
        "weights": _weights_constant(1),
        "operands": ["fl", "fr"],
        "recipes": [_recipe("join", [state, state], state)],
    }
    return make_instance(
        name=name,
        group="control",
        capacity=18,
        root="z",
        root_states=[state],
        nodes=nodes,
        metadata={
            "family": "expansive-valley",
            "expected_oracle_io": 33,
            "expected_prepared_policy_io": 35,
            "expected_contiguous_io": 49,
            "compulsory_floor": 33,
        },
    )


def hardness_instance(values: list[int], *, name: str, scaled: bool = True) -> Instance:
    if len(values) < 2 or any(value <= 0 for value in values):
        raise ValueError("hardness values must be positive and contain at least two entries")
    total = sum(values)
    if total % 2:
        raise ValueError("hardness construction requires even total")
    n = len(values)
    c1 = 3 * total // 2 + 1
    m = c1 + 1
    c2 = (n + 1) * m + 3 * total // 2 + 1
    k = c2 + 1
    b = 2 * k + c2
    l_size = b - c1
    h_size = b - c2
    scale = 8 if scaled else 1
    nodes: dict[str, dict[str, Any]] = {}
    finals: list[str] = []
    for index, item in enumerate(values):
        ls = f"L{index}"
        middle = f"m{index}"
        hs = f"H{index}"
        final = f"f{index}"
        if scaled:
            nodes[ls] = {"kind": "source", "weights": _weights_affine(0, l_size), "source_states": [64]}
            nodes[hs] = {"kind": "source", "weights": _weights_affine(0, h_size), "source_states": [64]}
            nodes[middle] = {
                "kind": "op",
                "weights": _weights_affine(0, 8 * item),
                "operands": [ls],
                "recipes": [
                    _recipe(f"low-{index}", [64], 8),
                    _recipe(f"high-{index}", [64], 16),
                ],
            }
            nodes[final] = {
                "kind": "op",
                "weights": _weights_affine(8 * m, 8 * item),
                "operands": [middle, hs],
                "recipes": [
                    _recipe(f"finish-low-{index}", [8, 64], 16),
                    _recipe(f"finish-high-{index}", [16, 64], 8),
                ],
            }
        else:
            # A fixed-state structural control with the same unscaled sizes.
            nodes[ls] = {"kind": "source", "weights": _weights_constant(l_size), "source_states": [64]}
            nodes[hs] = {"kind": "source", "weights": _weights_constant(h_size), "source_states": [64]}
            nodes[middle] = {
                "kind": "op",
                "weights": _weights_constant(item),
                "operands": [ls],
                "recipes": [_recipe(f"middle-{index}", [64], 64)],
            }
            nodes[final] = {
                "kind": "op",
                "weights": _weights_constant(m + 2 * item),
                "operands": [middle, hs],
                "recipes": [_recipe(f"finish-{index}", [64, 64], 64)],
            }
        finals.append(final)

    ls = "Ls"
    middle = "ms"
    hs = "Hs"
    final = "fs"
    if scaled:
        nodes[ls] = {"kind": "source", "weights": _weights_affine(0, l_size), "source_states": [64]}
        nodes[hs] = {"kind": "source", "weights": _weights_affine(0, h_size), "source_states": [64]}
        nodes[middle] = {
            "kind": "op",
            "weights": _weights_affine(0, 8),
            "operands": [ls],
            "recipes": [_recipe("sentinel-middle", [64], 8)],
        }
        nodes[final] = {
            "kind": "op",
            "weights": _weights_affine(0, 8 * m),
            "operands": [middle, hs],
            "recipes": [_recipe("sentinel-final", [8, 64], 8)],
        }
        comb_state = 32
        comb_weights = _weights_affine(0, 2 * k)
    else:
        nodes[ls] = {"kind": "source", "weights": _weights_constant(l_size), "source_states": [64]}
        nodes[hs] = {"kind": "source", "weights": _weights_constant(h_size), "source_states": [64]}
        nodes[middle] = {
            "kind": "op",
            "weights": _weights_constant(1),
            "operands": [ls],
            "recipes": [_recipe("sentinel-middle", [64], 64)],
        }
        nodes[final] = {
            "kind": "op",
            "weights": _weights_constant(m),
            "operands": [middle, hs],
            "recipes": [_recipe("sentinel-final", [64, 64], 64)],
        }
        comb_state = 64
        comb_weights = _weights_constant(k)
    finals.append(final)

    current = finals[0]
    current_state = 8 if scaled else 64
    for index, next_final in enumerate(finals[1:]):
        comb_id = f"c{index}"
        right_state = 8 if (scaled and next_final == "fs") else (8 if scaled else 64)
        # Ordinary finalizers can be either 8 or 16. Give the comb recipes for both.
        if scaled:
            if index == 0:
                left_options = [8, 16]
            else:
                left_options = [32]
            right_options = [8] if next_final == "fs" else [8, 16]
            recipes = [
                _recipe(f"comb-{index}-{left}-{right}", [left, right], comb_state)
                for left, right in product(left_options, right_options)
            ]
        else:
            recipes = [_recipe(f"comb-{index}", [64, 64], 64)]
        nodes[comb_id] = {
            "kind": "op",
            "weights": comb_weights,
            "operands": [current, next_final],
            "recipes": recipes,
        }
        current = comb_id
        current_state = comb_state

    floor = (n + 1) * (l_size + h_size) + k
    has_partition = any(
        sum(values[index] for index in range(n) if mask & (1 << index)) == total // 2
        for mask in range(1 << n)
    )
    return make_instance(
        name=name,
        group="hardness",
        capacity=scale * b,
        root=current,
        root_states=[comb_state],
        nodes=nodes,
        metadata={
            "family": "partition-floor",
            "values": values,
            "scaled": scaled,
            "has_partition": has_partition,
            "constants": {"S": total, "C1": c1, "M": m, "C2": c2, "K": k, "B": b, "L": l_size, "H": h_size},
            "compulsory_floor": scale * floor,
        },
    )


def _generic_instance(shape: Shape, profile: int, capacity: int, *, name: str, group: str) -> Instance:
    nodes: dict[str, dict[str, Any]] = {}
    next_id = 0

    @dataclass
    class Built:
        node_id: str
        length: int
        fixed_weight: int

    def build(item: Shape) -> Built:
        nonlocal next_id
        child_results = [build(child) for child in item]
        node_id = f"v{next_id}"
        next_id += 1
        if not child_results:
            if profile == 0:
                weight = 1
                nodes[node_id] = {"kind": "source", "weights": _weights_constant(weight), "source_states": [64]}
                return Built(node_id, 1, weight)
            if profile == 1:
                weight = 2 + (next_id % 3)
                nodes[node_id] = {"kind": "source", "weights": _weights_constant(weight), "source_states": [64]}
                return Built(node_id, 1, weight)
            length = 4 + 2 * (next_id % 3)
            source_states = [32, 64] if profile == 2 else [16, 32]
            nodes[node_id] = {"kind": "source", "weights": _weights_length(length), "source_states": source_states}
            return Built(node_id, length, length * min(source_states) // 8)

        operands = [child.node_id for child in child_results]
        if profile == 0:
            weight = 1
            nodes[node_id] = {
                "kind": "op",
                "weights": _weights_constant(weight),
                "operands": operands,
                "recipes": [_recipe(f"fixed-{node_id}", [64] * len(operands), 64, len(operands))],
            }
            return Built(node_id, 1, weight)
        if profile == 1:
            weight = max(1, min(child.fixed_weight for child in child_results) - 1)
            nodes[node_id] = {
                "kind": "op",
                "weights": _weights_constant(weight),
                "operands": operands,
                "recipes": [_recipe(f"hetero-{node_id}", [64] * len(operands), 64, weight + len(operands))],
            }
            return Built(node_id, 1, weight)

        length = max(1, min(child.length for child in child_results) // (2 if len(child_results) >= 1 else 1))
        if profile == 2:
            recipes = [
                _recipe(f"p32-{node_id}", [32] * len(operands), 32, length * (32 + len(operands))),
                _recipe(f"p64-{node_id}", [64] * len(operands), 64, length * (64 + len(operands))),
            ]
            root_min = 32
        else:
            recipes = [
                _recipe(f"p16-{node_id}", [16] * len(operands), 16, length * (16 + len(operands))),
                _recipe(f"p32to16-{node_id}", [32] * len(operands), 16, length * (24 + len(operands))),
                _recipe(f"p32-{node_id}", [32] * len(operands), 32, length * (32 + len(operands))),
            ]
            root_min = 16
        nodes[node_id] = {
            "kind": "op",
            "weights": _weights_length(length),
            "operands": operands,
            "recipes": recipes,
        }
        return Built(node_id, length, length * root_min // 8)

    built = build(shape)
    if profile in {0, 1}:
        root_states = [64]
    elif profile == 2:
        root_states = [32, 64]
    else:
        root_states = [16, 32]
    return make_instance(
        name=name,
        group=group,
        capacity=capacity,
        root=built.node_id,
        root_states=root_states,
        nodes=nodes,
        metadata={"family": "structural", "profile": profile, "shape": repr(shape)},
    )


def small_grid_instances() -> list[Instance]:
    shapes: list[Shape] = []
    for size in range(2, 6):
        shapes.extend(motzkin_shapes(size))
    assert len(shapes) == 16
    instances: list[Instance] = []
    for shape_index, shape in enumerate(shapes):
        for profile in range(4):
            for capacity in (8, 16, 32, 64):
                instances.append(
                    _generic_instance(
                        shape,
                        profile,
                        capacity,
                        name=f"small-s{shape_index:02d}-p{profile}-b{capacity}",
                        group="small",
                    )
                )
    return instances


def extended_instances() -> list[Instance]:
    shapes = motzkin_shapes(7)[:8]
    instances: list[Instance] = []
    for shape_index, shape in enumerate(shapes):
        for profile in (2, 3):
            instances.append(
                _generic_instance(
                    shape,
                    profile,
                    48,
                    name=f"extended-s{shape_index:02d}-p{profile}",
                    group="extended",
                )
            )
    return instances


def branchy_shape(size: int, variant: int) -> Shape:
    if size <= 1:
        return ()
    if size == 2:
        return ((),)
    if variant % 3 == 0:
        return ((), branchy_shape(size - 2, variant + 1))
    if variant % 3 == 1 and size >= 4:
        left_size = max(1, size // 3)
        right_size = size - 1 - left_size
        return (branchy_shape(left_size, variant + 1), branchy_shape(right_size, variant + 2))
    return (branchy_shape(size - 1, variant + 1),)


def scaling_instances() -> list[Instance]:
    instances: list[Instance] = []
    sizes = (8, 12, 16, 24, 32, 40, 48, 64)
    for index, size in enumerate(sizes):
        shape = branchy_shape(size, index)
        settings = (
            (1, min(1024, max(12, size * 2))),
            (2, min(1024, max(24, size * 3))),
            (3, min(1024, max(16, size * 2))),
        )
        for setting_index, (profile, capacity) in enumerate(settings):
            instances.append(
                _generic_instance(
                    shape,
                    profile,
                    capacity,
                    name=f"scaling-n{size:02d}-q{setting_index}",
                    group="scaling",
                )
            )
    return instances


def integer_instance(family: str, groups: int, bound: int, capacity_multiplier: int) -> Instance:
    if family not in {"sum", "dot", "abs"}:
        raise ValueError(f"unknown integer family {family}")
    if groups not in {2, 4, 8} or bound not in {7, 127} or capacity_multiplier not in {17, 24, 32}:
        raise ValueError("integer parameters are outside the frozen grid")
    length = groups
    capacity = capacity_multiplier * length
    nodes: dict[str, dict[str, Any]] = {}
    values: list[tuple[str, int, tuple[int, int]]] = []
    source_count = groups if family == "sum" else 2 * groups
    for source_index in range(source_count):
        node_id = f"s{source_index}"
        nodes[node_id] = {
            "kind": "source",
            "weights": _weights_length(length),
            "source_states": [64],
            "interval": [-bound, bound],
            "semantic": {"kind": "source", "index": source_index, "length": length, "interval": [-bound, bound]},
        }
    if family == "sum":
        for source_index in range(groups):
            values.append((f"s{source_index}", length, (-bound, bound)))
    else:
        for pair_index in range(groups):
            left = f"s{2 * pair_index}"
            right = f"s{2 * pair_index + 1}"
            node_id = f"e{pair_index}"
            if family == "dot":
                candidates = (-bound * bound, bound * bound)
                output_interval = (-bound * bound, bound * bound)
                operation = "product"
                k = lambda p: p * p
            else:
                output_interval = (0, 2 * bound)
                operation = "absdiff"
                k = lambda p: 2 * p
            recipes = []
            for output_state in STATES:
                lower, upper = output_interval
                if lower >= -(2 ** (output_state - 1)) and upper <= 2 ** (output_state - 1) - 1:
                    work = length * (k(64) + abs(64 - output_state))
                    recipes.append(
                        _recipe(
                            f"{operation}-64-to-{output_state}",
                            [64, 64],
                            output_state,
                            work,
                            {"kind": operation},
                        )
                    )
            nodes[node_id] = {
                "kind": "op",
                "weights": _weights_length(length),
                "operands": [left, right],
                "recipes": recipes,
                "semantic": {"kind": operation, "length": length, "interval": list(output_interval)},
            }
            values.append((node_id, length, output_interval))

    level = 0
    while len(values) > 1:
        if len(values) % 2:
            raise AssertionError("group counts are powers of two")
        next_values: list[tuple[str, int, tuple[int, int]]] = []
        for pair_index in range(0, len(values), 2):
            left_id, input_length, left_interval = values[pair_index]
            right_id, right_length, right_interval = values[pair_index + 1]
            if input_length != right_length or input_length % 2:
                raise AssertionError("invalid reduction extents")
            output_length = input_length // 2
            lower = 2 * (left_interval[0] + right_interval[0])
            upper = 2 * (left_interval[1] + right_interval[1])
            output_interval = (lower, upper)
            node_id = f"r{level}_{pair_index // 2}"
            recipes = []
            for input_state in STATES:
                for output_state in STATES:
                    if output_state > 2 * input_state:
                        continue
                    if lower < -(2 ** (output_state - 1)) or upper > 2 ** (output_state - 1) - 1:
                        continue
                    work = output_length * (3 * input_state + abs(input_state - output_state))
                    recipes.append(
                        _recipe(
                            f"reduce-{input_state}-to-{output_state}",
                            [input_state, input_state],
                            output_state,
                            work,
                            {"kind": "reduce"},
                        )
                    )
            nodes[node_id] = {
                "kind": "op",
                "weights": _weights_length(output_length),
                "operands": [left_id, right_id],
                "recipes": recipes,
                "semantic": {"kind": "reduce", "length": output_length, "interval": [lower, upper]},
            }
            next_values.append((node_id, output_length, output_interval))
        values = next_values
        level += 1
    root, root_length, root_interval = values[0]
    assert root_length == 1
    root_states = [
        state
        for state in STATES
        if root_interval[0] >= -(2 ** (state - 1)) and root_interval[1] <= 2 ** (state - 1) - 1
    ]
    return make_instance(
        name=f"integer-{family}-g{groups}-a{bound}-b{capacity_multiplier}",
        group="integer",
        capacity=capacity,
        root=root,
        root_states=root_states,
        nodes=nodes,
        metadata={
            "family": f"integer-{family}",
            "operator_family": family,
            "groups": groups,
            "source_length": length,
            "bound": bound,
            "capacity_multiplier": capacity_multiplier,
            "semantic_patterns": ["zero", "positive", "negative", "alternating", "pseudorandom-9137"],
        },
    )


def fixed64_projection(instance: Instance) -> Instance:
    nodes: dict[str, dict[str, Any]] = {}
    for node_id in instance.order:
        node = instance.node(node_id)
        if node.kind == "source":
            raw: dict[str, Any] = {
                "kind": "source",
                "weights": {str(state): value for state, value in node.weights.items()},
                "source_states": [64] if 64 in node.source_states else [],
                "semantic": node.semantic,
            }
            if node.interval is not None:
                raw["interval"] = list(node.interval)
            nodes[node_id] = raw
        else:
            recipes = [recipe.to_json() for recipe in node.recipes if recipe.output == 64 and all(state == 64 for state in recipe.inputs)]
            nodes[node_id] = {
                "kind": "op",
                "weights": {str(state): value for state, value in node.weights.items()},
                "operands": list(node.operands),
                "recipes": recipes or [_recipe(f"unavailable-{node_id}", [64] * len(node.operands), 64, 0)],
                "semantic": node.semantic,
            }
            if not recipes:
                # Preserve a structurally valid but impossible fixed-64 instance by assigning
                # a footprint that can never fit. This is only used when a true 64-bit recipe
                # does not exist; the retained integer grid always has one.
                nodes[node_id]["weights"] = {str(state): instance.capacity + 1 for state in STATES}
    return make_instance(
        name=f"{instance.name}-fixed64",
        group=instance.group,
        capacity=instance.capacity,
        root=instance.root,
        root_states=[64],
        nodes=nodes,
        metadata={**instance.metadata, "projection": "fixed64"},
    )


def integer_instances() -> list[Instance]:
    return [
        integer_instance(family, groups, bound, multiplier)
        for family in ("sum", "dot", "abs")
        for groups in (2, 4, 8)
        for bound in (7, 127)
        for multiplier in (17, 24, 32)
    ]


def control_instances() -> list[Instance]:
    separation = separation_instance(1, 8, 1, name="control-separation-89-91", group="control")
    valley = valley_instance()
    unit_shape = branchy_shape(9, 1)
    unit = _generic_instance(unit_shape, 0, 4, name="control-unit-weight", group="control")
    failed_shape = branchy_shape(12, 2)
    failed = _generic_instance(failed_shape, 2, 64, name="control-failed-separation", group="control")
    return [separation, valley, unit, failed]


def all_campaign_instances() -> list[tuple[Instance, dict[str, bool]]]:
    result: list[tuple[Instance, dict[str, bool]]] = []
    for instance in small_grid_instances():
        result.append((instance, {"oracle": True, "certificate": True, "semantic": False, "exact": True}))
    for instance in extended_instances():
        result.append((instance, {"oracle": True, "certificate": True, "semantic": False, "exact": True}))
    for exponent in range(8):
        instance = separation_instance(2**exponent)
        result.append((instance, {"oracle": True, "certificate": True, "semantic": False, "exact": True}))
    for instance in control_instances():
        is_valley = instance.metadata.get("family") == "expansive-valley"
        result.append((instance, {"oracle": True, "certificate": not is_valley, "semantic": False, "exact": not is_valley}))
    yes = hardness_instance([1, 1], name="hardness-yes-scaled", scaled=True)
    no = hardness_instance([1, 3], name="hardness-no-scaled", scaled=True)
    for instance in (yes, no):
        result.append((instance, {"oracle": True, "certificate": False, "semantic": False, "exact": False}))
    for instance in scaling_instances():
        result.append((instance, {"oracle": False, "certificate": True, "semantic": False, "exact": True}))
    for instance in integer_instances():
        result.append((instance, {"oracle": False, "certificate": True, "semantic": True, "exact": True}))
    assert len(result) == 364
    return result
