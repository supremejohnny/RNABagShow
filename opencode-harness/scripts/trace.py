#!/usr/bin/env python3
"""Structured execution trace generator.

Generates and validates trace JSON files for harness agent runs.
Never copies secrets, credentials, PHI, or source bodies into traces.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from patch_collector import collect_patch


TRACE_SCHEMA_VERSION = 1

REQUIRED_FIELDS = [
    "schema_version",
    "run_id",
    "task_id",
    "phase",
    "agent",
    "provider",
    "model",
    "started_at",
    "finished_at",
    "git_head",
    "baseline_diff_hash",
    "input_artifacts",
    "output_artifacts",
    "actions",
    "commands",
    "validation",
    "usage",
    "result",
    "failure_reason",
    "next_action",
]

USAGE_FIELDS = {
    "input_tokens", "output_tokens", "reasoning_tokens",
    "cache_read_tokens", "cost",
}

PHASE_VALUES = {
    "architect", "coding", "review", "debug", "audit",
    "validate", "repair",
}

AGENT_VALUES = {
    "architect", "coding", "review", "debug", "final-audit",
}


def generate_run_id():
    return secrets.token_hex(8)


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def get_git_head(repo_root=None):
    try:
        cmd = ["git", "rev-parse", "HEAD"]
        if repo_root:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)
        else:
            result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def get_diff_hash(repo_root=None):
    try:
        import hashlib
        root = os.path.abspath(repo_root or ".")
        return hashlib.sha256(collect_patch(root)).hexdigest()[:16]
    except Exception:
        pass
    return ""


def make_filename(timestamp_str, task_id, role, run_id):
    safe_task = "".join(c if c.isalnum() or c in "-_" else "_" for c in task_id)[:64]
    safe_role = role.replace(" ", "-").lower()
    return f"{timestamp_str}-{safe_task}-{safe_role}-{run_id}.json"


def validate_trace(trace):
    errors = []

    if not isinstance(trace, dict):
        return ["trace is not a JSON object"]

    for field in REQUIRED_FIELDS:
        if field not in trace:
            errors.append(f"missing required field: {field}")

    if trace.get("schema_version") != TRACE_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {TRACE_SCHEMA_VERSION}, "
            f"got {trace.get('schema_version')}"
        )

    if trace.get("phase") not in PHASE_VALUES:
        errors.append(f"invalid phase: {trace.get('phase')}")
    if trace.get("agent") not in AGENT_VALUES:
        errors.append(f"invalid agent: {trace.get('agent')}")

    usage = trace.get("usage", {})
    if not isinstance(usage, dict):
        errors.append("usage must be a JSON object")
    else:
        for key in USAGE_FIELDS:
            # Older trace producers did not expose every counter. Missing is
            # semantically the same as unknown and remains backward compatible.
            val = usage.get(key)
            if val is not None and not isinstance(val, (int, float)):
                errors.append(
                    f"usage.{key} must be null or a number, got {type(val).__name__}"
                )

    for list_field in [
        "input_artifacts", "output_artifacts",
        "actions", "commands", "validation",
    ]:
        val = trace.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"{list_field} must be a JSON array")

    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Generate and validate structured execution traces."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate a new trace file.")
    gen.add_argument("--task-id", required=True, help="Task identifier.")
    gen.add_argument("--phase", required=True,
                     choices=sorted(PHASE_VALUES),
                     help="Execution phase.")
    gen.add_argument("--agent", required=True,
                     choices=sorted(AGENT_VALUES),
                     help="Agent role.")
    gen.add_argument("--provider", required=True, help="Model provider.")
    gen.add_argument("--model", required=True, help="Model identifier.")
    gen.add_argument("--output", help="Output file path.")
    gen.add_argument("--repo-root", default=".",
                     help="Repository root directory.")
    gen.add_argument("--result", default="", help="Run result summary.")
    gen.add_argument("--failure-reason", default="",
                     help="Failure description.")
    gen.add_argument("--next-action", default="",
                     help="Next recommended action.")
    gen.add_argument("--input-artifacts", nargs="*", default=[],
                     help="Input artifact paths.")
    gen.add_argument("--output-artifacts", nargs="*", default=[],
                     help="Output artifact paths.")
    gen.add_argument("--actions", nargs="*", default=[],
                     help="Actions performed.")
    gen.add_argument("--commands", nargs="*", default=[],
                     help="Commands executed.")
    gen.add_argument("--validation", nargs="*", default=[],
                     help="Validation results.")

    val_cmd = sub.add_parser("validate", help="Validate an existing trace file.")
    val_cmd.add_argument("trace_file", help="Path to trace JSON file.")

    info = sub.add_parser("filename", help="Generate a trace filename.")
    info.add_argument("--timestamp", default=None, help="ISO timestamp.")
    info.add_argument("--task-id", required=True)
    info.add_argument("--role", required=True)
    info.add_argument("--run-id", default=None)

    args = parser.parse_args()

    if args.command == "generate":
        run_id = generate_run_id()
        ts = timestamp()
        repo_root = os.path.abspath(args.repo_root)
        git_head = get_git_head(repo_root)
        diff_hash = get_diff_hash(repo_root)

        trace = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "run_id": run_id,
            "task_id": args.task_id,
            "phase": args.phase,
            "agent": args.agent,
            "provider": args.provider,
            "model": args.model,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": "",
            "git_head": git_head,
            "baseline_diff_hash": diff_hash,
            "input_artifacts": args.input_artifacts,
            "output_artifacts": args.output_artifacts,
            "actions": args.actions,
            "commands": args.commands,
            "validation": args.validation,
            "usage": {
                "input_tokens": None,
                "output_tokens": None,
                "reasoning_tokens": None,
                "cache_read_tokens": None,
                "cost": None,
            },
            "result": args.result,
            "failure_reason": args.failure_reason,
            "next_action": args.next_action,
        }

        errors = validate_trace(trace)
        if errors:
            print("Trace validation errors:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            sys.exit(1)

        filename = make_filename(ts, args.task_id, args.agent, run_id)
        output_path = args.output or filename

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(trace, f, indent=2, ensure_ascii=False)
            f.write("\n")

        print(f"Trace written: {output_path}")
        print(f"  run_id: {run_id}")

    elif args.command == "validate":
        path = Path(args.trace_file)
        if not path.exists():
            print(f"ERROR: file not found: {args.trace_file}", file=sys.stderr)
            sys.exit(66)
        try:
            trace = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)

        errors = validate_trace(trace)
        if errors:
            print("Validation FAILED:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            sys.exit(1)
        print("PASS: trace is valid.")

    elif args.command == "filename":
        ts = args.timestamp or timestamp()
        rid = args.run_id or generate_run_id()
        name = make_filename(ts, args.task_id, args.role, rid)
        print(name)


if __name__ == "__main__":
    main()
