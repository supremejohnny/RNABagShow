#!/usr/bin/env python3
"""Complete, reviewable patch collector for harness isolation bundles.

Includes tracked unstaged/staged changes, untracked non-ignored files,
and status metadata. Excludes .git/, .env, .agent-runs/, .ai/trace/, and
ignored files.
"""

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path


EXCLUDE_DIRS = {".git", ".agent-runs", ".ai/trace"}


def _excluded(path_str):
    parts = Path(path_str).parts
    if any(path_str == item or path_str.startswith(item + "/") for item in EXCLUDE_DIRS):
        return True
    name = Path(path_str).name
    if name == ".env" or name.startswith(".env."):
        return True
    if name in {"credentials.json", "id_rsa", "id_ed25519"}:
        return True
    if Path(name).suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        return True
    return any(part == ".git" for part in parts)


def _redact_sensitive_literals(content):
    """Redact common literal credentials while leaving code structure visible."""
    assignment = re.compile(
        rb"(?i)\b(api[_-]?key|client[_-]?secret|password|access[_-]?token|refresh[_-]?token)"
        rb"(\s*[:=]\s*)(['\"])([^'\"\r\n]+)(['\"])"
    )
    content = assignment.sub(
        lambda match: match.group(1) + match.group(2) + match.group(3)
        + b"<REDACTED>" + match.group(5),
        content,
    )
    private_key = re.compile(
        rb"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----",
        re.DOTALL,
    )
    return private_key.sub(b"<REDACTED PRIVATE KEY>", content)


def collect_patch(repo_root):
    parts = []
    metadata_parts = []

    result = subprocess.run(
        ["git", "status", "--short", "--porcelain", "-z"],
        capture_output=True, cwd=repo_root,
    )
    if result.returncode == 0 and result.stdout:
        status_lines = result.stdout.rstrip(b"\0").split(b"\0")
        metadata_parts.append(b"# git status --short\n" + b"\n".join(status_lines) + b"\n")

    for opt in ["", "--cached"]:
        cmd = ["git", "diff"] + ([opt] if opt else [])
        result = subprocess.run(cmd, capture_output=True, cwd=repo_root)
        if result.returncode == 0 and result.stdout:
            header = b"# git diff" + (b" --cached" if opt else b"") + b"\n"
            parts.append(header + result.stdout)

    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        capture_output=True, cwd=repo_root,
    )
    if result.returncode == 0 and result.stdout:
        untracked = result.stdout.rstrip(b"\0").split(b"\0") if result.stdout.rstrip(b"\0") else []
        for raw in untracked:
            path_str = raw.decode(errors="replace")
            if _excluded(path_str):
                continue

            file_path = os.path.join(repo_root, path_str)
            if os.path.islink(file_path):
                try:
                    target = os.readlink(file_path)
                    if os.path.isabs(target):
                        target = "<ABSOLUTE TARGET REDACTED>"
                    synthetic = (
                        f"# untracked symlink: {path_str}\n"
                        f"diff --git a/{path_str} b/{path_str}\n"
                        "new file mode 120000\n"
                        "--- /dev/null\n"
                        f"+++ b/{path_str}\n"
                        "@@ -0,0 +1 @@\n"
                        f"+{target}\n"
                    ).encode()
                    parts.append(synthetic)
                except OSError:
                    pass
            elif os.path.isfile(file_path):
                try:
                    diff = subprocess.run(
                        ["git", "diff", "--no-index", "--", "/dev/null", path_str],
                        capture_output=True, cwd=repo_root,
                    )
                    # git diff --no-index returns 1 when differences are found.
                    if diff.returncode in {0, 1} and diff.stdout:
                        parts.append(f"# untracked: {path_str}\n".encode() + diff.stdout)
                except OSError:
                    pass

    combined = b"\n".join(metadata_parts + parts)
    return _redact_sensitive_literals(combined)


def main():
    parser = argparse.ArgumentParser(
        description="Collect a complete patch including untracked non-ignored files."
    )
    parser.add_argument("repo_root", nargs="?", default=".", help="Repository root directory.")
    parser.add_argument("--output", "-o", help="Write patch to file instead of stdout.")
    parser.add_argument("--hash-only", action="store_true", help="Print only the SHA-256 hash of the patch.")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)

    if not os.path.isdir(os.path.join(repo_root, ".git")):
        print("ERROR: not a Git repository", file=sys.stderr)
        sys.exit(1)

    patch = collect_patch(repo_root)

    if args.hash_only:
        print(hashlib.sha256(patch).hexdigest()[:16])
        return

    if args.output:
        Path(args.output).write_bytes(patch)
        print(f"Patch written to {args.output}")
    else:
        sys.stdout.buffer.write(patch)


if __name__ == "__main__":
    main()
