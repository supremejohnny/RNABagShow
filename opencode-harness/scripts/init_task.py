#!/usr/bin/env python3
"""Safe task initializer for the harness artifact-driven workflow.

Creates a task directory under .ai/TASKS/<task-id>/ with route-required
templates and a STATUS.json. Refuses to overwrite any existing artifact.
Never silently initializes project-level .ai/ in an existing repository.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
HARNESS_DIR = SCRIPTS_DIR.parent
TEMPLATES_DIR = HARNESS_DIR / "assets" / "templates"

STATUS_TEMPLATE = {
    "task_id": "",
    "state": "routed",
    "risk_level": "",
    "repair_cycles": 0,
    "max_repair_cycles": 2,
    "updated_at": "",
    "artifacts": {
        "request": None,
        "spec": None,
        "implementation_plan": None,
        "acceptance": None,
        "test_results": None,
        "review": None,
        "debug_report": None,
    },
    "runs": [],
}

ROUTE_ARTIFACTS = {
    "LOW": ["REQUEST.md"],
    "MEDIUM": ["REQUEST.md", "SPEC.md", "TEST_RESULTS.md"],
    "HIGH": [
        "REQUEST.md", "SPEC.md", "IMPLEMENTATION_PLAN.md",
        "ACCEPTANCE.md", "TEST_RESULTS.md",
    ],
}

CHECK_REQUIRED_SIBLING = {
    "MEDIUM": ["SPEC.md"],
    "HIGH": ["SPEC.md", "IMPLEMENTATION_PLAN.md", "ACCEPTANCE.md"],
}


def _find_ai_dir(repo_root):
    candidates = [
        Path(repo_root) / ".ai",
        Path(repo_root) / ".agent-runs",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def _determine_base(repo_root, task_id):
    ai_dir = _find_ai_dir(repo_root)
    if ai_dir:
        return ai_dir / "TASKS" / task_id
    return Path(repo_root) / ".agent-runs" / "tasks" / task_id


def init_task(repo_root, task_id, risk_level, request_text=None, add_missing=False):
    risk_level = risk_level.upper()
    if risk_level not in ROUTE_ARTIFACTS:
        raise ValueError(f"Invalid risk level: {risk_level} (valid: LOW, MEDIUM, HIGH)")

    task_dir = _determine_base(repo_root, task_id)

    if task_dir.exists() and any(task_dir.iterdir()):
        existing = sorted(
            str(p.relative_to(task_dir)) for p in task_dir.iterdir()
        )
        if existing and not add_missing:
            return False, f"Task directory already exists with artifacts: {existing}"

    task_dir.mkdir(parents=True, exist_ok=True)

    created = []
    required = ROUTE_ARTIFACTS[risk_level]
    for artifact_name in required:
        dest = task_dir / artifact_name
        if dest.exists():
            continue

        template_path = TEMPLATES_DIR / artifact_name
        if template_path.exists():
            content = template_path.read_text(encoding="utf-8")
            content = content.replace("{{TASK_ID}}", task_id)
            dest.write_text(content, encoding="utf-8")
        else:
            dest.write_text(f"# {artifact_name.replace('.md', '')}: {task_id}\n\n", encoding="utf-8")
        created.append(artifact_name)

    if request_text:
        request_path = task_dir / "REQUEST.md"
        if "REQUEST.md" in created or not request_path.exists() or request_path.stat().st_size == 0:
            request_path.write_text(request_text.rstrip() + "\n", encoding="utf-8")

    status = dict(STATUS_TEMPLATE)
    status["task_id"] = task_id
    status["risk_level"] = risk_level
    status["updated_at"] = datetime.now(timezone.utc).isoformat()

    for key in ["request", "spec", "implementation_plan", "acceptance", "test_results", "review", "debug_report"]:
        artifact_key = key.upper()
        if artifact_key == "IMPLEMENTATION_PLAN":
            artifact_key = "IMPLEMENTATION_PLAN.md"
        elif artifact_key == "ACCEPTANCE":
            artifact_key = "ACCEPTANCE.md"
        elif artifact_key == "DEBUG_REPORT":
            artifact_key = "DEBUG_REPORT.md"
        elif artifact_key == "TEST_RESULTS":
            artifact_key = "TEST_RESULTS.md"
        else:
            artifact_key = artifact_key + ".md"

        dest = task_dir / artifact_key
        if dest.exists():
            status["artifacts"][key] = str(dest)

    status_path = task_dir / "STATUS.json"
    if status_path.exists():
        pass
    else:
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2, ensure_ascii=False)
            f.write("\n")
        if "STATUS.json" not in created:
            created.append("STATUS.json")

    return True, f"Created {len(created)} artifact(s) at {task_dir}: {created}"


def check_route_requirements(repo_root, task_id, risk_level):
    task_dir = _determine_base(repo_root, task_id)
    missing = []
    for name in CHECK_REQUIRED_SIBLING.get(risk_level.upper(), []):
        path = task_dir / name
        if not path.exists():
            missing.append(name)
            continue
        content = path.read_text(encoding="utf-8").strip()
        if any(marker in content for marker in ("{{", "}}", "<!--")):
            missing.append(f"{name} (unresolved template markers)")
            continue
        substantive = [
            line.strip() for line in content.splitlines()
            if line.strip()
            and not line.lstrip().startswith("#")
            and not line.lstrip().startswith("- [ ]")
        ]
        if not substantive:
            missing.append(f"{name} (placeholder only)")
    return missing


def check_high_requirements(repo_root, task_id):
    """Compatibility API for callers of the first harness release."""
    return check_route_requirements(repo_root, task_id, "HIGH")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize a task directory with route-required artifacts and STATUS.json."
    )
    parser.add_argument("--task-id", required=True, help="Task identifier.")
    parser.add_argument("--risk-level", required=True, choices=["LOW", "MEDIUM", "HIGH"], help="Risk classification.")
    parser.add_argument("--repo-root", default=".", help="Repository root directory.")
    parser.add_argument("--request", help="Task request text to write into REQUEST.md.")
    parser.add_argument(
        "--add-missing", action="store_true",
        help="Add only missing artifacts; never overwrite existing files.",
    )
    parser.add_argument("--check-high", action="store_true", help="Check HIGH route requirements and exit.")
    parser.add_argument(
        "--check-required", choices=["MEDIUM", "HIGH"],
        help="Check completed Architect artifacts for the selected route and exit.",
    )
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    if not os.path.isdir(repo_root):
        print(f"ERROR: not a directory: {repo_root}", file=sys.stderr)
        sys.exit(1)

    if args.check_high or args.check_required:
        route = args.check_required or "HIGH"
        missing = check_route_requirements(repo_root, args.task_id, route)
        if missing:
            print(f"FAIL: {route} route missing required artifacts: {', '.join(missing)}")
            sys.exit(1)
        print(f"PASS: {route} route requirements satisfied.")
        sys.exit(0)

    success, message = init_task(
        repo_root, args.task_id, args.risk_level,
        request_text=args.request, add_missing=args.add_missing,
    )
    if not success:
        print(f"FAIL: {message}", file=sys.stderr)
        sys.exit(1)
    print(message)


if __name__ == "__main__":
    main()
