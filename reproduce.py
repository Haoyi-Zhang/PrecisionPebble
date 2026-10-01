#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from src.campaign import (  # noqa: E402
    bind_case_result,
    case_filename,
    index_sha256,
    load_index,
    validate_case_result,
)
from src.pipeline import evaluate_case, write_json  # noqa: E402

ADDRESS_LIMIT = 3 * 1024 * 1024 * 1024
CAMPAIGN_AUDIT_UNIT_CAP = 600_000
CAMPAIGN_CASE_BODY_CPU_CAP_SECONDS = 2_700.0

Evaluator = Callable[..., dict[str, Any]]


def constrain_process() -> dict[str, object]:
    resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_LIMIT, ADDRESS_LIMIT))
    affinity = None
    if hasattr(os, "sched_getaffinity") and hasattr(os, "sched_setaffinity"):
        available = sorted(os.sched_getaffinity(0))
        if available:
            os.sched_setaffinity(0, {available[0]})
            affinity = [available[0]]
    return {"address_limit_bytes": ADDRESS_LIMIT, "affinity": affinity, "workers": 1}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded chunk of the frozen 364-case campaign")
    parser.add_argument("--output", required=True, help="output directory, relative to the repository or absolute")
    parser.add_argument("--chunk", type=int, default=64, help="maximum new cases in this invocation")
    parser.add_argument("--oracle-state-cap", type=int, default=50_000)
    parser.add_argument("--oracle-cpu-cap", type=float, default=15.0)
    return parser.parse_args()


def _campaign_config(
    *,
    oracle_state_cap: int,
    oracle_cpu_cap: float,
    audit_unit_cap: int,
    case_body_cpu_cap_seconds: float,
) -> dict[str, Any]:
    return {
        "oracle_state_cap": oracle_state_cap,
        "oracle_case_cpu_cap_seconds": oracle_cpu_cap,
        "audit_unit_cap": audit_unit_cap,
        "cumulative_case_body_cpu_cap_seconds": case_body_cpu_cap_seconds,
    }


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc


def _manifest(
    *,
    repo: Path,
    records: list[dict[str, Any]],
    checked_cases: int,
    incomplete_cases: int,
    cumulative_audit_units: int,
    cumulative_case_body_cpu_seconds: float,
    prior_invocations: list[dict[str, Any]],
    current_invocation: dict[str, Any] | None,
    config: dict[str, Any],
    limits: dict[str, Any],
    terminal_status: str,
    complete: bool,
    message: str | None = None,
) -> dict[str, Any]:
    invocations = list(prior_invocations)
    if current_invocation is not None:
        invocations.append(current_invocation)
    value: dict[str, Any] = {
        "schema": 2,
        "index_sha256": index_sha256(repo),
        "campaign_config": config,
        "expected_cases": len(records),
        "checked_cases": checked_cases,
        "incomplete_cases": incomplete_cases,
        "complete": complete,
        "terminal_status": terminal_status,
        "cumulative_audit_units": cumulative_audit_units,
        "cumulative_case_body_cpu_seconds": cumulative_case_body_cpu_seconds,
        "total_invocation_process_cpu_seconds": sum(
            float(item["invocation_process_cpu_seconds"]) for item in invocations
        ),
        "max_rss_kib": max((int(item["max_rss_kib"]) for item in invocations), default=0),
        "invocations": invocations,
        "timing_semantics": {
            "case_body_cpu_seconds": (
                "Per-case process CPU measured inside evaluate_case; this is the quantity accumulated "
                f"against the configured {config['cumulative_case_body_cpu_cap_seconds']:g}-second campaign cap."
            ),
            "invocation_process_cpu_seconds": (
                "Process CPU for one reproduce.py invocation, including resume validation, JSON I/O, "
                "case bodies, and manifest writing; it is recorded separately and is not the cap quantity."
            ),
            "external_timing": (
                "Elapsed time and process-tree resource measurements, when retained, are collected by an "
                "external timing command and are not inferred from this manifest."
            ),
        },
        "limits": limits,
    }
    if message is not None:
        value["message"] = message
    return value


def run_campaign(
    *,
    repo: Path,
    output: Path,
    chunk: int,
    oracle_state_cap: int,
    oracle_cpu_cap: float,
    audit_unit_cap: int = CAMPAIGN_AUDIT_UNIT_CAP,
    case_body_cpu_cap_seconds: float = CAMPAIGN_CASE_BODY_CPU_CAP_SECONDS,
    evaluator: Evaluator = evaluate_case,
    limits: dict[str, Any] | None = None,
) -> int:
    """Run or resume a campaign while preserving fail-closed budget state.

    The campaign cap is applied to the sum of per-case body process CPU.  It is
    checked at resume, before each new case is submitted, after each candidate
    case, and before a complete manifest is emitted.  A candidate that crosses
    a cap is persisted as ``incomplete`` and remains a blocker on later runs.
    """

    if type(chunk) is not int or chunk <= 0:
        raise ValueError("chunk must be a positive integer")
    if type(oracle_state_cap) is not int or oracle_state_cap <= 0:
        raise ValueError("oracle_state_cap must be a positive integer")
    if not isinstance(oracle_cpu_cap, (int, float)) or isinstance(oracle_cpu_cap, bool) or oracle_cpu_cap <= 0:
        raise ValueError("oracle_cpu_cap must be positive")
    if type(audit_unit_cap) is not int or audit_unit_cap <= 0:
        raise ValueError("audit_unit_cap must be a positive integer")
    if (
        not isinstance(case_body_cpu_cap_seconds, (int, float))
        or isinstance(case_body_cpu_cap_seconds, bool)
        or case_body_cpu_cap_seconds <= 0
    ):
        raise ValueError("case_body_cpu_cap_seconds must be positive")

    repo = repo.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cases_dir = output / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    index = load_index(repo)
    records: list[dict[str, Any]] = index["records"]
    expected_files = {case_filename(record) for record in records}
    observed_files = {path.name for path in cases_dir.glob("*.json")}
    extras = sorted(observed_files - expected_files)
    if extras:
        raise ValueError(f"unexpected case files prevent recovery: {extras[:5]}")

    config = _campaign_config(
        oracle_state_cap=oracle_state_cap,
        oracle_cpu_cap=float(oracle_cpu_cap),
        audit_unit_cap=audit_unit_cap,
        case_body_cpu_cap_seconds=float(case_body_cpu_cap_seconds),
    )
    limits = dict(limits or {})
    limits.update(config)

    manifest_path = output / "manifest.json"
    prior_invocations: list[dict[str, Any]] = []
    if manifest_path.exists():
        prior = _load_json(manifest_path)
        if not isinstance(prior, dict):
            raise ValueError("existing manifest is not a JSON object")
        if prior.get("index_sha256") != index_sha256(repo):
            raise ValueError("existing manifest is not bound to the current frozen index")
        if prior.get("campaign_config") != config:
            raise ValueError("existing manifest campaign configuration differs from this invocation")
        raw_invocations = prior.get("invocations", [])
        if not isinstance(raw_invocations, list):
            raise ValueError("existing manifest invocations field is malformed")
        prior_invocations = list(raw_invocations)

    checked: dict[str, dict[str, Any]] = {}
    blockers: dict[str, dict[str, Any]] = {}
    cumulative_audit_units = 0
    cumulative_case_body_cpu_seconds = 0.0
    for record in records:
        path = cases_dir / case_filename(record)
        if not path.exists():
            continue
        result = _load_json(path)
        status = result.get("status") if isinstance(result, dict) else None
        errors = validate_case_result(
            repo,
            record,
            result,
            oracle_state_cap=oracle_state_cap,
            oracle_cpu_cap=float(oracle_cpu_cap),
            required_status=None,
        )
        if errors:
            raise ValueError(f"stale or malformed recovery record {path.name}: {'; '.join(errors)}")
        cumulative_audit_units += int(result["metrics"]["audit_units"])
        cumulative_case_body_cpu_seconds += float(result["metrics"]["case_body_cpu_seconds"])
        if status == "checked":
            checked[record["name"]] = result
        else:
            blockers[record["name"]] = result

    invocation_start = time.process_time()

    def finish(
        terminal_status: str,
        complete: bool,
        *,
        new_cases_checked: int,
        candidates_evaluated: int,
        message: str | None = None,
        record_invocation: bool = True,
    ) -> int:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        current_invocation = None
        if record_invocation:
            current_invocation = {
                "new_cases_checked": new_cases_checked,
                "candidate_cases_evaluated": candidates_evaluated,
                "invocation_process_cpu_seconds": time.process_time() - invocation_start,
                "max_rss_kib": usage.ru_maxrss,
            }
        manifest = _manifest(
            repo=repo,
            records=records,
            checked_cases=len(checked),
            incomplete_cases=len(blockers),
            cumulative_audit_units=cumulative_audit_units,
            cumulative_case_body_cpu_seconds=cumulative_case_body_cpu_seconds,
            prior_invocations=prior_invocations,
            current_invocation=current_invocation,
            config=config,
            limits=limits,
            terminal_status=terminal_status,
            complete=complete,
            message=message,
        )
        write_json(manifest_path, manifest)
        print(json.dumps(manifest, indent=2))
        return 0 if complete or terminal_status == "chunk-complete" else 2

    # Resume-start guard: a previously persisted failure/incomplete case cannot
    # be converted to success by an invocation that evaluates no cases.
    if blockers:
        return finish(
            "incomplete-case-retained",
            False,
            new_cases_checked=0,
            candidates_evaluated=0,
            message=f"recovery is blocked by retained non-checked cases: {sorted(blockers)[:5]}",
        )

    pending = [record for record in records if record["name"] not in checked]
    if cumulative_audit_units > audit_unit_cap or cumulative_case_body_cpu_seconds > case_body_cpu_cap_seconds:
        return finish(
            "budget-exceeded-at-resume",
            False,
            new_cases_checked=0,
            candidates_evaluated=0,
            message="persisted checked records already exceed a campaign cap",
        )
    if pending and (
        cumulative_audit_units >= audit_unit_cap
        or cumulative_case_body_cpu_seconds >= case_body_cpu_cap_seconds
    ):
        return finish(
            "budget-exhausted-before-submit",
            False,
            new_cases_checked=0,
            candidates_evaluated=0,
            message="a campaign cap has been reached while cases remain",
        )

    # A genuinely complete campaign may be revalidated without appending a
    # misleading zero-work invocation.
    if not pending:
        if (
            len(checked) != len(records)
            or cumulative_audit_units > audit_unit_cap
            or cumulative_case_body_cpu_seconds > case_body_cpu_cap_seconds
        ):
            return finish(
                "final-validation-failed",
                False,
                new_cases_checked=0,
                candidates_evaluated=0,
                message="final completeness or budget validation failed",
            )
        return finish(
            "complete",
            True,
            new_cases_checked=0,
            candidates_evaluated=0,
            record_invocation=False,
        )

    new_cases_checked = 0
    candidates_evaluated = 0
    for record in pending[:chunk]:
        if (
            cumulative_audit_units >= audit_unit_cap
            or cumulative_case_body_cpu_seconds >= case_body_cpu_cap_seconds
        ):
            return finish(
                "budget-exhausted-before-submit",
                False,
                new_cases_checked=new_cases_checked,
                candidates_evaluated=candidates_evaluated,
                message=f"campaign cap reached before submitting {record['name']}",
            )

        candidate = evaluator(
            repo,
            record,
            oracle_state_cap=oracle_state_cap,
            oracle_cpu_cap=float(oracle_cpu_cap),
        )
        candidate = bind_case_result(
            repo,
            record,
            candidate,
            oracle_state_cap=oracle_state_cap,
            oracle_cpu_cap=float(oracle_cpu_cap),
        )
        candidates_evaluated += 1
        validation_errors = validate_case_result(
            repo,
            record,
            candidate,
            oracle_state_cap=oracle_state_cap,
            oracle_cpu_cap=float(oracle_cpu_cap),
            required_status=None,
        )
        if validation_errors:
            raise ValueError(f"evaluator returned malformed result for {record['name']}: {'; '.join(validation_errors)}")

        case_units = int(candidate["metrics"]["audit_units"])
        case_cpu = float(candidate["metrics"]["case_body_cpu_seconds"])
        prospective_units = cumulative_audit_units + case_units
        prospective_cpu = cumulative_case_body_cpu_seconds + case_cpu
        path = cases_dir / case_filename(record)

        if candidate.get("status") != "checked":
            write_json(path, candidate)
            blockers[record["name"]] = candidate
            cumulative_audit_units = prospective_units
            cumulative_case_body_cpu_seconds = prospective_cpu
            return finish(
                "case-validation-failed",
                False,
                new_cases_checked=new_cases_checked,
                candidates_evaluated=candidates_evaluated,
                message=f"case {record['name']} returned status {candidate.get('status')!r}",
            )

        cap_errors: list[str] = []
        if prospective_units > audit_unit_cap:
            cap_errors.append(f"audit-unit cap exceeded: {prospective_units}>{audit_unit_cap}")
        if prospective_cpu > case_body_cpu_cap_seconds:
            cap_errors.append(
                "cumulative case-body CPU cap exceeded: "
                f"{prospective_cpu:.9f}>{case_body_cpu_cap_seconds:.9f}"
            )
        if cap_errors:
            candidate = dict(candidate)
            candidate["status"] = "incomplete"
            candidate["errors"] = list(candidate.get("errors", [])) + cap_errors
            candidate["budget_status"] = {
                "prospective_audit_units": prospective_units,
                "audit_unit_cap": audit_unit_cap,
                "prospective_case_body_cpu_seconds": prospective_cpu,
                "case_body_cpu_cap_seconds": case_body_cpu_cap_seconds,
            }
            write_json(path, candidate)
            blockers[record["name"]] = candidate
            cumulative_audit_units = prospective_units
            cumulative_case_body_cpu_seconds = prospective_cpu
            return finish(
                "budget-exceeded-after-candidate",
                False,
                new_cases_checked=new_cases_checked,
                candidates_evaluated=candidates_evaluated,
                message=f"case {record['name']} was retained as incomplete after crossing a cap",
            )

        write_json(path, candidate)
        checked[record["name"]] = candidate
        cumulative_audit_units = prospective_units
        cumulative_case_body_cpu_seconds = prospective_cpu
        new_cases_checked += 1
        print(
            f"checked {record['order'] + 1:03d}/{len(records)} {record['name']} "
            f"audit_units={case_units} case_body_cpu={case_cpu:.4f}s"
        )

    still_pending = [record for record in records if record["name"] not in checked]
    if still_pending:
        return finish(
            "chunk-complete",
            False,
            new_cases_checked=new_cases_checked,
            candidates_evaluated=candidates_evaluated,
        )

    # Final complete exit repeats the identity and budget conditions rather
    # than inferring success from an empty pending list alone.
    if (
        len(checked) != len(records)
        or blockers
        or cumulative_audit_units > audit_unit_cap
        or cumulative_case_body_cpu_seconds > case_body_cpu_cap_seconds
    ):
        return finish(
            "final-validation-failed",
            False,
            new_cases_checked=new_cases_checked,
            candidates_evaluated=candidates_evaluated,
            message="final completeness or budget validation failed",
        )
    return finish(
        "complete",
        True,
        new_cases_checked=new_cases_checked,
        candidates_evaluated=candidates_evaluated,
    )


def main() -> int:
    args = parse_args()
    limits = constrain_process()
    output = Path(args.output)
    if not output.is_absolute():
        output = REPO / output
    try:
        return run_campaign(
            repo=REPO,
            output=output,
            chunk=args.chunk,
            oracle_state_cap=args.oracle_state_cap,
            oracle_cpu_cap=args.oracle_cpu_cap,
            limits=limits,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"campaign error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
