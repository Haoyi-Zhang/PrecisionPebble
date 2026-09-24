from __future__ import annotations

import unittest

from src.contiguous import contiguous_policy
from src.generators import integer_instance, separation_instance
from src.optimizer import PreparationAwareOptimizer
from src.reference_eq6 import reference_eq6


class ReferenceEquationTest(unittest.TestCase):
    def test_concrete_separation_is_89_versus_91(self) -> None:
        instance = separation_instance(1, 8, 1, name="reference-concrete", group="test")
        optimum = PreparationAwareOptimizer(instance, exact=True).solve()
        self.assertEqual(optimum.cost.io, 89)
        self.assertEqual(reference_eq6(instance).io, 91)
        self.assertEqual(contiguous_policy(instance)[0].io, 91)

    def test_parameter_family_is_23t_versus_25t(self) -> None:
        for t in (1, 2, 4, 8):
            with self.subTest(t=t):
                instance = separation_instance(t, 2 * t, t, name=f"reference-t{t}", group="test")
                optimum = PreparationAwareOptimizer(instance, exact=True).solve()
                self.assertEqual(optimum.cost.io, 23 * t)
                self.assertEqual(reference_eq6(instance).io, 25 * t)
                self.assertEqual(contiguous_policy(instance)[0].io, 25 * t)

    def test_typed_instance_is_rejected(self) -> None:
        instance = integer_instance("sum", 8, 7, 24)
        with self.assertRaises(ValueError):
            reference_eq6(instance)


if __name__ == "__main__":
    unittest.main()
