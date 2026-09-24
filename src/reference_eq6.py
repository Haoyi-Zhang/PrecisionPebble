"""Independent, literal cost implementation of Bhattacharjee et al. Eq. (6).

This module is intentionally separate from :mod:`src.contiguous` and the
preparation-aware optimizer.  It transcribes the fixed-node-weight k-ary tree
recurrence in Eq. (6) and adds the sink-store term from Eq. (7) of:

  A. Bhattacharjee et al., "Dataflow-Specific Algorithms for
  Resource-Constrained Scheduling and Memory Design," SPAA 2025,
  https://doi.org/10.1145/3694906.3743342.

The implementation accepts only instances that collapse to one fixed weight
and one fixed recipe/state per node.  It does not import or reuse published
source code; it is a clean-room transcription of the displayed equation.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations, product
from typing import Any

from .model import Instance


@dataclass(frozen=True)
class ReferenceEquationResult:
    """Result and audit counters for the literal recurrence."""

    io: int | None
    root_state: int
    table_states: int
    recurrence_candidates: int

    def to_json(self) -> dict[str, Any]:
        return {
            "io": self.io,
            "root_state": self.root_state,
            "table_states": self.table_states,
            "recurrence_candidates": self.recurrence_candidates,
        }


def _validate_fixed_weight_instance(instance: Instance) -> int:
    """Return the unique root state or reject a typed/choice-dependent input."""

    if len(instance.root_states) != 1:
        raise ValueError("Eq. (6) check requires exactly one allowed root state")
    root_state = instance.root_states[0]

    required: dict[str, int] = {}

    def visit(node_id: str, state: int) -> None:
        previous = required.get(node_id)
        if previous is not None:
            if previous != state:
                raise ValueError(f"node {node_id!r} is required in multiple states")
            return
        required[node_id] = state
        node = instance.node(node_id)
        if len(set(node.weights.values())) != 1:
            raise ValueError(f"node {node_id!r} does not have a fixed weight")
        if node.kind == "source":
            if node.source_states != (state,):
                raise ValueError(f"source {node_id!r} does not have one fixed initial state")
            return
        if len(node.recipes) != 1:
            raise ValueError(f"operator {node_id!r} does not have one fixed recipe")
        recipe = node.recipes[0]
        if recipe.output != state:
            raise ValueError(f"operator {node_id!r} fixed recipe does not produce state {state}")
        for child_id, child_state in zip(node.operands, recipe.inputs):
            visit(child_id, child_state)

    visit(instance.root, root_state)
    if set(required) != set(instance.nodes):
        raise ValueError("fixed-state traversal did not cover the complete tree")
    return root_state


def reference_eq6(instance: Instance) -> ReferenceEquationResult:
    """Evaluate the displayed Eq. (6), plus the root-store term in Eq. (7).

    ``delta=1`` retains a completed child root in fast memory.  ``delta=0``
    stores, deletes, and later reloads that root, contributing ``2*w``.  Each
    child subtree is evaluated as a complete recursive subproblem under the
    residual budget after previously retained child roots are subtracted.
    """

    root_state = _validate_fixed_weight_instance(instance)

    def weight(node_id: str) -> int:
        values = set(instance.node(node_id).weights.values())
        if len(values) != 1:  # defensive; validation above should catch this
            raise ValueError(f"node {node_id!r} does not have a fixed weight")
        return next(iter(values))

    memo: dict[tuple[str, int], int | None] = {}
    candidate_count = 0

    def value(node_id: str, budget: int) -> int | None:
        nonlocal candidate_count
        key = (node_id, budget)
        if key in memo:
            return memo[key]
        if budget < 0:
            memo[key] = None
            return None

        node = instance.node(node_id)
        node_weight = weight(node_id)
        if node.kind == "source":
            answer = node_weight if node_weight <= budget else None
            memo[key] = answer
            return answer

        child_weights = {child_id: weight(child_id) for child_id in node.operands}
        if node_weight + sum(child_weights.values()) > budget:
            memo[key] = None
            return None

        best: int | None = None
        for order in permutations(node.operands):
            # Eq. (6) ranges over all delta in {0,1}^k, including source roots.
            for keep_bits in product((0, 1), repeat=len(order)):
                candidate_count += 1
                held = 0
                total = 0
                feasible = True
                for child_id, keep in zip(order, keep_bits):
                    child_cost = value(child_id, budget - held)
                    if child_cost is None:
                        feasible = False
                        break
                    total += child_cost
                    if keep:
                        held += child_weights[child_id]
                    else:
                        total += 2 * child_weights[child_id]
                if feasible and (best is None or total < best):
                    best = total
        memo[key] = best
        return best

    base = value(instance.root, instance.capacity)
    terminal = None if base is None else base + weight(instance.root)
    return ReferenceEquationResult(
        io=terminal,
        root_state=root_state,
        table_states=len(memo),
        recurrence_candidates=candidate_count,
    )
