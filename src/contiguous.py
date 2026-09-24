from __future__ import annotations

from fractions import Fraction
from itertools import permutations, product

from .cost import Cost, MaybeCost
from .model import Instance


def contiguous_policy(instance: Instance) -> tuple[MaybeCost, int | None]:
    """Literal complete-child recurrence with optional spill of completed roots."""

    memo: dict[tuple[str, int, int], MaybeCost] = {}

    def value(node_id: str, state: int, budget: int) -> MaybeCost:
        key = (node_id, state, budget)
        if key in memo:
            return memo[key]
        node = instance.node(node_id)
        if budget < 0:
            memo[key] = None
            return None
        if node.kind == "source":
            answer = Cost(node.weight(state), Fraction(0, 1)) if state in node.source_states and node.weight(state) <= budget else None
            memo[key] = answer
            return answer
        best: MaybeCost = None
        for recipe in sorted((item for item in node.recipes if item.output == state), key=lambda item: item.name):
            input_weights = [instance.node(child).weight(input_state) for child, input_state in zip(node.operands, recipe.inputs)]
            if node.weight(state) + sum(input_weights) > budget:
                continue
            for order in permutations(range(len(node.operands))):
                cut_options = [
                    (False, True) if instance.node(node.operands[index]).kind == "op" else (False,)
                    for index in order
                ]
                for cut_mask in product(*cut_options):
                    held = 0
                    total = Cost.zero()
                    feasible = True
                    for operand_index, spill in zip(order, cut_mask):
                        child_id = node.operands[operand_index]
                        child_state = recipe.inputs[operand_index]
                        child_weight = instance.node(child_id).weight(child_state)
                        child_cost = value(child_id, child_state, budget - held)
                        if child_cost is None:
                            feasible = False
                            break
                        total = total + child_cost
                        if spill:
                            total = total + Cost(2 * child_weight, Fraction(0, 1))
                        else:
                            held += child_weight
                    if feasible:
                        total = total + Cost(0, recipe.work)
                        if best is None or total < best:
                            best = total
        memo[key] = best
        return best

    terminal: MaybeCost = None
    root_state: int | None = None
    for state in sorted(instance.root_states):
        base = value(instance.root, state, instance.capacity)
        if base is None:
            continue
        candidate = base + Cost(instance.node(instance.root).weight(state), Fraction(0, 1))
        if terminal is None or candidate < terminal or (candidate == terminal and (root_state is None or state < root_state)):
            terminal = candidate
            root_state = state
    return terminal, root_state
