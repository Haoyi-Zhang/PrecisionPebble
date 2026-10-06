from __future__ import annotations

import copy
from dataclasses import replace
from fractions import Fraction
import unittest

from src.bellman_checker import check_certificate
from src.claim_checker import check_solution_claim
from src.generators import separation_instance, valley_instance
from src.optimizer import PreparationAwareOptimizer


class ClaimEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.instance = separation_instance(1, 2, 1)
        self.solution = PreparationAwareOptimizer(self.instance).solve()
        self.infeasible = replace(self.instance, capacity=1)
        self.no_solution = PreparationAwareOptimizer(self.infeasible).solve()

    def test_explicit_infinity_certificate_is_accepted(self) -> None:
        result = check_solution_claim(self.infeasible, None, [], self.no_solution.certificate)
        self.assertTrue(result["valid"], result["errors"])

    def test_missing_infinite_state_cost_is_rejected(self) -> None:
        certificate = copy.deepcopy(self.no_solution.certificate)
        del next(iter(certificate["states"].values()))["cost"]
        self.assertFalse(check_certificate(self.infeasible, certificate)["valid"])

    def test_missing_infinite_terminal_cost_is_rejected(self) -> None:
        certificate = copy.deepcopy(self.no_solution.certificate)
        del certificate["terminal_cost"]
        self.assertFalse(check_certificate(self.infeasible, certificate)["valid"])

    def test_missing_infeasible_root_state_is_rejected(self) -> None:
        certificate = copy.deepcopy(self.no_solution.certificate)
        del certificate["root_state"]
        self.assertFalse(check_certificate(self.infeasible, certificate)["valid"])

    def test_bare_infeasibility_claim_is_rejected(self) -> None:
        result = check_solution_claim(self.instance, None, [], None)
        self.assertFalse(result["valid"])

    def test_upper_bound_certificate_is_outside_infeasibility_contract(self) -> None:
        instance = replace(valley_instance(), capacity=1)
        solution = PreparationAwareOptimizer(instance, exact=False).solve()
        self.assertTrue(check_certificate(instance, solution.certificate)["valid"])
        result = check_solution_claim(instance, None, [], solution.certificate)
        self.assertFalse(result["valid"])

    def test_equivalent_zero_rational_claim_is_accepted(self) -> None:
        claimed = self.solution.cost.to_json()
        claimed["work"] = [0, 2]
        result = check_solution_claim(self.instance, claimed, self.solution.events, self.solution.certificate)
        self.assertTrue(result["valid"], result["errors"])

    def test_equivalent_nonzero_rational_claim_is_accepted(self) -> None:
        nodes = dict(self.instance.nodes)
        root = nodes[self.instance.root]
        nodes[root.id] = replace(root, recipes=(replace(root.recipes[0], work=Fraction(1, 3)),))
        instance = replace(self.instance, nodes=nodes)
        solution = PreparationAwareOptimizer(instance).solve()
        claimed = solution.cost.to_json()
        claimed["work"] = [2, 6]
        result = check_solution_claim(instance, claimed, solution.events, solution.certificate)
        self.assertTrue(result["valid"], result["errors"])

    def test_wrong_rational_claim_is_rejected(self) -> None:
        claimed = self.solution.cost.to_json()
        claimed["work"] = [1, 2]
        self.assertFalse(check_solution_claim(self.instance, claimed, self.solution.events, self.solution.certificate)["valid"])

    def test_finite_trace_without_certificate_is_a_feasibility_check(self) -> None:
        result = check_solution_claim(self.instance, self.solution.cost.to_json(), self.solution.events, None)
        self.assertTrue(result["valid"], result["errors"])
        self.assertIsNone(result["certificate_check"])


if __name__ == "__main__":
    unittest.main()
