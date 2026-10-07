from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import permutations
from typing import Any

from .cost import Cost, MaybeCost, cost_to_json
from .model import Instance, Recipe


@dataclass(frozen=True)
class StateKey:
    node: str
    state: int
    budget: int

    def encode(self) -> str:
        return f"{self.node}|{self.state}|{self.budget}"


@dataclass
class SolveResult:
    cost: MaybeCost
    root_state: int | None
    events: list[dict[str, Any]]
    certificate: dict[str, Any]
    spill_edges: list[tuple[str, str]]


class PreparationAwareOptimizer:
    """Exact on contractive instances; a feasible upper-bound policy otherwise."""

    def __init__(self, instance: Instance, *, exact: bool = True):
        self.instance = instance
        self.exact = exact
        if exact and not instance.contractive:
            raise ValueError("exact mode requires every allowed recipe to be allocation-contractive")
        self._memo: dict[StateKey, MaybeCost] = {}
        self._choices: dict[StateKey, dict[str, Any] | None] = {}
        self._recipe_descriptors: dict[tuple[str, int], tuple[tuple[Recipe, tuple[int, ...], int], ...]] | None = None

    def _recipe_candidates(self, node_id: str, output_state: int) -> list[Recipe]:
        return [recipe for recipe in self.instance.node(node_id).recipes if recipe.output == output_state]

    def _descriptors(self, node_id: str, output_state: int) -> tuple[tuple[Recipe, tuple[int, ...], int], ...]:
        key = (node_id, output_state)
        cache = self._recipe_descriptors
        if cache is not None and key in cache:
            return cache[key]
        node = self.instance.node(node_id)
        descriptors = []
        for recipe in sorted(self._recipe_candidates(node_id, output_state), key=lambda item: item.name):
            weights = tuple(
                self.instance.node(child).weight(input_state)
                for child, input_state in zip(node.operands, recipe.inputs)
            )
            descriptors.append((recipe, weights, node.weight(recipe.output) + sum(weights)))
        result = tuple(descriptors)
        if cache is not None:
            cache[key] = result
        return result

    def value(self, node_id: str, state: int, budget: int) -> MaybeCost:
        key = StateKey(node_id, state, budget)
        if key in self._memo:
            return self._memo[key]
        node = self.instance.node(node_id)
        if budget < 0:
            self._memo[key] = None
            self._choices[key] = None
            return None
        if node.kind == "source":
            if state in node.source_states and node.weight(state) <= budget:
                result: MaybeCost = Cost(node.weight(state), Fraction(0, 1))
                choice: dict[str, Any] | None = {"kind": "source", "state": state}
            else:
                result = None
                choice = None
            self._memo[key] = result
            self._choices[key] = choice
            return result

        best: MaybeCost = None
        best_choice: dict[str, Any] | None = None
        best_tie: tuple[Any, ...] | None = None
        for recipe, input_weights, footprint in self._descriptors(node_id, state):
            if footprint > budget:
                continue
            for order in permutations(range(len(node.operands))):
                held = 0
                total = Cost.zero()
                child_records: list[dict[str, Any]] = []
                feasible = True
                cut_bits: list[int] = []
                for operand_index in order:
                    child_id = node.operands[operand_index]
                    child_state = recipe.inputs[operand_index]
                    child = self.instance.node(child_id)
                    child_weight = input_weights[operand_index]
                    residual = budget - held
                    direct = self.value(child_id, child_state, residual)
                    prepared: MaybeCost = None
                    if child.kind == "op":
                        base = self.value(child_id, child_state, self.instance.capacity)
                        if base is not None:
                            prepared = base + Cost(2 * child_weight, Fraction(0, 1))
                    use_cut = False
                    selected = direct
                    if prepared is not None and (selected is None or prepared < selected):
                        selected = prepared
                        use_cut = True
                    # Deterministic ties prefer an uncut edge.
                    if selected is None:
                        feasible = False
                        break
                    total = total + selected
                    child_records.append(
                        {
                            "id": child_id,
                            "operand_index": operand_index,
                            "state": child_state,
                            "budget": self.instance.capacity if use_cut else residual,
                            "residual_before": residual,
                            "cut": use_cut,
                            "weight": child_weight,
                        }
                    )
                    cut_bits.append(1 if use_cut else 0)
                    held += child_weight
                if not feasible:
                    continue
                total = total + Cost(0, recipe.work)
                tie = (
                    recipe.name,
                    tuple(node.operands[index] for index in order),
                    tuple(cut_bits),
                )
                if best is None or total < best or (total == best and (best_tie is None or tie < best_tie)):
                    best = total
                    best_tie = tie
                    best_choice = {
                        "kind": "op",
                        "recipe": recipe.name,
                        "output": recipe.output,
                        "children": child_records,
                    }
        self._memo[key] = best
        self._choices[key] = best_choice
        return best

    def solve(self) -> SolveResult:
        # Model dictionaries are mutable; allocation metadata belongs to this
        # solve only. Direct value() calls do not retain descriptor metadata.
        self._recipe_descriptors = {}
        try:
            return self._solve()
        finally:
            self._recipe_descriptors = None

    def _solve(self) -> SolveResult:
        best: MaybeCost = None
        best_state: int | None = None
        for state in sorted(self.instance.root_states):
            value = self.value(self.instance.root, state, self.instance.capacity)
            if value is None:
                continue
            terminal = value + Cost(self.instance.node(self.instance.root).weight(state), Fraction(0, 1))
            if best is None or terminal < best or (terminal == best and (best_state is None or state < best_state)):
                best = terminal
                best_state = state

        events: list[dict[str, Any]] = []
        spill_edges: list[tuple[str, str]] = []
        if best_state is not None:
            self._emit_preparations(self.instance.root, best_state, self.instance.capacity, events, spill_edges)
            self._emit_component(self.instance.root, best_state, self.instance.capacity, events)
            events.append({"event": "store", "node": self.instance.root})

        states = {
            key.encode(): {
                "cost": cost_to_json(self._memo[key]),
                "choice": self._choices[key],
            }
            for key in sorted(self._memo, key=lambda item: (item.node, item.state, item.budget))
        }
        certificate = {
            "schema": 1,
            "instance": self.instance.name,
            "exact_mode": self.exact,
            "contractive": self.instance.contractive,
            "capacity": self.instance.capacity,
            "root": self.instance.root,
            "root_state": best_state,
            "terminal_cost": cost_to_json(best),
            "states": states,
        }
        return SolveResult(
            cost=best,
            root_state=best_state,
            events=events,
            certificate=certificate,
            spill_edges=spill_edges,
        )

    def _choice(self, node_id: str, state: int, budget: int) -> dict[str, Any]:
        key = StateKey(node_id, state, budget)
        if key not in self._memo:
            self.value(node_id, state, budget)
        choice = self._choices.get(key)
        if choice is None:
            raise ValueError(f"cannot extract an infeasible state {key}")
        return choice

    def _emit_preparations(
        self,
        node_id: str,
        state: int,
        budget: int,
        events: list[dict[str, Any]],
        spill_edges: list[tuple[str, str]],
    ) -> None:
        node = self.instance.node(node_id)
        if node.kind == "source":
            return
        choice = self._choice(node_id, state, budget)
        for child_record in choice["children"]:
            child_id = str(child_record["id"])
            child_state = int(child_record["state"])
            child_budget = int(child_record["budget"])
            if bool(child_record["cut"]):
                self._emit_preparations(child_id, child_state, self.instance.capacity, events, spill_edges)
                self._emit_component(child_id, child_state, self.instance.capacity, events)
                events.append({"event": "store", "node": child_id})
                events.append({"event": "delete", "node": child_id})
                spill_edges.append((child_id, node_id))
            else:
                self._emit_preparations(child_id, child_state, child_budget, events, spill_edges)

    def _emit_component(self, node_id: str, state: int, budget: int, events: list[dict[str, Any]]) -> None:
        node = self.instance.node(node_id)
        if node.kind == "source":
            events.append({"event": "load", "node": node_id, "state": state})
            return
        choice = self._choice(node_id, state, budget)
        for child_record in choice["children"]:
            child_id = str(child_record["id"])
            child_state = int(child_record["state"])
            if bool(child_record["cut"]):
                events.append({"event": "load", "node": child_id, "state": child_state})
            else:
                self._emit_component(child_id, child_state, int(child_record["budget"]), events)
        events.append(
            {
                "event": "compute",
                "node": node_id,
                "recipe": str(choice["recipe"]),
                "output": state,
            }
        )
