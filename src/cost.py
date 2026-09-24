from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Optional


@dataclass(frozen=True, order=True)
class Cost:
    """Lexicographic objective: transferred allocation units, then work."""

    io: int
    work: Fraction

    def __add__(self, other: "Cost") -> "Cost":
        return Cost(self.io + other.io, self.work + other.work)

    @staticmethod
    def zero() -> "Cost":
        return Cost(0, Fraction(0, 1))

    def to_json(self) -> dict[str, Any]:
        return {"io": self.io, "work": [self.work.numerator, self.work.denominator]}

    @staticmethod
    def from_json(raw: dict[str, Any]) -> "Cost":
        num, den = raw["work"]
        return Cost(int(raw["io"]), Fraction(int(num), int(den)))


MaybeCost = Optional[Cost]


def add_cost(left: MaybeCost, right: Cost) -> MaybeCost:
    if left is None:
        return None
    return left + right


def minimum(*values: MaybeCost) -> MaybeCost:
    finite = [value for value in values if value is not None]
    return min(finite) if finite else None


def cost_to_json(value: MaybeCost) -> Any:
    return None if value is None else value.to_json()


def cost_from_json(value: Any) -> MaybeCost:
    return None if value is None else Cost.from_json(value)
