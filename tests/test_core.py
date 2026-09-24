from __future__ import annotations

import copy
import unittest

from src.bellman_checker import check_certificate
from src.contiguous import contiguous_policy
from src.event_checker import check_events
from src.generators import fixed64_projection, integer_instance, separation_instance, valley_instance
from src.optimizer import PreparationAwareOptimizer
from src.oracle import configuration_oracle
from src.semantic import check_integer_semantics


class CoreResultsTest(unittest.TestCase):
    def test_separation_values_and_witness(self) -> None:
        instance = separation_instance(1, 8, 1, name="test-separation", group="test")
        solution = PreparationAwareOptimizer(instance, exact=True).solve()
        self.assertEqual(solution.cost.io, 89)
        self.assertEqual(contiguous_policy(instance)[0].io, 91)
        self.assertTrue(check_events(instance, solution.events).valid)
        self.assertTrue(check_certificate(instance, solution.certificate)["valid"])
        oracle = configuration_oracle(instance, state_cap=5_000, cpu_cap=5.0)
        self.assertEqual(oracle.status, "complete")
        self.assertEqual(oracle.cost, solution.cost)

    def test_expansive_valley_discriminates_policies(self) -> None:
        instance = valley_instance()
        policy = PreparationAwareOptimizer(instance, exact=False).solve()
        oracle = configuration_oracle(instance, state_cap=5_000, cpu_cap=5.0)
        self.assertEqual(oracle.cost.io, 33)
        self.assertEqual(policy.cost.io, 35)
        self.assertEqual(contiguous_policy(instance)[0].io, 49)
        with self.assertRaises(ValueError):
            PreparationAwareOptimizer(instance, exact=True)

    def test_certificate_corruption_is_rejected(self) -> None:
        instance = separation_instance(1, 8, 1, name="test-certificate", group="test")
        solution = PreparationAwareOptimizer(instance, exact=True).solve()
        corrupted = copy.deepcopy(solution.certificate)
        key = next(key for key, value in corrupted["states"].items() if value["cost"] is not None)
        corrupted["states"][key]["cost"]["io"] += 1
        self.assertFalse(check_certificate(instance, corrupted)["valid"])

    def test_integer_target_values_and_semantics(self) -> None:
        expected = {
            ("sum", 17): (518, None),
            ("sum", 24): (514, 552),
            ("sum", 32): (514, 520),
            ("dot", 17): (1130, None),
            ("dot", 24): (1026, 1704),
            ("dot", 32): (1026, 1192),
            ("abs", 17): (1114, None),
            ("abs", 24): (1026, 1704),
            ("abs", 32): (1026, 1192),
        }
        for family in ("sum", "dot", "abs"):
            for multiplier in (17, 24, 32):
                with self.subTest(family=family, multiplier=multiplier):
                    instance = integer_instance(family, 8, 7, multiplier)
                    typed = PreparationAwareOptimizer(instance, exact=True).solve()
                    fixed = PreparationAwareOptimizer(fixed64_projection(instance), exact=True).solve()
                    typed_expected, fixed_expected = expected[(family, multiplier)]
                    self.assertEqual(typed.cost.io, typed_expected)
                    self.assertEqual(None if fixed.cost is None else fixed.cost.io, fixed_expected)
                    self.assertTrue(check_integer_semantics(instance, typed.events)["valid"])


if __name__ == "__main__":
    unittest.main()
