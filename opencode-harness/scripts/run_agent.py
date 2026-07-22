#!/usr/bin/env python3
"""Deterministic, artifact-driven OpenCode role runner.

Coding runs in the source worktree. Review and Debug run in a disposable,
read-only-by-contract artifact bundle. OpenCode JSON events are parsed by this
wrapper; raw prompts, source bodies, tool output, and error logs are never
written to execution traces.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
HARNESS_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from patch_collector import collect_patch  # noqa: E402
from trace import make_filename, validate_trace  # noqa: E402

CODING_MODEL = "deepseek/deepseek-v4-pro"
CODING_FALLBACK_MODEL = CODING_MODEL
REVIEW_MODEL = "doubaoglm/glm-5-2-260617"
DEBUG_MODEL = REVIEW_MODEL
FORBIDDEN_PREFIX = "lpc/"


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _get_opencode():
    return shutil.which("opencode")


def _opencode_models():
    opencode = _get_opencode()
    if not opencode:
        return None
    try:
        result = subprocess.run(
            [opencode, "models"], capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _model_available(model_name):
    output = _opencode_models()
    if output is None:
        return False
    return model_name in {line.strip() for line in output.splitlines()}


def _check_model(model_name, role):
    if model_name.startswith(FORBIDDEN_PREFIX):
        return False, f"FAIL: {role} must not use forbidden model prefix {FORBIDDEN_PREFIX!r}"
    if not _model_available(model_name):
        return False, f"FAIL: required {role} model {model_name} not found in `opencode models`"
    return True, ""


def generate_run_id():
    return secrets.token_hex(8)


def _task_root(repo_root, task_id):
    ai = Path(repo_root) / ".ai"
    if ai.is_dir():
        return ai / "TASKS" / task_id
    return Path(repo_root) / ".agent-runs" / "tasks" / task_id


def _determine_report_path(repo_root, task_id, role):
    ai = Path(repo_root) / ".ai"
    if ai.is_dir():
        if role == "review":
            return str(ai / "REVIEWS" / task_id / "REVIEW.md")
        return str(ai / "TASKS" / task_id / "DEBUG_REPORT.md")
    base = Path(repo_root) / ".agent-runs"
    if role == "review":
        return str(base / "reviews" / task_id / "REVIEW.md")
    return str(base / "tasks" / task_id / "DEBUG_REPORT.md")


def _determine_trace_dir(repo_root):
    ai = Path(repo_root) / ".ai"
    return str(ai / "trace" if ai.is_dir() else Path(repo_root) / ".agent-runs" / "traces")


def _git_head(repo_root):
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _patch_hash(repo_root):
    return hashlib.sha256(collect_patch(repo_root)).hexdigest()[:16]


def _artifact_label(path, repo_root):
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(Path(repo_root).resolve()))
    except ValueError:
        return Path(path).name


def parse_opencode_events(stdout):
    """Return final text, token usage, safe actions, and session id.

    Token counters are summed across step-finish events. When OpenCode does not
    report usage, every usage field remains null rather than being estimated.
    """
    messages = OrderedDict()
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cache_read_tokens": 0,
        "cost": 0.0,
    }
    usage_seen = False
    actions = []
    session_id = None

    for raw_line in stdout.splitlines():
        try:
            event = json.loads(raw_line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        session_id = event.get("sessionID") or part.get("sessionID") or session_id
        event_type = event.get("type") or part.get("type")

        if event_type == "text" and isinstance(part.get("text"), str):
            message_id = part.get("messageID") or f"event-{len(messages)}"
            messages[message_id] = messages.get(message_id, "") + part["text"]

        if event_type in {"tool_use", "tool"} or part.get("type") == "tool":
            tool = part.get("tool") or event.get("tool")
            action = f"tool:{tool}" if isinstance(tool, str) else ""
            if action and action not in actions:
                actions.append(action)

        if event_type in {"step_finish", "step-finish"} or part.get("type") == "step-finish":
            tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
            cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
            mapping = {
                "input_tokens": tokens.get("input"),
                "output_tokens": tokens.get("output"),
                "reasoning_tokens": tokens.get("reasoning"),
                "cache_read_tokens": cache.get("read"),
                "cost": part.get("cost"),
            }
            for key, value in mapping.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    totals[key] += value
                    usage_seen = True

    final_text = ""
    for text in messages.values():
        if text.strip():
            final_text = text.strip()
    usage = totals if usage_seen else {key: None for key in totals}
    return final_text, usage, actions, session_id


def _write_trace(repo_root, *, run_id, task_id, role, model, started_at,
                 baseline_hash, input_artifacts, output_artifacts, actions,
                 usage, result, failure_reason="", next_action="",
                 session_id=None):
    trace = {
        "schema_version": 1,
        "run_id": run_id,
        "task_id": task_id,
        "phase": role,
        "agent": role,
        "provider": model.split("/", 1)[0],
        "model": model,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "git_head": _git_head(repo_root),
        "baseline_diff_hash": baseline_hash,
        "input_artifacts": [x for x in input_artifacts if x],
        "output_artifacts": [x for x in output_artifacts if x],
        "actions": actions,
        "commands": [f"opencode run --model {model} --agent " + ("build" if role == "coding" else "plan")],
        "validation": [],
        "usage": usage,
        "result": result,
        "failure_reason": failure_reason,
        "next_action": next_action,
    }
    if session_id:
        trace["session_id"] = session_id
    errors = validate_trace(trace)
    if errors:
        raise ValueError("invalid trace: " + "; ".join(errors))
    trace_dir = Path(_determine_trace_dir(repo_root))
    trace_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = trace_dir / make_filename(stamp, task_id, role, run_id)
    path.write_text(json.dumps(trace, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _record_status_run(repo_root, task_id, role, run_id)
    return str(path)


def _record_status_run(repo_root, task_id, role, run_id):
    status_path = _task_root(repo_root, task_id) / "STATUS.json"
    if not status_path.is_file():
        return
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
        runs = data.setdefault("runs", [])
        if run_id not in runs:
            runs.append(run_id)
        artifacts = data.setdefault("artifacts", {})
        test_results = _task_root(repo_root, task_id) / "TEST_RESULTS.md"
        if test_results.is_file():
            artifacts["test_results"] = _artifact_label(test_results, repo_root)
        if role == "review":
            report = Path(_determine_report_path(repo_root, task_id, "review"))
            if report.is_file():
                artifacts["review"] = _artifact_label(report, repo_root)
        if role == "debug":
            report = Path(_determine_report_path(repo_root, task_id, "debug"))
            if report.is_file():
                artifacts["debug_report"] = _artifact_label(report, repo_root)
        data["updated_at"] = _utc_now()
        status_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, TypeError):
        # Trace generation must not destroy an otherwise successful agent run
        # merely because an optional status file is malformed.
        return


def _create_isolation_bundle(repo_root, task_id, role):
    bundle = Path(tempfile.mkdtemp(prefix=f"opencode-harness-{role}-"))
    specs = bundle / "specs"
    diffs = bundle / "diffs"
    results = bundle / "results"
    specs.mkdir()
    diffs.mkdir()
    results.mkdir()

    ai = Path(repo_root) / ".ai"
    for name in ("PROJECT.md", "ARCHITECTURE.md", "CONVENTIONS.md"):
        src = ai / name
        if src.is_file():
            shutil.copy2(src, specs / name)

    task_dir = _task_root(repo_root, task_id)
    if task_dir.is_dir():
        for src in task_dir.iterdir():
            if src.is_file() and src.name != "STATUS.json":
                target = results if src.name in {"TEST_RESULTS.md", "DEBUG_REPORT.md"} else specs
                shutil.copy2(src, target / src.name)

    if role == "debug":
        previous_review = Path(_determine_report_path(repo_root, task_id, "review"))
        if previous_review.is_file():
            shutil.copy2(previous_review, results / "REVIEW.md")

    (diffs / "implementation.diff").write_bytes(collect_patch(repo_root))
    template = HARNESS_DIR / "assets" / "templates" / ("REVIEW.md" if role == "review" else "DEBUG_REPORT.md")
    if template.is_file():
        shutil.copy2(template, specs / "REPORT_FORMAT.md")

    readme = (
        f"Isolated {role.upper()} bundle for task {task_id}.\n"
        "Read only specs/, diffs/, and results/. Do not modify files.\n"
        "Return the complete report as the final response only.\n"
        "Do not request or inspect the source worktree, Git history, secrets, or unrelated files.\n"
    )
    (bundle / "README.txt").write_text(readme, encoding="utf-8")
    return str(bundle)


def _run_process(command, timeout=600):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout), ""
    except subprocess.TimeoutExpired:
        return None, "run timed out"
    except OSError as exc:
        return None, f"run error: {exc}"


def run_coding(repo_root, task_id, task_file=None, task_content=None):
    ok, message = _check_model(CODING_MODEL, "Coding")
    if not ok:
        return 1, message, None, None
    opencode = _get_opencode()
    if not opencode:
        return 1, "FAIL: opencode not available on PATH", None, None
    if task_content is None and task_file:
        try:
            task_content = Path(task_file).read_text(encoding="utf-8")
        except OSError as exc:
            return 1, f"FAIL: cannot read task file: {exc}", None, None
    if not task_content:
        return 1, "FAIL: no task content provided", None, None

    prompt = (
        "Implement the bounded task below in the current Git worktree. Read applicable AGENTS.md "
        "and the named task artifacts first. Preserve unrelated changes. Do not commit, push, "
        "reset, rebase, call Codex, or expose secrets. Add relevant tests and run bounded validation. "
        f"Write concise, sanitized validation evidence to {_task_root(repo_root, task_id) / 'TEST_RESULTS.md'}. "
        "Finish with changed files, commands/results, and remaining issues.\n\n" + task_content
    )
    run_id = generate_run_id()
    started = _utc_now()
    before = _patch_hash(repo_root)
    command = [
        opencode, "run", "--auto", "--format", "json", "--model", CODING_MODEL,
        "--agent", "build", "--dir", repo_root, prompt,
    ]
    process, process_error = _run_process(command)
    stdout = process.stdout if process else ""
    final_text, usage, actions, session_id = parse_opencode_events(stdout)
    exit_code = process.returncode if process else 1
    failure = process_error or (f"OpenCode exit status {exit_code}" if exit_code else "")
    result = "passed" if exit_code == 0 else "failed"
    trace_path = _write_trace(
        repo_root, run_id=run_id, task_id=task_id, role="coding", model=CODING_MODEL,
        started_at=started, baseline_hash=before,
        input_artifacts=[_artifact_label(task_file, repo_root) if task_file else "inline-task"],
        output_artifacts=["working-tree patch"], actions=actions, usage=usage,
        result=result, failure_reason=failure,
        next_action="run bounded validation" if exit_code == 0 else "inspect failure and route to Debug",
        session_id=session_id,
    )
    unchanged = before == _patch_hash(repo_root)
    if exit_code:
        return exit_code, f"FAIL: Coding {failure}. Trace: {trace_path}", run_id, unchanged
    summary = "PASS: Coding completed"
    if not final_text:
        summary += " (OpenCode emitted no final text)"
    return 0, f"{summary}. Trace: {trace_path}", run_id, unchanged


def _validate_report(role, report):
    if not report.strip():
        return "no final text report"
    if role == "review":
        verdicts = re.findall(r"(?mi)^Verdict:\s*(PASS|CHANGES_REQUIRED|BLOCKED)\s*$", report)
        if len(verdicts) != 1:
            return "review must contain exactly one anchored Verdict: PASS, CHANGES_REQUIRED, or BLOCKED"
    else:
        lowered = report.lower()
        required = ("failure reason", "proposed fix", "affected files")
        missing = [heading for heading in required if heading not in lowered]
        if missing:
            return "debug report missing section(s): " + ", ".join(missing)
    return ""


def _normalize_report(role, report):
    """Drop conversational preamble while preserving the returned report."""
    heading = "# Review" if role == "review" else "# Debug"
    position = report.find(heading)
    return report[position:].strip() if position >= 0 else report.strip()


def _run_review_or_debug(repo_root, task_id, role):
    model = REVIEW_MODEL if role == "review" else DEBUG_MODEL
    ok, message = _check_model(model, role.capitalize())
    if not ok:
        return 1, message, None
    opencode = _get_opencode()
    if not opencode:
        return 1, "FAIL: opencode not available on PATH", None

    bundle = _create_isolation_bundle(repo_root, task_id, role)
    run_id = generate_run_id()
    started = _utc_now()
    baseline = _patch_hash(repo_root)
    prompt = (
        f"Read README.txt and the bounded artifacts. Produce a {role} report matching "
        "specs/REPORT_FORMAT.md. Return the complete Markdown report as your final response only. "
        "Do not edit files. For review, avoid style-only suggestions and use exactly one verdict line."
    )
    command = [
        opencode, "run", "--pure", "--format", "json", "--model", model,
        "--agent", "plan", "--dir", bundle, prompt,
    ]
    try:
        process, process_error = _run_process(command)
        stdout = process.stdout if process else ""
        report, usage, actions, session_id = parse_opencode_events(stdout)
        report = _normalize_report(role, report)
        exit_code = process.returncode if process else 1
        report_error = _validate_report(role, report) if exit_code == 0 else ""
        if report_error:
            exit_code = 1
        failure = process_error or report_error or (f"OpenCode exit status {exit_code}" if exit_code else "")
        report_path = ""
        if exit_code == 0:
            report_path = _determine_report_path(repo_root, task_id, role)
            Path(report_path).parent.mkdir(parents=True, exist_ok=True)
            Path(report_path).write_text(report.rstrip() + "\n", encoding="utf-8")
        trace_path = _write_trace(
            repo_root, run_id=run_id, task_id=task_id, role=role, model=model,
            started_at=started, baseline_hash=baseline,
            input_artifacts=[f"isolated-{role}-bundle"],
            output_artifacts=[_artifact_label(report_path, repo_root)] if report_path else [],
            actions=actions, usage=usage, result="passed" if exit_code == 0 else "failed",
            failure_reason=failure,
            next_action="Codex final audit" if role == "review" and exit_code == 0 else "apply bounded repair",
            session_id=session_id,
        )
    finally:
        shutil.rmtree(bundle, ignore_errors=True)

    if exit_code:
        return exit_code, f"FAIL: {role.capitalize()} {failure}. Trace: {trace_path}", run_id
    return 0, f"PASS: {role.capitalize()} report written to {report_path}. Trace: {trace_path}", run_id


def run_review(repo_root, task_id):
    return _run_review_or_debug(repo_root, task_id, "review")


def run_debug(repo_root, task_id):
    return _run_review_or_debug(repo_root, task_id, "debug")


def main():
    parser = argparse.ArgumentParser(description="Run one deterministic OpenCode harness role.")
    parser.add_argument("role", choices=["coding", "review", "debug"])
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-file")
    parser.add_argument("--task-content")
    args = parser.parse_args()
    repo_root = os.path.abspath(args.repo_root)
    if not os.path.isdir(os.path.join(repo_root, ".git")):
        print("ERROR: not a Git repository: " + repo_root, file=sys.stderr)
        return 1
    if args.role == "coding":
        code, message, run_id, _ = run_coding(
            repo_root, args.task_id, task_file=args.task_file, task_content=args.task_content,
        )
    else:
        code, message, run_id = (run_review if args.role == "review" else run_debug)(repo_root, args.task_id)
    print(message)
    if run_id:
        print(f"run_id: {run_id}")
    return code


if __name__ == "__main__":
    sys.exit(main())
