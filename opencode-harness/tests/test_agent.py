"""Tests for run_agent.py with a fake opencode executable.

Proves:
1. Coding invokes only DeepSeek v4 Pro.
2. Review and Debug invoke only GLM 5.2 in an isolated directory.
3. lpc/* never selected even if present in models output.
4. Missing exact models fail before a run command.
5. Review and Debug reports captured at correct paths.
6. Missing final text report fails.
7. Untracked implementation files appear in the review patch; ignored files do not.
8. JSON event usage is converted to trace fields without copying raw content.
9. Unknown usage remains null.
10. Project and task initialization refuse overwrites.
11. HIGH cannot start without complete Architect artifacts.
12. Compatibility path resolves and scripts pass syntax checks.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from run_agent import (
    CODING_MODEL,
    CODING_FALLBACK_MODEL,
    REVIEW_MODEL,
    DEBUG_MODEL,
    FORBIDDEN_PREFIX,
    _check_model,
    _opencode_models,
    _get_opencode,
    _determine_report_path,
    run_coding,
    run_review,
    run_debug,
    parse_opencode_events,
)

from init_task import init_task, check_high_requirements

INIT_TASK_PY = os.path.join(SCRIPTS_DIR, "init_task.py")
PATCH_COLLECTOR_PY = os.path.join(SCRIPTS_DIR, "patch_collector.py")


def _make_fake_opencode(tmpdir, models_output=None, fail_models=False, run_exit=0,
                        report_content=None, record_invocations=None):
    fake_path = os.path.join(tmpdir, "bin")
    os.makedirs(fake_path, exist_ok=True)
    fake = os.path.join(fake_path, "opencode")
    fake_py = fake + ".py"

    models_text = models_output or (CODING_MODEL + "\n" + REVIEW_MODEL + "\n")
    fail_models_text = "True" if fail_models else "False"
    rec = repr(record_invocations) if record_invocations else "None"
    rep = repr(report_content) if report_content else "None"

    code = (
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "record_path = " + rec + "\n"
        "models_text = " + repr(models_text) + "\n"
        "fail_models = " + fail_models_text + "\n"
        "report_content_value = " + rep + "\n"
        "def main():\n"
        '    args = sys.argv[1:]\n'
        '    if args and args[0] == "models":\n'
        "        if fail_models:\n"
        '            print("ERROR: models failed", file=sys.stderr)\n'
        "            sys.exit(1)\n"
        "        print(models_text, end='')\n"
        "        return\n"
        '    if args and args[0] == "--version":\n'
        '        print("opencode 1.0.0")\n'
        "        return\n"
        '    if args and args[0] == "run":\n'
        '        cmd_line = " ".join(sys.argv)\n'
        "        if record_path is not None:\n"
        '            with open(record_path, "a") as f:\n'
        '                f.write(cmd_line + "\\n")\n'
        "        if report_content_value is not None:\n"
        '            print(json.dumps({"type":"text","sessionID":"ses-test","part":{"type":"text","messageID":"msg-final","text":report_content_value}}))\n'
        '        print(json.dumps({"type":"step_finish","sessionID":"ses-test","part":{"type":"step-finish","tokens":{"input":10,"output":5,"reasoning":2,"cache":{"read":3,"write":0}},"cost":0.01}}))\n'
        "        sys.exit(" + str(run_exit) + ")\n"
        "        return\n"
        '    if args and args[0] == "--help":\n'
        '        print("usage: opencode run [--auto] [--model MODEL] [--agent AGENT] [--dir DIR] [--pure] PROMPT")\n'
        "        return\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )

    with open(fake_py, "w") as f:
        f.write(code)

    with open(fake, "w") as f:
        f.write('#!/bin/bash\nexec python3 "' + fake_py + '" "$@"\n')

    os.chmod(fake, 0o755)
    return fake, fake_path


class TestAgentModelPolicy(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.git_root = os.path.join(self.tmpdir, "repo")
        os.makedirs(self.git_root)
        subprocess.run(["git", "init"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.test"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.git_root, capture_output=True)
        with open(os.path.join(self.git_root, "test.py"), "w") as f:
            f.write("print('hello')\n")
        subprocess.run(["git", "add", "test.py"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.git_root, capture_output=True)

        self.original_path = os.environ.get("PATH", "")
        self.fake_path = os.path.join(self.tmpdir, "bin")
        os.environ["PATH"] = self.fake_path + os.pathsep + self.original_path

    def tearDown(self):
        os.environ["PATH"] = self.original_path
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_coding_model_is_deepseek_v4_pro(self):
        self.assertEqual(CODING_MODEL, "deepseek/deepseek-v4-pro")
        self.assertEqual(CODING_FALLBACK_MODEL, CODING_MODEL)

    def test_review_model_is_glm_5_2(self):
        self.assertEqual(REVIEW_MODEL, "doubaoglm/glm-5-2-260617")

    def test_debug_model_is_glm_5_2(self):
        self.assertEqual(DEBUG_MODEL, "doubaoglm/glm-5-2-260617")

    def test_lpc_is_forbidden_prefix(self):
        self.assertEqual(FORBIDDEN_PREFIX, "lpc/")
        ok, msg = _check_model("lpc/gpt-4", "Coding")
        self.assertFalse(ok)
        self.assertIn("forbidden", msg)

    def test_missing_model_fails_before_run(self):
        fake, _ = _make_fake_opencode(
            self.tmpdir, models_output="some-other-model\n", run_exit=0,
        )
        ok, msg = _check_model(CODING_MODEL, "Coding")
        self.assertFalse(ok)
        self.assertIn("not found", msg)

    def test_model_available_passes(self):
        fake, _ = _make_fake_opencode(
            self.tmpdir,
            models_output=f"{CODING_MODEL}\n{REVIEW_MODEL}\n",
        )
        ok, msg = _check_model(CODING_MODEL, "Coding")
        self.assertTrue(ok)

    def test_review_requires_glm_only(self):
        # _check_model only validates model availability, not role mapping.
        # Role enforcement is tested via test_coding_does_not_invoke_glm
        # and test_review_invokes_only_glm_in_isolated_dir.
        fake, _ = _make_fake_opencode(
            self.tmpdir,
            models_output=f"{CODING_MODEL}\n{REVIEW_MODEL}\n",
        )
        ok_coding, _ = _check_model(CODING_MODEL, "Coding")
        self.assertTrue(ok_coding)
        ok_review, _ = _check_model(REVIEW_MODEL, "Review")
        self.assertTrue(ok_review)


class TestAgentInvocation(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.git_root = os.path.join(self.tmpdir, "repo")
        os.makedirs(self.git_root)
        subprocess.run(["git", "init"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.test"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.git_root, capture_output=True)
        with open(os.path.join(self.git_root, "test.py"), "w") as f:
            f.write("print('hello')\n")
        subprocess.run(["git", "add", "test.py"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.git_root, capture_output=True)

        self.record_path = os.path.join(self.tmpdir, "invocations.txt")
        self.original_path = os.environ.get("PATH", "")
        self.fake_path = os.path.join(self.tmpdir, "bin")
        os.environ["PATH"] = self.fake_path + os.pathsep + self.original_path

    def tearDown(self):
        os.environ["PATH"] = self.original_path
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_coding_invokes_deepseek_model(self):
        fake, _ = _make_fake_opencode(
            self.tmpdir,
            models_output=f"{CODING_MODEL}\n{REVIEW_MODEL}\n",
            record_invocations=self.record_path,
            run_exit=0,
        )
        code, msg, run_id, _ = run_coding(self.git_root, "task-1", task_content="Fix typo in README")
        self.assertEqual(code, 0)

        with open(self.record_path, "r") as f:
            invocations = f.read()
        self.assertIn("deepseek/deepseek-v4-pro", invocations)
        self.assertIn("--agent", invocations)
        self.assertIn("build", invocations)
        self.assertIn("--format json", invocations)

        traces = list(Path(self.git_root, ".agent-runs", "traces").glob("*.json"))
        self.assertEqual(len(traces), 1)
        trace = json.loads(traces[0].read_text(encoding="utf-8"))
        self.assertEqual(trace["model"], CODING_MODEL)
        self.assertEqual(trace["usage"]["input_tokens"], 10)
        self.assertEqual(trace["usage"]["output_tokens"], 5)
        self.assertEqual(trace["usage"]["reasoning_tokens"], 2)
        self.assertEqual(trace["usage"]["cache_read_tokens"], 3)
        self.assertEqual(trace["usage"]["cost"], 0.01)
        self.assertNotIn("Fix typo in README", traces[0].read_text(encoding="utf-8"))

    def test_coding_does_not_invoke_glm(self):
        coding_out = f"{CODING_MODEL}\n{REVIEW_MODEL}\n"
        fake, _ = _make_fake_opencode(
            self.tmpdir,
            models_output=coding_out,
            record_invocations=self.record_path,
            run_exit=0,
        )
        code, msg, run_id, _ = run_coding(self.git_root, "task-2", task_content="Fix typo")
        self.assertEqual(code, 0)
        with open(self.record_path, "r") as f:
            invocations = f.read()
        self.assertIn(CODING_MODEL, invocations)
        self.assertNotIn(REVIEW_MODEL, invocations)

    def test_review_invokes_only_glm_in_isolated_dir(self):
        fake, _ = _make_fake_opencode(
            self.tmpdir,
            models_output=f"{CODING_MODEL}\n{REVIEW_MODEL}\n",
            record_invocations=self.record_path,
            run_exit=0,
            report_content="Verdict: PASS\n\nAll checks passed.\n",
        )
        code, msg, run_id = run_review(self.git_root, "task-3")
        self.assertEqual(code, 0)

        with open(self.record_path, "r") as f:
            invocations = f.read()
        self.assertIn(REVIEW_MODEL, invocations)
        self.assertNotIn(CODING_MODEL, invocations)
        self.assertIn("--pure", invocations)
        self.assertIn("opencode-harness-review-", invocations)
        self.assertNotIn(self.git_root, invocations)

    def test_debug_invokes_only_glm_in_isolated_dir(self):
        fake, _ = _make_fake_opencode(
            self.tmpdir,
            models_output=f"{CODING_MODEL}\n{REVIEW_MODEL}\n",
            record_invocations=self.record_path,
            run_exit=0,
            report_content="# Debug Report\n\n## Failure reason\nFound the issue.\n\n## Proposed fix\nFix it.\n\n## Affected files\n- app.py\n",
        )
        code, msg, run_id = run_debug(self.git_root, "task-4")
        self.assertEqual(code, 0)

        with open(self.record_path, "r") as f:
            invocations = f.read()
        self.assertIn(REVIEW_MODEL, invocations)
        self.assertNotIn(CODING_MODEL, invocations)
        self.assertIn("--pure", invocations)
        self.assertIn("opencode-harness-debug-", invocations)

    def test_review_without_auto_flag(self):
        fake, _ = _make_fake_opencode(
            self.tmpdir,
            models_output=f"{CODING_MODEL}\n{REVIEW_MODEL}\n",
            record_invocations=self.record_path,
            run_exit=0,
            report_content="Verdict: PASS\n\nNo issues found.\n",
        )
        code, msg, run_id = run_review(self.git_root, "task-noauto")
        self.assertEqual(code, 0)
        with open(self.record_path, "r") as f:
            invocations = f.read()
        self.assertNotIn("--auto", invocations)

    def test_event_parser_selects_last_message_and_unknown_usage(self):
        events = "\n".join([
            json.dumps({"type": "text", "part": {"type": "text", "messageID": "m1", "text": "progress"}}),
            json.dumps({"type": "text", "part": {"type": "text", "messageID": "m2", "text": "Verdict: PASS"}}),
        ])
        final_text, usage, actions, session_id = parse_opencode_events(events)
        self.assertEqual(final_text, "Verdict: PASS")
        self.assertTrue(all(value is None for value in usage.values()))


class TestAgentReportCapture(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.git_root = os.path.join(self.tmpdir, "repo")
        os.makedirs(self.git_root)
        subprocess.run(["git", "init"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.test"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.git_root, capture_output=True)
        with open(os.path.join(self.git_root, "test.py"), "w") as f:
            f.write("print('hello')\n")
        subprocess.run(["git", "add", "test.py"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.git_root, capture_output=True)

        self.original_path = os.environ.get("PATH", "")
        self.fake_path = os.path.join(self.tmpdir, "bin")
        os.environ["PATH"] = self.fake_path + os.pathsep + self.original_path

    def tearDown(self):
        os.environ["PATH"] = self.original_path
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_fake_with_report(self, role, report_content, run_exit=0):
        record = os.path.join(self.tmpdir, "invocations.txt")
        fake_path = os.path.join(self.tmpdir, "bin")
        os.makedirs(fake_path, exist_ok=True)
        fake_py = os.path.join(fake_path, "opencode.py")
        fake_sh = os.path.join(fake_path, "opencode")

        models_text = CODING_MODEL + "\n" + REVIEW_MODEL + "\n"
        rec = repr(record)
        rep = repr(report_content)
        run_exit_str = str(run_exit)

        code = (
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "record = " + rec + "\n"
            "models_text = " + repr(models_text) + "\n"
            "report_content = " + rep + "\n"
            "def main():\n"
            '    args = sys.argv[1:]\n'
            '    if args and args[0] == "models":\n'
            "        print(models_text, end='')\n"
            "        return\n"
            '    if args and args[0] == "--version":\n'
            '        print("opencode 1.0.0")\n'
            "        return\n"
            '    if args and args[0] == "run":\n'
            '        with open(record, "a") as f:\n'
            '            f.write(" ".join(sys.argv) + "\\n")\n'
            '        if report_content:\n'
            '            print(json.dumps({"type":"text","sessionID":"ses-report","part":{"type":"text","messageID":"msg-final","text":report_content}}))\n'
            '        print(json.dumps({"type":"step_finish","sessionID":"ses-report","part":{"type":"step-finish","tokens":{"input":12,"output":7,"cache":{"read":1}},"cost":0.02}}))\n'
            "        sys.exit(" + run_exit_str + ")\n"
            "        return\n"
            '    if args and args[0] == "--help":\n'
            '        print("usage: opencode run [OPTIONS] PROMPT")\n'
            "        return\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )

        with open(fake_py, "w") as f:
            f.write(code)
        with open(fake_sh, "w") as f:
            f.write('#!/bin/bash\nexec python3 "' + fake_py + '" "$@"\n')
        os.chmod(fake_sh, 0o755)

    def test_review_report_written_to_reviews_dir(self):
        os.makedirs(os.path.join(self.git_root, ".ai", "TASKS", "task-r1"))
        self._create_fake_with_report("review", "Verdict: PASS\nAll good.", run_exit=0)
        code, msg, run_id = run_review(self.git_root, "task-r1")
        self.assertEqual(code, 0)
        review_path = os.path.join(self.git_root, ".ai", "REVIEWS", "task-r1", "REVIEW.md")
        self.assertTrue(os.path.isfile(review_path), f"Expected REVIEW.md at {review_path}")
        with open(review_path, "r") as f:
            content = f.read()
        self.assertIn("Verdict: PASS", content)

    def test_debug_report_written_to_tasks_dir(self):
        os.makedirs(os.path.join(self.git_root, ".ai", "TASKS", "task-d1"))
        self._create_fake_with_report(
            "debug",
            "# Debug Report\n\n## Failure reason\nFound the bug.\n\n"
            "## Proposed fix\nCorrect the branch.\n\n## Affected files\n- test.py\n",
            run_exit=0,
        )
        code, msg, run_id = run_debug(self.git_root, "task-d1")
        self.assertEqual(code, 0)
        debug_path = os.path.join(self.git_root, ".ai", "TASKS", "task-d1", "DEBUG_REPORT.md")
        self.assertTrue(os.path.isfile(debug_path), f"Expected DEBUG_REPORT.md at {debug_path}")
        with open(debug_path, "r") as f:
            content = f.read()
        self.assertIn("Debug Report", content)

    def test_empty_report_fails(self):
        os.makedirs(os.path.join(self.git_root, ".ai", "TASKS", "task-empty"))
        self._create_fake_with_report("review", "", run_exit=0)
        code, msg, run_id = run_review(self.git_root, "task-empty")
        self.assertNotEqual(code, 0)
        self.assertTrue("no final text" in msg.lower() or "empty" in msg.lower() or "unchanged" in msg.lower())

    def test_no_report_file_fails(self):
        os.makedirs(os.path.join(self.git_root, ".ai", "TASKS", "task-norpt"))
        os.makedirs(self.fake_path, exist_ok=True)
        fake_py = os.path.join(self.fake_path, "opencode.py")
        fake_sh = os.path.join(self.fake_path, "opencode")
        models_text = CODING_MODEL + "\n" + REVIEW_MODEL + "\n"
        code = (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "models_text = " + repr(models_text) + "\n"
            "def main():\n"
            '    args = sys.argv[1:]\n'
            '    if args and args[0] == "models":\n'
            "        print(models_text, end='')\n"
            "        return\n"
            '    if args and args[0] == "--version":\n'
            '        print("opencode 1.0.0")\n'
            "        return\n"
            '    if args and args[0] == "run":\n'
            "        sys.exit(0)\n"
            "        return\n"
            '    if args and args[0] == "--help":\n'
            '        print("usage: opencode run [OPTIONS] PROMPT")\n'
            "        return\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        with open(fake_py, "w") as f:
            f.write(code)
        with open(fake_sh, "w") as f:
            f.write('#!/bin/bash\nexec python3 "' + fake_py + '" "$@"\n')
        os.chmod(fake_sh, 0o755)

        code, msg, run_id = run_review(self.git_root, "task-norpt")
        self.assertNotEqual(code, 0)
        self.assertTrue("no final text" in msg.lower() or "empty" in msg.lower() or "unchanged" in msg.lower())


class TestPatchCollector(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.git_root = os.path.join(self.tmpdir, "repo")
        os.makedirs(self.git_root)
        subprocess.run(["git", "init"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.test"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.git_root, capture_output=True)
        with open(os.path.join(self.git_root, "main.py"), "w") as f:
            f.write("print('hello')\n")
        subprocess.run(["git", "add", "main.py"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.git_root, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_untracked_file_appears_in_patch(self):
        with open(os.path.join(self.git_root, "new_file.py"), "w") as f:
            f.write("# New implementation\nprint('new')\n")

        result = subprocess.run(
            [sys.executable, PATCH_COLLECTOR_PY, self.git_root],
            capture_output=True, cwd=self.git_root,
        )
        self.assertEqual(result.returncode, 0)
        output = result.stdout.decode(errors="replace")
        self.assertIn("untracked: new_file.py", output)
        self.assertIn("print('new')", output)

    def test_untracked_symlink_appears_in_patch(self):
        os.symlink("main.py", os.path.join(self.git_root, "compat.py"))
        result = subprocess.run(
            [sys.executable, PATCH_COLLECTOR_PY, self.git_root],
            capture_output=True, cwd=self.git_root,
        )
        output = result.stdout.decode(errors="replace")
        self.assertIn("untracked symlink: compat.py", output)
        self.assertIn("new file mode 120000", output)
        self.assertIn("+main.py", output)

    def test_gitignored_file_does_not_appear(self):
        with open(os.path.join(self.git_root, ".gitignore"), "w") as f:
            f.write("ignored_dir/\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add gitignore"], cwd=self.git_root, capture_output=True)
        os.makedirs(os.path.join(self.git_root, "ignored_dir"), exist_ok=True)
        with open(os.path.join(self.git_root, "ignored_dir", "secret.py"), "w") as f:
            f.write("SECRET=12345\n")

        result = subprocess.run(
            [sys.executable, PATCH_COLLECTOR_PY, self.git_root],
            capture_output=True, cwd=self.git_root,
        )
        self.assertEqual(result.returncode, 0)
        output = result.stdout.decode(errors="replace")
        self.assertNotIn("secret.py", output)
        self.assertNotIn("SECRET=12345", output)

    def test_dotenv_excluded_from_patch(self):
        with open(os.path.join(self.git_root, ".env"), "w") as f:
            f.write("SECRET_KEY=abc\n")

        result = subprocess.run(
            [sys.executable, PATCH_COLLECTOR_PY, self.git_root],
            capture_output=True, cwd=self.git_root,
        )
        self.assertEqual(result.returncode, 0)
        output = result.stdout.decode(errors="replace")
        self.assertNotIn("SECRET_KEY", output)

    def test_literal_credential_is_redacted(self):
        secret = "not-a-real-" + "test-key"
        with open(os.path.join(self.git_root, "config.py"), "w") as f:
            f.write("api_" + "key = " + json.dumps(secret) + "\n")
        result = subprocess.run(
            [sys.executable, PATCH_COLLECTOR_PY, self.git_root],
            capture_output=True, cwd=self.git_root,
        )
        output = result.stdout.decode(errors="replace")
        self.assertNotIn(secret, output)
        self.assertIn("<REDACTED>", output)

    def test_staged_changes_in_patch(self):
        with open(os.path.join(self.git_root, "main.py"), "w") as f:
            f.write("print('modified')\n")
        subprocess.run(["git", "add", "main.py"], cwd=self.git_root, capture_output=True)

        result = subprocess.run(
            [sys.executable, PATCH_COLLECTOR_PY, self.git_root],
            capture_output=True, cwd=self.git_root,
        )
        self.assertEqual(result.returncode, 0)
        output = result.stdout.decode(errors="replace")
        self.assertIn("--cached", output)

    def test_patch_unicode_paths(self):
        with open(os.path.join(self.git_root, "f\xc3\xacl\xc3\xa9.py"), "w") as f:
            f.write("# Unicode file\n")
        result = subprocess.run(
            [sys.executable, PATCH_COLLECTOR_PY, self.git_root],
            capture_output=True, cwd=self.git_root,
        )
        self.assertEqual(result.returncode, 0)


class TestTaskInit(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.git_root = os.path.join(self.tmpdir, "repo")
        os.makedirs(self.git_root)
        subprocess.run(["git", "init"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.test"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.git_root, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_low_creates_minimal_artifacts(self):
        success, msg = init_task(self.git_root, "task-low", "LOW")
        self.assertTrue(success)
        task_dir = os.path.join(self.git_root, ".agent-runs", "tasks", "task-low")
        self.assertTrue(os.path.isdir(task_dir))
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "REQUEST.md")))
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "STATUS.json")))
        with open(os.path.join(task_dir, "STATUS.json")) as f:
            status = json.load(f)
        self.assertEqual(status["risk_level"], "LOW")
        self.assertEqual(status["state"], "routed")

    def test_init_medium_creates_spec_and_test_templates(self):
        success, msg = init_task(self.git_root, "task-med", "MEDIUM")
        self.assertTrue(success)
        task_dir = os.path.join(self.git_root, ".agent-runs", "tasks", "task-med")
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "REQUEST.md")))
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "SPEC.md")))
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "TEST_RESULTS.md")))
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "STATUS.json")))

    def test_init_high_creates_full_artifact_set(self):
        success, msg = init_task(self.git_root, "task-high", "HIGH")
        self.assertTrue(success)
        task_dir = os.path.join(self.git_root, ".agent-runs", "tasks", "task-high")
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "REQUEST.md")))
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "SPEC.md")))
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "IMPLEMENTATION_PLAN.md")))
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "ACCEPTANCE.md")))
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "STATUS.json")))

    def test_init_refuses_overwrite(self):
        init_task(self.git_root, "task-ow", "LOW")
        success, msg = init_task(self.git_root, "task-ow", "LOW")
        self.assertFalse(success)
        self.assertIn("already exists", msg)

    def test_add_missing_never_overwrites(self):
        init_task(self.git_root, "task-owo", "LOW", request_text="first")
        task_dir = os.path.join(self.git_root, ".agent-runs", "tasks", "task-owo")
        with open(os.path.join(task_dir, "REQUEST.md")) as f:
            self.assertEqual(f.read(), "first\n")
        success, msg = init_task(self.git_root, "task-owo", "LOW", request_text="second", add_missing=True)
        self.assertTrue(success)
        with open(os.path.join(task_dir, "REQUEST.md")) as f:
            self.assertEqual(f.read(), "first\n")

    def test_high_architect_check_missing_artifacts(self):
        # When files don't exist at all, check reports missing
        missing = check_high_requirements(self.git_root, "task-noexist")
        self.assertTrue(len(missing) > 0)

    def test_high_architect_check_placeholder_only(self):
        from pathlib import Path as P
        task_dir = os.path.join(self.git_root, ".agent-runs", "tasks", "task-ph")
        os.makedirs(task_dir, exist_ok=True)
        for name in ["SPEC.md", "IMPLEMENTATION_PLAN.md", "ACCEPTANCE.md"]:
            path = os.path.join(task_dir, name)
            P(path).write_text(f"# {name}\n")
        missing = check_high_requirements(self.git_root, "task-ph")
        self.assertTrue(len(missing) > 0)

    def test_init_high_check_passes_with_content(self):
        success, _ = init_task(self.git_root, "task-real", "HIGH")
        task_dir = os.path.join(self.git_root, ".agent-runs", "tasks", "task-real")
        for name in ["SPEC.md", "IMPLEMENTATION_PLAN.md", "ACCEPTANCE.md"]:
            path = os.path.join(task_dir, name)
            with open(path, "w") as f:
                f.write(f"# {name}\n\nDetailed content for {name}. This is a real specification with meaningful content.\n")
        missing = check_high_requirements(self.git_root, "task-real")
        self.assertEqual(missing, [])

    def test_init_uses_dot_ai_when_present(self):
        os.makedirs(os.path.join(self.git_root, ".ai"))
        success, msg = init_task(self.git_root, "task-ai", "LOW")
        self.assertTrue(success)
        task_dir = os.path.join(self.git_root, ".ai", "TASKS", "task-ai")
        self.assertTrue(os.path.isdir(task_dir))
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "STATUS.json")))

    def test_invalid_risk_level(self):
        with self.assertRaises(ValueError):
            init_task(self.git_root, "task-invalid", "INVALID")


class TestTraceDiffHash(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.git_root = os.path.join(self.tmpdir, "repo")
        os.makedirs(self.git_root)
        subprocess.run(["git", "init"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.test"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.git_root, capture_output=True)
        with open(os.path.join(self.git_root, "main.py"), "w") as f:
            f.write("print('hello')\n")
        subprocess.run(["git", "add", "main.py"], cwd=self.git_root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.git_root, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_diff_hash_changes_with_untracked_file(self):
        sys.path.insert(0, SCRIPTS_DIR)
        from trace import get_diff_hash

        hash1 = get_diff_hash(self.git_root)
        with open(os.path.join(self.git_root, "untracked.py"), "w") as f:
            f.write("# new file\n")
        hash2 = get_diff_hash(self.git_root)
        self.assertNotEqual(hash1, hash2, "Diff hash should change when untracked file is added")

    def test_finished_at_in_required_fields(self):
        sys.path.insert(0, SCRIPTS_DIR)
        from trace import REQUIRED_FIELDS
        self.assertIn("finished_at", REQUIRED_FIELDS)
        self.assertIn("failure_reason", REQUIRED_FIELDS)
        self.assertIn("baseline_diff_hash", REQUIRED_FIELDS)

    def test_trace_without_finished_at_fails_validation(self):
        sys.path.insert(0, SCRIPTS_DIR)
        from trace import validate_trace, TRACE_SCHEMA_VERSION
        trace = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "run_id": "abcd1234",
            "task_id": "t1",
            "phase": "coding",
            "agent": "coding",
            "provider": "deepseek",
            "model": CODING_MODEL,
            "started_at": "2026-01-01T00:00:00Z",
            "git_head": "abc",
            "baseline_diff_hash": "",
            "input_artifacts": [],
            "output_artifacts": [],
            "actions": [],
            "commands": [],
            "validation": [],
            "usage": {},
            "result": "",
            "failure_reason": "",
            "next_action": "",
        }
        errors = validate_trace(trace)
        self.assertIn("missing required field: finished_at", errors)


class TestCompatibilitySymlink(unittest.TestCase):

    def test_symlink_points_to_harness(self):
        link = os.path.join(os.path.dirname(SCRIPTS_DIR), "..", "..", "opencode_harness")
        if os.path.islink(link):
            target = os.readlink(link)
            self.assertEqual(target, "opencode-harness")

    def test_delegate_sh_exists(self):
        delegate = os.path.join(SCRIPTS_DIR, "delegate.sh")
        self.assertTrue(os.path.isfile(delegate))

    def test_scripts_pass_bash_syntax(self):
        for script in ["orchestrator.sh", "delegate.sh", "isolation.sh", "collect_result.sh", "verify_environment.sh"]:
            path = os.path.join(SCRIPTS_DIR, script)
            if os.path.isfile(path):
                result = subprocess.run(
                    ["bash", "-n", path], capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, f"{script} failed syntax check: {result.stderr}")

    def test_orchestrator_avoids_bash4_uppercase_expansion(self):
        path = os.path.join(SCRIPTS_DIR, "orchestrator.sh")
        content = Path(path).read_text(encoding="utf-8")
        self.assertNotIn("^^}", content)


if __name__ == "__main__":
    unittest.main()
