#!/usr/bin/env python3
"""Safely update per-task STATUS.json without shell interpolation."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def status_path(repo_root, task_id):
    for path in (
        Path(repo_root) / ".ai" / "TASKS" / task_id / "STATUS.json",
        Path(repo_root) / ".agent-runs" / "tasks" / task_id / "STATUS.json",
    ):
        if path.is_file():
            return path
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--state")
    parser.add_argument("--increment-repair", action="store_true")
    parser.add_argument("--check-repair-limit", action="store_true")
    args = parser.parse_args()
    path = status_path(args.repo_root, args.task_id)
    if not path:
        print("STATUS.json not found", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    if args.check_repair_limit:
        current = int(data.get("repair_cycles", 0))
        maximum = int(data.get("max_repair_cycles", 2))
        print(f"{current}/{maximum}")
        return 0 if current < maximum else 2
    if args.increment_repair:
        data["repair_cycles"] = int(data.get("repair_cycles", 0)) + 1
    if args.state:
        data["state"] = args.state
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
