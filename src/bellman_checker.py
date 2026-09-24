from __future__ import annotations

from fractions import Fraction
from itertools import permutations, product
from typing import Any

from .cost import Cost, MaybeCost, cost_from_json, cost_to_json
from .model import Instance


def check_certificate(instance: Instance, certificate: dict[str, Any]) -> dict[str, Any]:
    """Recompute every Bellman state using explicit cut masks, not the optimizer."""

    exact_mode = bool(certificate.get("exact_mode", True))
    if exact_mode and not instance.contractive:
        return {"valid": False, "error": "exact certificate supplied for a noncontractive instance"}
    memo: dict[tuple[str, int, int], MaybeCost] = {}
    alternatives = 0

    def value(node_id: str, state: int, budget: int) -> MaybeCost:
        nonlocal alternatives
        key = (node_id, state, budget)
        if key in memo:
            return memo[key]
        node = instance.node(node_id)
        if budget < 0:
            memo[key] = None
            return None
        if node.kind == "source":
            result = Cost(node.weight(state), Fraction(0, 1)) if state in node.source_states and node.weight(state) <= budget else None
            memo[key] = result
            return result

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
                    alternatives += 1
                    held = 0
                    total = Cost.zero()
                    feasible = True
                    for operand_index, cut in zip(order, cut_mask):
                        child_id = node.operands[operand_index]
                        child_state = recipe.inputs[operand_index]
                        child_weight = instance.node(child_id).weight(child_state)
                        if cut:
                            child_cost = value(child_id, child_state, instance.capacity)
                            if child_cost is not None:
                                child_cost = child_cost + Cost(2 * child_weight, Fraction(0, 1))
                        else:
                            child_cost = value(child_id, child_state, budget - held)
                        if child_cost is None:
                            feasible = False
                            break
                        total = total + child_cost
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

    supplied_states = certificate.get("states", {})
    expected_states = {
        f"{node_id}|{state}|{budget}": cost_to_json(value_cost)
        for (node_id, state, budget), value_cost in sorted(memo.items())
    }
    errors: list[str] = []
    if set(supplied_states) != set(expected_states):
        missing = sorted(set(expected_states) - set(supplied_states))
        extra = sorted(set(supplied_states) - set(expected_states))
        if missing:
            errors.append(f"missing state records: {missing[:5]}{' ...' if len(missing) > 5 else ''}")
        if extra:
            errors.append(f"unexpected state records: {extra[:5]}{' ...' if len(extra) > 5 else ''}")
    for key in sorted(set(supplied_states) & set(expected_states)):
        supplied_cost = supplied_states[key].get("cost")
        if supplied_cost != expected_states[key]:
            errors.append(f"state {key} cost mismatch: supplied={supplied_cost}, expected={expected_states[key]}")
            if len(errors) >= 10:
                break
    if certificate.get("terminal_cost") != cost_to_json(terminal):
        errors.append(
            f"terminal cost mismatch: supplied={certificate.get('terminal_cost')}, expected={cost_to_json(terminal)}"
        )
    if certificate.get("root_state") != root_state:
        errors.append(f"root-state mismatch: supplied={certificate.get('root_state')}, expected={root_state}")

    return {
        "valid": not errors,
        "error": None if not errors else "; ".join(errors),
        "checked_states": len(expected_states),
        "checked_alternatives": alternatives,
        "terminal_cost": cost_to_json(terminal),
        "root_state": root_state,
    }
