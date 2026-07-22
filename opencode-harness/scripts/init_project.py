#!/usr/bin/env python3
"""Initialize .ai/ project directory from reusable templates.

Creates the .ai/ layout with template stubs. Never overwrites existing
files. Maps existing AGENTS.md / README content into stubs when present
instead of duplicating.
"""

import argparse
import os
import sys
from pathlib import Path


TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "assets" / "templates"

AI_SUBDIRS = ["TASKS", "REVIEWS", "trace"]

PROJECT_FILES = {
    "PROJECT.md": "# Project Overview\n\n<!-- Describe the project purpose, tech stack, and domain context. -->\n",
    "ARCHITECTURE.md": "# Architecture\n\n<!-- Describe system architecture, components, and data flow. -->\n",
    "CONVENTIONS.md": "# Conventions\n\n<!-- Code conventions, naming, and patterns for this repository. -->\n",
}


def repo_has_file(target_dir, name):
    return (Path(target_dir) / name).exists()


def init_project(target_dir, force=False):
    ai_dir = Path(target_dir) / ".ai"
    repo = Path(target_dir)

    if ai_dir.exists():
        existing = sorted(
            str(p.relative_to(ai_dir)) for p in ai_dir.rglob("*") if p.is_file()
        )
        if existing:
            print(f".ai/ already exists with {len(existing)} file(s):")
            for f in existing:
                print(f"  {f}")
            if not force:
                print("Use --force to add only missing template stubs.")
                return False
        print("Adding missing stubs (--force)...")

    ai_dir.mkdir(parents=True, exist_ok=True)

    for sub in AI_SUBDIRS:
        (ai_dir / sub).mkdir(exist_ok=True)

    for name, default_content in PROJECT_FILES.items():
        path = ai_dir / name
        if path.exists():
            print(f"  SKIP (exists): {path}")
            continue

        if name == "PROJECT.md" and repo_has_file(target_dir, "AGENTS.md"):
            content = (
                "# Project Overview\n\n"
                "This project is documented in the repository root.\n"
                "See `AGENTS.md` for agent instructions and product context.\n"
            )
        elif name == "ARCHITECTURE.md" and repo_has_file(target_dir, "AGENTS.md"):
            content = (
                "# Architecture\n\n"
                "Canonical component descriptions are in `AGENTS.md`.\n"
            )
        elif name == "CONVENTIONS.md" and repo_has_file(target_dir, "AGENTS.md"):
            content = (
                "# Conventions\n\n"
                "Repository conventions are defined in `AGENTS.md`.\n"
            )
        else:
            content = default_content

        path.write_text(content, encoding="utf-8")
        print(f"  CREATE: {path}")

    if not any((ai_dir / n).exists() for n in PROJECT_FILES):
        pass

    print(f"\nInitialized .ai/ at {ai_dir}")
    print("Review the stub files and replace them with project-specific content.")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Initialize .ai/ project directory from templates."
    )
    parser.add_argument(
        "target", nargs="?", default=".",
        help="Target repository root directory (default: current)."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Add missing stubs without overwriting existing files."
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Only check if .ai/ exists, exit 0 if yes."
    )
    args = parser.parse_args()

    target = os.path.abspath(args.target)
    if not os.path.isdir(target):
        print(f"ERROR: not a directory: {target}", file=sys.stderr)
        sys.exit(1)

    if args.check:
        if (Path(target) / ".ai").is_dir():
            print("EXISTS")
            sys.exit(0)
        else:
            print("NOT_FOUND")
            sys.exit(1)

    success = init_project(target, force=args.force)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
