#!/usr/bin/env python3
"""Risk-based task router.

Classify a task as LOW, MEDIUM, or HIGH based on keywords and heuristics.
Security, credentials, database migration, deployment, and destructive
operations are never routed LOW.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SECURITY_KEYWORDS = [
    "auth", "credential", "secret", "password", "token",
    "security", "ssl", "tls", "encrypt", "hash", "permission",
    "access_control", "role", "privacy", "phi", "pii",
    "oauth", "jwt", "api_key", "api key", "certificate",
]

DATABASE_KEYWORDS = [
    "migration", "schema", "database", "postgres", "sql",
    "alembic", "ddl", "alter table", "create table",
    "drop table", "truncate",
]

DEPLOYMENT_KEYWORDS = [
    "deploy", "production", "release", "docker", "kubernetes",
    "compose", "nginx", "proxy", "gateway", "ci/cd",
    "ci/cd", "pipeline",
]

DESTRUCTIVE_KEYWORDS = [
    "delete", "destroy", "drop", "purge", "truncate",
    "irreversible", "destructive", "remove_all", "remove all",
    "force push", "hard reset",
]

ARCHITECTURE_KEYWORDS = [
    "architecture", "refactor", "redesign", "rewrite",
    "restructure", "new_service", "new service",
    "new_component", "new component",
]

AMBIGUITY_KEYWORDS = [
    "maybe", "perhaps", "either", "unclear",
    "investigate", "explore", "experiment", "trial",
]

VERIFICATION_KEYWORDS = [
    "integration test", "e2e", "end-to-end", "end to end",
    "manual test", "performance", "load test", "stress test",
]

CORE_INFRA_PATTERNS = [
    "main.py", "/app/", "/api/", "/core/", "/config/",
    "/server/", "/router/", "/middleware/",
]


def _keyword_match(text, keywords):
    text_lower = text.lower()
    matches = []
    for kw in keywords:
        if " " in kw or len(kw) > 3:
            if kw in text_lower:
                matches.append(kw)
        else:
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                matches.append(kw)
    return matches


def _has_any(text, keywords):
    return len(_keyword_match(text, keywords)) > 0


def classify(text, file_paths=None):
    """Classify a task description and optional file list.

    Returns (level, score, reasons) where level is LOW/MEDIUM/HIGH.
    """
    file_paths = file_paths or []
    score = 0
    reasons = []

    if len(file_paths) > 5:
        score += 20
        reasons.append("many files affected (>5)")
    elif len(file_paths) > 2:
        score += 10
        reasons.append(f"multiple files affected ({len(file_paths)})")

    for fp in file_paths:
        for pat in CORE_INFRA_PATTERNS:
            if pat in fp:
                score += 15
                reasons.append(f"core infrastructure affected: {fp}")
                break
        else:
            continue
        break

    security_matches = _keyword_match(text, SECURITY_KEYWORDS)
    if security_matches:
        score += 30
        reasons.append(f"security keyword: {security_matches[0]}")

    db_matches = _keyword_match(text, DATABASE_KEYWORDS)
    if db_matches:
        score += 30
        reasons.append(f"database keyword: {db_matches[0]}")

    deploy_matches = _keyword_match(text, DEPLOYMENT_KEYWORDS)
    if deploy_matches:
        score += 25
        reasons.append(f"deployment keyword: {deploy_matches[0]}")

    destructive_matches = _keyword_match(text, DESTRUCTIVE_KEYWORDS)
    if destructive_matches:
        score += 40
        reasons.append(f"destructive keyword: {destructive_matches[0]}")

    arch_matches = _keyword_match(text, ARCHITECTURE_KEYWORDS)
    if arch_matches:
        score += 20
        reasons.append(f"architecture keyword: {arch_matches[0]}")

    amb_count = sum(1 for kw in AMBIGUITY_KEYWORDS if kw in text.lower())
    if amb_count > 2:
        score += 15
        reasons.append(f"high ambiguity ({amb_count} indicators)")

    verify_matches = _keyword_match(text, VERIFICATION_KEYWORDS)
    if verify_matches:
        score += 10
        reasons.append(f"complex verification: {verify_matches[0]}")

    has_hard_invariant = (
        _has_any(text, SECURITY_KEYWORDS)
        or _has_any(text, DATABASE_KEYWORDS)
        or _has_any(text, DEPLOYMENT_KEYWORDS)
        or _has_any(text, DESTRUCTIVE_KEYWORDS)
    )

    if has_hard_invariant and score < 15:
        score = 15
        reasons.append("hard invariant: security/db/deployment/destructive bumped to min MEDIUM")

    if score >= 40:
        level = "HIGH"
    elif score >= 15:
        level = "MEDIUM"
    else:
        level = "LOW"

    return level, score, reasons


def main():
    parser = argparse.ArgumentParser(
        description="Classify task risk level (LOW/MEDIUM/HIGH)."
    )
    parser.add_argument(
        "input", nargs="?", help="Task file to read, or '-' for stdin."
    )
    parser.add_argument(
        "--json", action="store_true", help="Output classification as JSON."
    )
    parser.add_argument(
        "--files", nargs="*", default=[], help="File paths affected by the task."
    )
    args = parser.parse_args()

    if args.input and args.input != "-":
        path = Path(args.input)
        if not path.exists():
            print(f"ERROR: file not found: {args.input}", file=sys.stderr)
            sys.exit(66)
        text = path.read_text(encoding="utf-8")
    elif args.input == "-":
        text = sys.stdin.read()
    else:
        text = ""
        for line in sys.stdin:
            text += line

    if not text.strip():
        print("ERROR: no task content provided", file=sys.stderr)
        sys.exit(64)

    level, score, reasons = classify(text, args.files)

    if args.json:
        result = {
            "level": level,
            "score": score,
            "reasons": reasons,
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"Risk level: {level} (score: {score})")
        if reasons:
            for r in reasons:
                print(f"  - {r}")

    if level == "HIGH":
        sys.exit(3)
    elif level == "MEDIUM":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
