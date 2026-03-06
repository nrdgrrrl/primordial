#!/usr/bin/env python3
"""Run machine-readable milestone acceptance checks.

The acceptance files use a deliberately small, JSON-compatible subset of YAML.
That keeps this runner stdlib-only while still letting the repository use
`.yaml` files for milestone definitions.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 120
SUPPORTED_CHECK_TYPES = {"command", "file_exists", "json_assert"}


@dataclass
class CheckResult:
    check_id: str
    status: str
    detail: str
    duration_seconds: float


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run milestone acceptance checks.",
    )
    parser.add_argument(
        "acceptance",
        nargs="?",
        help="Path to an acceptance YAML file. Defaults to the current milestone.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the discovered checks without executing them.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    acceptance_path = _resolve_acceptance_path(repo_root, args.acceptance)
    payload = _load_acceptance_payload(acceptance_path)
    _validate_acceptance_payload(payload, acceptance_path)

    milestone = payload["milestone"]
    checks = payload["checks"]

    print(
        f"Milestone {milestone['id']}: {milestone['title']}\n"
        f"Acceptance: {acceptance_path.relative_to(repo_root)}"
    )

    spec_path = repo_root / milestone["spec"]
    if not spec_path.exists():
        print(f"[FAIL] milestone.spec missing: {milestone['spec']}")
        return 1

    if args.list:
        for check in checks:
            print(f"- {check['id']} [{check['type']}] {check.get('description', '')}".rstrip())
        return 0

    results: list[CheckResult] = []
    for check in checks:
        started = time.perf_counter()
        try:
            detail = _run_check(check, repo_root)
            status = "PASS"
        except CheckFailure as exc:
            detail = exc.message
            status = "FAIL"
        duration_seconds = time.perf_counter() - started
        results.append(
            CheckResult(
                check_id=check["id"],
                status=status,
                detail=detail,
                duration_seconds=duration_seconds,
            )
        )

    failed = [result for result in results if result.status == "FAIL"]
    for result in results:
        print(
            f"[{result.status}] {result.check_id} "
            f"({result.duration_seconds:.2f}s) - {result.detail}"
        )

    if not failed:
        print(f"All {len(results)} checks passed.")
        return 0

    print(f"{len(failed)} of {len(results)} checks failed.")
    print("Missing work:")
    for result in failed:
        print(f"- {result.check_id}: {result.detail}")
    return 1


class CheckFailure(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _resolve_acceptance_path(repo_root: Path, requested: str | None) -> Path:
    if requested:
        candidate = Path(requested)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        return candidate

    default_path = repo_root / "docs" / "acceptance.yaml"
    if default_path.exists():
        return default_path

    milestone_paths = sorted(
        (repo_root / "docs").glob("acceptance_M*.yaml"),
        key=_milestone_sort_key,
    )
    if milestone_paths:
        return milestone_paths[-1]

    raise SystemExit("No acceptance file found. Pass one explicitly or add docs/acceptance_M*.yaml.")


def _milestone_sort_key(path: Path) -> tuple[int, str]:
    stem = path.stem
    digits = "".join(ch for ch in stem if ch.isdigit())
    return (int(digits) if digits else -1, stem)


def _load_acceptance_payload(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"Acceptance file not found: {path}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{path} is not valid JSON-compatible YAML: {exc.msg} at line {exc.lineno} column {exc.colno}."
        ) from exc

    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a top-level mapping/object.")
    return payload


def _validate_acceptance_payload(payload: dict[str, Any], path: Path) -> None:
    required_top_level = {"schema_version", "milestone", "checks"}
    missing = required_top_level - payload.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise SystemExit(f"{path} is missing required keys: {names}")

    if payload["schema_version"] != 1:
        raise SystemExit(f"{path} has unsupported schema_version: {payload['schema_version']}")

    milestone = payload["milestone"]
    if not isinstance(milestone, dict):
        raise SystemExit(f"{path} milestone must be an object.")
    for key in ("id", "title", "spec"):
        if key not in milestone:
            raise SystemExit(f"{path} milestone is missing '{key}'.")

    checks = payload["checks"]
    if not isinstance(checks, list) or not checks:
        raise SystemExit(f"{path} checks must be a non-empty list.")

    seen_ids: set[str] = set()
    for check in checks:
        if not isinstance(check, dict):
            raise SystemExit(f"{path} has a non-object check entry.")
        for key in ("id", "type"):
            if key not in check:
                raise SystemExit(f"{path} has a check missing '{key}'.")
        if check["id"] in seen_ids:
            raise SystemExit(f"{path} has a duplicate check id: {check['id']}")
        seen_ids.add(check["id"])
        if check["type"] not in SUPPORTED_CHECK_TYPES:
            raise SystemExit(
                f"{path} check '{check['id']}' has unsupported type '{check['type']}'."
            )


def _run_check(check: dict[str, Any], repo_root: Path) -> str:
    check_type = check["type"]
    if check_type == "command":
        return _run_command_check(check, repo_root)
    if check_type == "file_exists":
        return _run_file_exists_check(check, repo_root)
    if check_type == "json_assert":
        return _run_json_assert_check(check, repo_root)
    raise CheckFailure(f"unsupported check type: {check_type}")


def _run_command_check(check: dict[str, Any], repo_root: Path) -> str:
    command = check["run"]
    timeout_seconds = int(check.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    cwd = repo_root / check.get("cwd", ".")
    expect = check.get("expect", {})
    expected_exit_code = int(expect.get("exit_code", 0))

    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CheckFailure(
            f"command timed out after {timeout_seconds}s: {command}"
        ) from exc

    if completed.returncode != expected_exit_code:
        message = (
            f"expected exit {expected_exit_code}, got {completed.returncode}: {command}"
        )
        tail = _command_output_tail(completed.stdout, completed.stderr)
        if tail:
            message = f"{message} | output: {tail}"
        raise CheckFailure(message)

    required_stdout = expect.get("stdout_contains", [])
    if isinstance(required_stdout, str):
        required_stdout = [required_stdout]
    for needle in required_stdout:
        if needle not in completed.stdout:
            raise CheckFailure(
                f"stdout missing expected text '{needle}': {command}"
            )

    return f"command succeeded: {command}"


def _run_file_exists_check(check: dict[str, Any], repo_root: Path) -> str:
    path = repo_root / check["path"]
    if not path.exists():
        raise CheckFailure(f"missing required path: {check['path']}")
    return f"path exists: {check['path']}"


def _run_json_assert_check(check: dict[str, Any], repo_root: Path) -> str:
    path = repo_root / check["path"]
    if not path.exists():
        raise CheckFailure(f"JSON file not found: {check['path']}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckFailure(
            f"{check['path']} is not valid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}"
        ) from exc

    assertions = check.get("assertions", [])
    if not assertions:
        raise CheckFailure(f"json_assert check '{check['id']}' has no assertions")

    for assertion in assertions:
        _evaluate_assertion(payload, assertion)

    return f"{len(assertions)} assertions passed for {check['path']}"


def _evaluate_assertion(payload: Any, assertion: dict[str, Any]) -> None:
    path = assertion["path"]
    op = assertion["op"]
    actual = _get_json_path(payload, path)
    expected = assertion.get("value")

    if op == "exists":
        return
    if op == "eq" and actual == expected:
        return
    if op == "ne" and actual != expected:
        return
    if op == "gt" and actual > expected:
        return
    if op == "ge" and actual >= expected:
        return
    if op == "lt" and actual < expected:
        return
    if op == "le" and actual <= expected:
        return
    if op == "contains" and expected in actual:
        return

    if op not in {"exists", "eq", "ne", "gt", "ge", "lt", "le", "contains"}:
        raise CheckFailure(f"unsupported assertion op '{op}' for path '{path}'")

    expected_text = "" if op == "exists" else f" {op} {expected!r}"
    raise CheckFailure(f"assertion failed: {path} -> {actual!r} does not satisfy{expected_text}")


def _get_json_path(payload: Any, path: str) -> Any:
    current = payload
    for segment in path.split("."):
        if isinstance(current, list):
            try:
                index = int(segment)
            except ValueError as exc:
                raise CheckFailure(
                    f"cannot index list with non-integer segment '{segment}' in path '{path}'"
                ) from exc
            try:
                current = current[index]
            except IndexError as exc:
                raise CheckFailure(f"list index out of range in path '{path}'") from exc
            continue

        if not isinstance(current, dict):
            raise CheckFailure(
                f"path '{path}' stepped into non-object value before segment '{segment}'"
            )
        if segment not in current:
            raise CheckFailure(f"missing JSON path '{path}'")
        current = current[segment]
    return current


def _command_output_tail(stdout: str, stderr: str, *, max_chars: int = 240) -> str:
    text = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part.strip())
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


if __name__ == "__main__":
    raise SystemExit(main())
