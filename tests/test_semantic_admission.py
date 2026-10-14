from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.campaign import load_index
from src.pipeline import evaluate_case


REPO = Path(__file__).resolve().parents[1]


class SemanticAdmissionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = next(record for record in load_index(REPO)["records"] if record["semantic"])
        cls.raw = json.loads((REPO / "instances" / cls.record["file"]).read_text(encoding="utf-8"))

    def _evaluate_raw(self, raw: dict) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            instance_path = repo / "instances" / self.record["file"]
            instance_path.parent.mkdir(parents=True)
            instance_path.write_text(json.dumps(raw), encoding="utf-8")
            return evaluate_case(repo, self.record, oracle_state_cap=100, oracle_cpu_cap=1.0)

    def test_frozen_typed_case_runs_the_complete_profile(self) -> None:
        result = self._evaluate_raw(copy.deepcopy(self.raw))
        self.assertEqual(result["status"], "checked", result["errors"])
        self.assertTrue(result["semantic"]["valid"])
        self.assertEqual(
            {item["pattern"] for item in result["semantic"]["patterns"]},
            {"zero", "positive", "negative", "alternating", "pseudorandom-9137"},
        )

    def test_empty_semantic_profile_is_rejected_by_production_evaluator(self) -> None:
        raw = copy.deepcopy(self.raw)
        raw["metadata"]["semantic_patterns"] = []
        with self.assertRaisesRegex(ValueError, "complete supported profile"):
            self._evaluate_raw(raw)

    def test_malformed_semantic_metadata_is_rejected_by_production_evaluator(self) -> None:
        controls = (
            ("semantic_patterns", "zero", "JSON array"),
            ("semantic_patterns", ["zero"] * 5, "duplicates"),
            ("semantic_patterns", ["zero", "positive", "negative", "alternating", "unknown"], "complete supported profile"),
            ("source_length", True, "must be an integer"),
            ("source_length", 2.0, "must be an integer"),
            ("bound", False, "must be an integer"),
        )
        for field, value, message in controls:
            with self.subTest(field=field, value=value):
                raw = copy.deepcopy(self.raw)
                raw["metadata"][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    self._evaluate_raw(raw)

        raw = copy.deepcopy(self.raw)
        raw["metadata"]["operator_family"] = "dot"
        with self.assertRaisesRegex(ValueError, "must agree with family"):
            self._evaluate_raw(raw)


if __name__ == "__main__":
    unittest.main()
