from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from reproduce import run_campaign
from src.campaign import case_filename, validate_complete_campaign
from src.cost import Cost
from tools.compare_replay import compare_campaigns
from tools.summarize import load_results


class CampaignIntegrityTest(unittest.TestCase):
    def _repo(self, root: Path, count: int = 2) -> tuple[Path, list[dict]]:
        repo = root / "repo"
        campaign = repo / "instances" / "campaign"
        campaign.mkdir(parents=True)
        records = []
        for order in range(count):
            name = f"case-{order}"
            relative = f"campaign/{order:03d}-{name}.json"
            payload = {"schema": 1, "name": name, "sentinel": order}
            (repo / "instances" / relative).write_text(json.dumps(payload), encoding="utf-8")
            records.append(
                {
                    "order": order,
                    "name": name,
                    "group": "fixture",
                    "file": relative,
                    "exact": True,
                    "certificate": False,
                    "oracle": False,
                    "semantic": False,
                }
            )
        index = {"schema": 1, "case_count": count, "records": records}
        (repo / "instances" / "index.json").write_text(json.dumps(index), encoding="utf-8")
        return repo, records

    @staticmethod
    def _evaluator(cpu_by_name: dict[str, float], units: int = 1):
        def evaluate(repo: Path, record: dict, *, oracle_state_cap: int, oracle_cpu_cap: float) -> dict:
            del repo, oracle_state_cap, oracle_cpu_cap
            return {
                "schema": 2,
                "name": record["name"],
                "group": record["group"],
                "instance_file": record["file"],
                "status": "checked",
                "errors": [],
                "metrics": {
                    "audit_unit_components": {"fixture": units},
                    "audit_units": units,
                    "case_body_cpu_seconds": cpu_by_name[record["name"]],
                },
            }
        return evaluate

    def test_compare_rejects_nonexistent_and_empty_campaigns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _ = self._repo(root, 1)
            missing = root / "missing"
            empty = root / "empty"
            empty.mkdir()
            report = compare_campaigns(repo, missing, empty)
            self.assertFalse(report["logical_match"])
            self.assertTrue(any("does not exist" in item for item in report["validation_errors"]))
            self.assertTrue(any("manifest is missing" in item for item in report["validation_errors"]))

    def test_compare_rejects_when_both_campaigns_miss_the_same_case(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, records = self._repo(root, 2)
            evaluator = self._evaluator({record["name"]: 0.1 for record in records})
            left = root / "left"
            right = root / "right"
            for output in (left, right):
                self.assertEqual(
                    run_campaign(
                        repo=repo, output=output, chunk=2, oracle_state_cap=10, oracle_cpu_cap=1.0, evaluator=evaluator
                    ),
                    0,
                )
                (output / "cases" / case_filename(records[1])).unlink()
            report = compare_campaigns(repo, left, right)
            self.assertFalse(report["logical_match"])
            self.assertTrue(any("missing case files" in item for item in report["validation_errors"]))

    def test_budget_reached_between_chunks_blocks_next_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, records = self._repo(root, 2)
            output = root / "results"
            calls: list[str] = []
            base = self._evaluator({record["name"]: 0.1 for record in records}, units=1)
            def evaluator(repo: Path, record: dict, *, oracle_state_cap: int, oracle_cpu_cap: float) -> dict:
                calls.append(record["name"])
                return base(repo, record, oracle_state_cap=oracle_state_cap, oracle_cpu_cap=oracle_cpu_cap)
            self.assertEqual(
                run_campaign(
                    repo=repo, output=output, chunk=1, oracle_state_cap=10, oracle_cpu_cap=1.0,
                    audit_unit_cap=1, case_body_cpu_cap_seconds=10.0, evaluator=evaluator
                ),
                0,
            )
            self.assertEqual(
                run_campaign(
                    repo=repo, output=output, chunk=1, oracle_state_cap=10, oracle_cpu_cap=1.0,
                    audit_unit_cap=1, case_body_cpu_cap_seconds=10.0, evaluator=evaluator
                ),
                2,
            )
            self.assertEqual(calls, [records[0]["name"]])
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["terminal_status"], "budget-exhausted-before-submit")
            self.assertFalse(manifest["complete"])

    def test_compare_rejects_same_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, _ = self._repo(root, 1)
            path = root / "same"
            path.mkdir()
            report = compare_campaigns(repo, path, path)
            self.assertFalse(report["logical_match"])
            self.assertIn("reference and replay resolve to the same directory", report["validation_errors"])

    def test_final_case_over_budget_stays_incomplete_on_empty_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, records = self._repo(root, 2)
            output = root / "results"
            evaluator = self._evaluator({records[0]["name"]: 0.4, records[1]["name"]: 0.7})
            first = run_campaign(
                repo=repo,
                output=output,
                chunk=2,
                oracle_state_cap=10,
                oracle_cpu_cap=1.0,
                audit_unit_cap=10,
                case_body_cpu_cap_seconds=1.0,
                evaluator=evaluator,
            )
            self.assertEqual(first, 2)
            final_case = json.loads((output / "cases" / case_filename(records[1])).read_text())
            self.assertEqual(final_case["status"], "incomplete")
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertFalse(manifest["complete"])
            self.assertEqual(manifest["terminal_status"], "budget-exceeded-after-candidate")

            second = run_campaign(
                repo=repo,
                output=output,
                chunk=2,
                oracle_state_cap=10,
                oracle_cpu_cap=1.0,
                audit_unit_cap=10,
                case_body_cpu_cap_seconds=1.0,
                evaluator=evaluator,
            )
            self.assertEqual(second, 2)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertFalse(manifest["complete"])
            self.assertEqual(manifest["terminal_status"], "incomplete-case-retained")

    def test_resume_binds_checked_record_to_input_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, records = self._repo(root, 2)
            output = root / "results"
            evaluator = self._evaluator({record["name"]: 0.1 for record in records})
            first = run_campaign(
                repo=repo,
                output=output,
                chunk=1,
                oracle_state_cap=10,
                oracle_cpu_cap=1.0,
                evaluator=evaluator,
            )
            self.assertEqual(first, 0)
            input_path = repo / "instances" / records[0]["file"]
            input_path.write_text(json.dumps({"schema": 1, "changed": True}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identity/input digest mismatch"):
                run_campaign(
                    repo=repo,
                    output=output,
                    chunk=1,
                    oracle_state_cap=10,
                    oracle_cpu_cap=1.0,
                    evaluator=evaluator,
                )

    def test_summary_rejects_same_count_with_wrong_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, records = self._repo(root, 1)
            output = root / "results"
            evaluator = self._evaluator({records[0]["name"]: 0.1})
            self.assertEqual(
                run_campaign(
                    repo=repo,
                    output=output,
                    chunk=1,
                    oracle_state_cap=10,
                    oracle_cpu_cap=1.0,
                    evaluator=evaluator,
                ),
                0,
            )
            case_path = output / "cases" / case_filename(records[0])
            case = json.loads(case_path.read_text())
            case["record_identity"]["name"] = "different-but-same-count"
            case_path.write_text(json.dumps(case), encoding="utf-8")
            validation = validate_complete_campaign(repo, output)
            self.assertFalse(validation.valid)
            self.assertTrue(any("identity/input digest mismatch" in item for item in validation.errors))
            with self.assertRaisesRegex(SystemExit, "invalid complete campaign"):
                load_results(output, repo)

    def test_cost_parser_rejects_fractional_and_boolean_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "cost io must be an integer"):
            Cost.from_json({"io": 31.9, "work": [0, 1]})
        with self.assertRaisesRegex(ValueError, "cost work numerator must be an integer"):
            Cost.from_json({"io": 1, "work": [True, 1]})
        value = Cost.from_json({"io": 1, "work": [1, 2]})
        self.assertEqual(value.work.numerator, 1)
        self.assertEqual(value.work.denominator, 2)


if __name__ == "__main__":
    unittest.main()
