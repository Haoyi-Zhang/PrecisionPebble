"""Finite current-artifact controls; no historical implementation or private path."""
from __future__ import annotations
import copy
from fractions import Fraction
from itertools import product
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.bellman_checker import check_certificate
from src.claim_checker import check_solution_claim
from src.event_checker import check_events
from src.generators import separation_instance, valley_instance
from src.model import make_instance
from src.optimizer import PreparationAwareOptimizer


def fixture(capacity=7, weight=2, degree=2, nested=False):
    def source():
        return {"kind": "source", "weights": {"8": weight, "16": weight + 1, "32": weight + 2, "64": weight + 3}, "source_states": [8, 16]}
    def operation(operands):
        recipes = []
        for states in product((8, 16), repeat=len(operands)):
            for name, work in (("z", [1, 3]), ("a", [2, 6])):
                recipes.append({"name": name + "-" + "-".join(map(str, states)),
                                "inputs": list(states), "output": 8, "work": work})
        return {"kind": "op", "weights": {"8": 1, "16": 1, "32": 1, "64": 1},
                "operands": operands, "recipes": list(reversed(recipes))}
    nodes = {"s" + str(i): source() for i in range(degree)}
    operands = list(nodes)
    if nested:
        nodes["u"] = operation([operands[0]])
        operands[0] = "u"
    nodes["r"] = operation(operands)
    return {"schema": 1, "name": "descriptor-fixture", "group": "test", "capacity": capacity,
            "states": [8, 16, 32, 64], "root": "r", "root_states": [8, 16], "nodes": nodes}


def model(raw):
    return make_instance(**{key: raw[key] for key in ("name", "group", "capacity", "root", "root_states", "nodes")})


def finite_reference(raw, limit=4000):
    """Smallest-cost scan over explicit one-shot configurations, independent of
    the two-capacity recurrence, choices and production oracle. Uses raw JSON
    allocations and scalar cost pairs. State exhaustion raises, not agreement.
    """
    nodes = raw["nodes"]
    initial = ((), frozenset(), frozenset())  # chosen labels, resident, stored
    distance = {initial: (0, Fraction(0))}
    pending = {initial}
    while pending:
        config = min(pending, key=distance.__getitem__)
        pending.remove(config)
        labels, red, blue = config
        chosen = dict(labels)
        cost = distance[config]
        if raw["root"] in blue and chosen[raw["root"]] in raw["root_states"]:
            return cost
        memory = sum(nodes[n]["weights"][str(chosen[n])] for n in red)
        successors = []
        for name, node in nodes.items():
            if node["kind"] == "source" and name not in chosen:
                for state in node["source_states"]:
                    size = node["weights"][str(state)]
                    if memory + size <= raw["capacity"]:
                        assigned = dict(chosen, **{name: state})
                        successors.append(((tuple(sorted(assigned.items())), red | {name}, blue), (size, Fraction(0))))
            elif node["kind"] == "op":
                if name in chosen:
                    size = node["weights"][str(chosen[name])]
                    if name in red and name not in blue:
                        successors.append(((labels, red, blue | {name}), (size, Fraction(0))))
                    if name in blue and name not in red and memory + size <= raw["capacity"]:
                        successors.append(((labels, red | {name}, blue), (size, Fraction(0))))
                    if name in red and name in blue:
                        successors.append(((labels, red - {name}, blue), (0, Fraction(0))))
                else:
                    operands = node["operands"]
                    if all(child in red for child in operands):
                        for recipe in node["recipes"]:
                            if [chosen[child] for child in operands] != recipe["inputs"]:
                                continue
                            state = recipe["output"]
                            if memory + node["weights"][str(state)] <= raw["capacity"]:
                                assigned = dict(chosen, **{name: state})
                                successors.append(((tuple(sorted(assigned.items())), (red - set(operands)) | {name}, blue),
                                                   (0, Fraction(*recipe["work"]))))
        for next_config, edge in successors:
            value = (cost[0] + edge[0], cost[1] + edge[1])
            if next_config not in distance or value < distance[next_config]:
                if next_config not in distance and len(distance) >= limit:
                    raise AssertionError("independent finite reference exhausted its state bound")
                distance[next_config] = value
                pending.add(next_config)
    return None


class RecipeDescriptorRegression(unittest.TestCase):
    def checked(self, raw):
        instance = model(raw)
        solution = PreparationAwareOptimizer(instance).solve()
        observed = None if solution.cost is None else (solution.cost.io, solution.cost.work)
        self.assertEqual(observed, finite_reference(raw))
        claim = check_solution_claim(instance, None if solution.cost is None else solution.cost.to_json(),
                                     solution.events, solution.certificate)
        self.assertTrue(claim["valid"], claim["errors"])
        return instance, solution

    def test_independent_finite_costs_and_infinity(self):
        for weight, degree, nested, capacity in product((1, 2, 3), (1, 2, 3), (False, True), range(1, 10)):
            with self.subTest(weight=weight, degree=degree, nested=nested, capacity=capacity):
                self.checked(fixture(capacity, weight, degree, nested))

    def test_recipe_order_rational_tie_and_uncut_tie(self):
        raw = fixture(20, nested=True)
        _, solution = self.checked(raw)
        root = solution.certificate["states"]["r|8|20"]["choice"]
        self.assertTrue(root["recipe"].startswith("a-"))
        self.assertEqual([child["id"] for child in root["children"]], ["s1", "u"])
        self.assertFalse(any(child["cut"] for child in root["children"]))
        self.assertEqual(solution.cost.work, Fraction(2, 3))
        changed = copy.deepcopy(raw)
        for node in changed["nodes"].values():
            if node["kind"] == "op":
                node["recipes"].reverse()
        _, reversed_solution = self.checked(changed)
        self.assertEqual(solution.certificate, reversed_solution.certificate)
        self.assertEqual(solution.events, reversed_solution.events)

    def test_one_descriptor_build_per_solve_key_without_reordering(self):
        class Counting(PreparationAwareOptimizer):
            def _recipe_candidates(self, node_id, state):
                self.calls.append((node_id, state))
                return super()._recipe_candidates(node_id, state)
        instance = separation_instance(1, 8, 1, name="descriptor-count", group="test")
        optimizer = Counting(instance)
        optimizer.calls = []
        solution = optimizer.solve()
        self.assertEqual(len(optimizer.calls), len(set(optimizer.calls)))
        queried = [(key.split("|")[0], int(key.split("|")[1])) for key in solution.certificate["states"]
                   if instance.node(key.split("|")[0]).kind == "op"]
        self.assertGreater(len(queried), len(optimizer.calls))
        self.assertIsNone(optimizer._recipe_descriptors)
        self.assertTrue(check_certificate(instance, solution.certificate)["valid"])

    def test_model_isolation_and_no_cache_between_direct_value_calls(self):
        for weight in (2, 3, 1):
            self.checked(fixture(10, weight))
        instance = model(fixture(10, 2))
        optimizer = PreparationAwareOptimizer(instance)
        self.assertEqual(optimizer.value("r", 8, 5).io, 4)
        for node in instance.nodes.values():
            if node.kind == "source":
                node.weights[8] = 3
        self.assertEqual(optimizer.value("r", 8, 9), PreparationAwareOptimizer(instance).value("r", 8, 9))
        self.assertIsNone(optimizer._recipe_descriptors)
        # Memoized states still require the original fixed instance, as before.

    def test_cache_cleanup_after_exception_and_boundary_states(self):
        optimizer = PreparationAwareOptimizer(model(fixture()))
        with patch.object(optimizer, "_solve", side_effect=RuntimeError("fixture stop")):
            with self.assertRaisesRegex(RuntimeError, "fixture stop"):
                optimizer.solve()
        self.assertIsNone(optimizer._recipe_descriptors)
        self.assertIsNone(optimizer.value("r", 8, -1))
        self.assertIsNone(optimizer.value("r", 16, 7))
        self.assertIsNone(optimizer._memo[next(key for key in optimizer._memo if key.budget == -1)])
        self.assertTrue(check_certificate(optimizer.instance, PreparationAwareOptimizer(optimizer.instance).solve().certificate)["valid"])

    def test_independent_checkers_reject_corruption_and_expansive_exactness(self):
        instance, solution = self.checked(fixture(7, nested=True))
        self.assertTrue(check_events(instance, solution.events).valid)
        for field in ("cost", "record"):
            corrupted = copy.deepcopy(solution.certificate)
            key = next(key for key, value in corrupted["states"].items() if value["cost"] is not None)
            if field == "record":
                del corrupted["states"][key]
            else:
                corrupted["states"][key][field] = None
            self.assertFalse(check_certificate(instance, corrupted)["valid"])
        extraction = copy.deepcopy(solution.certificate)
        extraction["states"][key]["choice"] = None
        # The Bellman check proves costs/keys, not extraction choices. Event
        # replay and exact before/current comparison have separate duties.
        self.assertTrue(check_certificate(instance, extraction)["valid"])
        self.assertFalse(check_events(instance, solution.events[:-1]).valid)
        with self.assertRaises(ValueError):
            PreparationAwareOptimizer(valley_instance(), exact=True)
        self.assertEqual(PreparationAwareOptimizer(valley_instance(), exact=False).solve().cost.io, 35)


if __name__ == "__main__":
    unittest.main()
