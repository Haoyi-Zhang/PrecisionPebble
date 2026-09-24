from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.generators import all_campaign_instances, hardness_instance, motzkin_shapes, separation_instance
from src.model import dump_instance, load_instance


class ModelTest(unittest.TestCase):
    def _load_raw(self, raw: dict) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "instance.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            load_instance(path)

    def _base(self) -> dict:
        return separation_instance(1, 2, 1, name="validation-base", group="test").to_json()

    def test_motzkin_grid_count(self) -> None:
        self.assertEqual(sum(len(motzkin_shapes(size)) for size in range(2, 6)), 16)

    def test_campaign_contract(self) -> None:
        campaign = all_campaign_instances()
        self.assertEqual(len(campaign), 364)
        self.assertLessEqual(max(len(instance.nodes) for instance, _ in campaign), 64)
        self.assertLessEqual(max(instance.capacity for instance, _ in campaign), 1024)
        self.assertLessEqual(max(instance.recipe_count for instance, _ in campaign), 192)

    def test_json_round_trip(self) -> None:
        instance = hardness_instance([1, 1], name="round-trip", scaled=True)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "instance.json"
            dump_instance(instance, path)
            recovered = load_instance(path)
        self.assertEqual(recovered.to_json(), instance.to_json())

    def test_nonpositive_capacity_is_rejected(self) -> None:
        raw = self._base()
        raw["capacity"] = 0
        with self.assertRaisesRegex(ValueError, "capacity"):
            self._load_raw(raw)

    def test_missing_root_is_rejected(self) -> None:
        raw = self._base()
        raw["root"] = "missing"
        with self.assertRaisesRegex(ValueError, "root"):
            self._load_raw(raw)

    def test_source_root_is_rejected(self) -> None:
        raw = self._base()
        raw["root"] = "sa"
        with self.assertRaisesRegex(ValueError, "internal root"):
            self._load_raw(raw)

    def test_undeclared_root_state_is_rejected(self) -> None:
        raw = self._base()
        raw["root_states"] = [7]
        with self.assertRaisesRegex(ValueError, "root states"):
            self._load_raw(raw)

    def test_missing_operand_is_rejected(self) -> None:
        raw = self._base()
        raw["nodes"]["b"]["operands"][0] = "missing"
        with self.assertRaisesRegex(ValueError, "missing operand"):
            self._load_raw(raw)

    def test_shared_operand_is_rejected(self) -> None:
        raw = self._base()
        raw["nodes"]["c"]["operands"][0] = "sb1"
        with self.assertRaisesRegex(ValueError, "exactly one consumer"):
            self._load_raw(raw)

    def test_cycle_is_rejected(self) -> None:
        raw = self._base()
        raw["nodes"]["A"]["operands"] = ["z"]
        with self.assertRaisesRegex(ValueError, "cycle|consumer"):
            self._load_raw(raw)

    def test_disconnected_node_is_rejected(self) -> None:
        raw = self._base()
        raw["nodes"]["orphan"] = copy.deepcopy(raw["nodes"]["sa"])
        with self.assertRaisesRegex(ValueError, "exactly one consumer|disconnected"):
            self._load_raw(raw)

    def test_nonpositive_weight_is_rejected(self) -> None:
        raw = self._base()
        raw["nodes"]["sa"]["weights"]["64"] = 0
        with self.assertRaisesRegex(ValueError, "nonpositive allocation"):
            self._load_raw(raw)

    def test_undeclared_source_state_is_rejected(self) -> None:
        raw = self._base()
        raw["nodes"]["sa"]["source_states"] = [7]
        with self.assertRaisesRegex(ValueError, "undeclared state"):
            self._load_raw(raw)

    def test_wrong_recipe_arity_is_rejected(self) -> None:
        raw = self._base()
        raw["nodes"]["b"]["recipes"][0]["inputs"] = [64]
        with self.assertRaisesRegex(ValueError, "wrong arity"):
            self._load_raw(raw)

    def test_negative_work_is_rejected(self) -> None:
        raw = self._base()
        raw["nodes"]["b"]["recipes"][0]["work"] = [-1, 1]
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            self._load_raw(raw)

    def test_zero_work_denominator_is_rejected(self) -> None:
        raw = self._base()
        raw["nodes"]["b"]["recipes"][0]["work"] = [0, 0]
        with self.assertRaisesRegex(ValueError, "denominator"):
            self._load_raw(raw)

    def test_duplicate_recipe_name_is_rejected(self) -> None:
        raw = self._base()
        raw["nodes"]["b"]["recipes"].append(copy.deepcopy(raw["nodes"]["b"]["recipes"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate recipe"):
            self._load_raw(raw)


if __name__ == "__main__":
    unittest.main()
