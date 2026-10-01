from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CampaignValidation:
    cases: list[dict[str, Any]]
    manifest: dict[str, Any] | None
    errors: list[str]

    @property
    def valid(self) -> bool:
        return not self.errors


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_index(repo: Path) -> dict[str, Any]:
    path = repo / "instances" / "index.json"
    if not path.is_file():
        raise ValueError(f"missing frozen index: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != 1:
        raise ValueError("unsupported or malformed frozen index")
    records = raw.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("frozen index has no records")
    if raw.get("case_count") != len(records):
        raise ValueError("frozen index case_count mismatch")
    orders: set[int] = set()
    names: set[str] = set()
    files: set[str] = set()
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"index record {position} is not an object")
        order = record.get("order")
        name = record.get("name")
        instance_file = record.get("file")
        if type(order) is not int or order != position:
            raise ValueError(f"index record {position} has invalid order {order!r}")
        if not isinstance(name, str) or not name:
            raise ValueError(f"index record {position} has invalid name")
        if not isinstance(instance_file, str) or not instance_file:
            raise ValueError(f"index record {position} has invalid input path")
        if order in orders or name in names or instance_file in files:
            raise ValueError("frozen index contains a duplicate order, name, or input path")
        orders.add(order)
        names.add(name)
        files.add(instance_file)
        input_path = repo / "instances" / instance_file
        if not input_path.is_file():
            raise ValueError(f"frozen input is missing: {input_path}")
    return raw


def index_sha256(repo: Path) -> str:
    return sha256_file(repo / "instances" / "index.json")


def case_filename(record: dict[str, Any]) -> str:
    return f"{record['order']:03d}-{record['name']}.json"


def case_evaluation_config(record: dict[str, Any], *, oracle_state_cap: int, oracle_cpu_cap: float) -> dict[str, Any]:
    return {
        "exact": bool(record["exact"]),
        "certificate": bool(record["certificate"]),
        "oracle": bool(record["oracle"]),
        "semantic": bool(record["semantic"]),
        "oracle_state_cap": int(oracle_state_cap),
        "oracle_case_cpu_cap_seconds": float(oracle_cpu_cap),
    }


def case_identity(repo: Path, record: dict[str, Any]) -> dict[str, Any]:
    input_path = repo / "instances" / record["file"]
    return {
        "index_order": record["order"],
        "name": record["name"],
        "group": record["group"],
        "instance_file": record["file"],
        "input_sha256": sha256_file(input_path),
    }


def bind_case_result(
    repo: Path,
    record: dict[str, Any],
    result: dict[str, Any],
    *,
    oracle_state_cap: int,
    oracle_cpu_cap: float,
) -> dict[str, Any]:
    result = dict(result)
    result["record_identity"] = case_identity(repo, record)
    result["evaluation_config"] = case_evaluation_config(
        record,
        oracle_state_cap=oracle_state_cap,
        oracle_cpu_cap=oracle_cpu_cap,
    )
    return result


def validate_case_result(
    repo: Path,
    record: dict[str, Any],
    result: Any,
    *,
    oracle_state_cap: int,
    oracle_cpu_cap: float,
    required_status: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["case result is not a JSON object"]
    expected_identity = case_identity(repo, record)
    expected_config = case_evaluation_config(
        record,
        oracle_state_cap=oracle_state_cap,
        oracle_cpu_cap=oracle_cpu_cap,
    )
    if result.get("record_identity") != expected_identity:
        errors.append("record identity/input digest mismatch")
    if result.get("evaluation_config") != expected_config:
        errors.append("evaluation configuration mismatch")
    if result.get("name") != record["name"]:
        errors.append("case name mismatch")
    if result.get("group") != record["group"]:
        errors.append("case group mismatch")
    if result.get("instance_file") != record["file"]:
        errors.append("instance path mismatch")
    if required_status is not None and result.get("status") != required_status:
        errors.append(f"case status is {result.get('status')!r}, expected {required_status!r}")
    metrics = result.get("metrics")
    if not isinstance(metrics, dict):
        errors.append("case metrics are missing")
    else:
        units = metrics.get("audit_units")
        cpu = metrics.get("case_body_cpu_seconds")
        components = metrics.get("audit_unit_components")
        if type(units) is not int or units < 0:
            errors.append("audit_units must be a nonnegative integer")
        if not isinstance(cpu, (int, float)) or isinstance(cpu, bool) or cpu < 0:
            errors.append("case_body_cpu_seconds must be nonnegative")
        if components is not None:
            if not isinstance(components, dict) or any(type(value) is not int or value < 0 for value in components.values()):
                errors.append("audit_unit_components must contain nonnegative integers")
            elif type(units) is int and units != sum(components.values()):
                errors.append("audit_units does not equal the component sum")
    return errors


def validate_complete_campaign(repo: Path, path: Path) -> CampaignValidation:
    errors: list[str] = []
    if not path.exists():
        return CampaignValidation([], None, [f"campaign directory does not exist: {path}"])
    if not path.is_dir():
        return CampaignValidation([], None, [f"campaign path is not a directory: {path}"])
    cases_dir = path / "cases"
    manifest_path = path / "manifest.json"
    if not cases_dir.is_dir():
        errors.append("campaign cases directory is missing")
    if not manifest_path.is_file():
        errors.append("campaign manifest is missing")
    if errors:
        return CampaignValidation([], None, errors)

    try:
        index = load_index(repo)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return CampaignValidation([], None, [str(exc)])
    records = index["records"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CampaignValidation([], None, [f"cannot read campaign manifest: {exc}"])
    if not isinstance(manifest, dict):
        return CampaignValidation([], None, ["campaign manifest is not an object"])

    if manifest.get("index_sha256") != index_sha256(repo):
        errors.append("manifest is not bound to the current frozen index")
    config = manifest.get("campaign_config")
    if not isinstance(config, dict):
        errors.append("manifest campaign_config is missing")
        oracle_state_cap = -1
        oracle_cpu_cap = -1.0
        audit_unit_cap = -1
        case_body_cpu_cap = -1.0
    else:
        oracle_state_cap = config.get("oracle_state_cap")
        oracle_cpu_cap = config.get("oracle_case_cpu_cap_seconds")
        audit_unit_cap = config.get("audit_unit_cap")
        case_body_cpu_cap = config.get("cumulative_case_body_cpu_cap_seconds")
        if type(oracle_state_cap) is not int or oracle_state_cap <= 0:
            errors.append("manifest oracle_state_cap is invalid")
            oracle_state_cap = -1
        if not isinstance(oracle_cpu_cap, (int, float)) or isinstance(oracle_cpu_cap, bool) or oracle_cpu_cap <= 0:
            errors.append("manifest oracle_case_cpu_cap_seconds is invalid")
            oracle_cpu_cap = -1.0
        if type(audit_unit_cap) is not int or audit_unit_cap <= 0:
            errors.append("manifest audit_unit_cap is invalid")
            audit_unit_cap = -1
        if not isinstance(case_body_cpu_cap, (int, float)) or isinstance(case_body_cpu_cap, bool) or case_body_cpu_cap <= 0:
            errors.append("manifest cumulative_case_body_cpu_cap_seconds is invalid")
            case_body_cpu_cap = -1.0

    if manifest.get("complete") is not True or manifest.get("terminal_status") != "complete":
        errors.append("campaign manifest is not complete")
    if manifest.get("expected_cases") != len(records):
        errors.append("manifest expected_cases mismatch")
    if manifest.get("checked_cases") != len(records):
        errors.append("manifest checked_cases mismatch")
    if manifest.get("incomplete_cases", 0) != 0:
        errors.append("manifest retains incomplete cases")

    expected_names = [case_filename(record) for record in records]
    observed_paths = sorted(cases_dir.glob("*.json"))
    observed_names = [item.name for item in observed_paths]
    if observed_names != sorted(expected_names):
        missing = sorted(set(expected_names) - set(observed_names))
        extra = sorted(set(observed_names) - set(expected_names))
        if missing:
            errors.append(f"missing case files: {missing[:5]}{' ...' if len(missing) > 5 else ''}")
        if extra:
            errors.append(f"unexpected case files: {extra[:5]}{' ...' if len(extra) > 5 else ''}")
    if not observed_paths:
        errors.append("campaign contains no case records")

    cases: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    path_by_name = {item.name: item for item in observed_paths}
    for record in records:
        filename = case_filename(record)
        case_path = path_by_name.get(filename)
        if case_path is None:
            continue
        try:
            result = json.loads(case_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read {filename}: {exc}")
            continue
        case_errors = validate_case_result(
            repo,
            record,
            result,
            oracle_state_cap=int(oracle_state_cap),
            oracle_cpu_cap=float(oracle_cpu_cap),
            required_status="checked",
        )
        errors.extend(f"{filename}: {message}" for message in case_errors)
        if result.get("name") in seen_names:
            errors.append(f"duplicate case identity {result.get('name')!r}")
        else:
            seen_names.add(result.get("name"))
        cases.append(result)

    if len(cases) != len(records):
        errors.append(f"loaded {len(cases)} of {len(records)} expected case records")
    cumulative_units = sum(
        int(case.get("metrics", {}).get("audit_units", 0))
        for case in cases
        if type(case.get("metrics", {}).get("audit_units")) is int
    )
    cumulative_cpu = sum(
        float(case.get("metrics", {}).get("case_body_cpu_seconds", 0.0))
        for case in cases
        if isinstance(case.get("metrics", {}).get("case_body_cpu_seconds"), (int, float))
        and not isinstance(case.get("metrics", {}).get("case_body_cpu_seconds"), bool)
    )
    if manifest.get("cumulative_audit_units") != cumulative_units:
        errors.append("manifest cumulative_audit_units mismatch")
    manifest_cpu = manifest.get("cumulative_case_body_cpu_seconds")
    if not isinstance(manifest_cpu, (int, float)) or isinstance(manifest_cpu, bool) or abs(float(manifest_cpu) - cumulative_cpu) > 1e-9:
        errors.append("manifest cumulative_case_body_cpu_seconds mismatch")
    if audit_unit_cap > 0 and cumulative_units > audit_unit_cap:
        errors.append("complete campaign exceeds the audit-unit cap")
    if case_body_cpu_cap > 0 and cumulative_cpu > case_body_cpu_cap:
        errors.append("complete campaign exceeds the cumulative case-body CPU cap")
    return CampaignValidation(cases, manifest, errors)
