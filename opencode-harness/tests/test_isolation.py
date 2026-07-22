"""Tests for isolation bundle creation."""

import os
import shutil
import subprocess
import tempfile
import unittest


ISOLATION_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "isolation.sh"
)


class TestIsolation(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._setup_git_repo()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _setup_git_repo(self):
        subprocess.run(["git", "init"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.test"],
            cwd=self.tmpdir, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=self.tmpdir, capture_output=True,
        )
        with open(os.path.join(self.tmpdir, "test.py"), "w") as f:
            f.write("print('hello')\n")
        subprocess.run(["git", "add", "test.py"], cwd=self.tmpdir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=self.tmpdir, capture_output=True,
        )

    def test_isolation_requires_phase_and_task_id(self):
        result = subprocess.run(
            ["bash", ISOLATION_SCRIPT],
            cwd=self.tmpdir,
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_isolation_review_creates_bundle(self):
        os.makedirs(os.path.join(self.tmpdir, ".ai", "TASKS", "test-1"))
        with open(os.path.join(self.tmpdir, ".ai", "TASKS", "test-1", "REQUEST.md"), "w") as f:
            f.write("# Test request\n")
        with open(os.path.join(self.tmpdir, ".ai", "TASKS", "test-1", "SPEC.md"), "w") as f:
            f.write("# Test spec\n")

        result = subprocess.run(
            ["bash", ISOLATION_SCRIPT, "review", "test-1", "--worktree", self.tmpdir],
            cwd=self.tmpdir,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)

        output_lines = result.stdout.strip().split("\n")
        bundle_dir = output_lines[-1]
        self.assertTrue(os.path.isdir(bundle_dir))

        self.assertTrue(os.path.isdir(os.path.join(bundle_dir, "specs")))
        self.assertTrue(os.path.isdir(os.path.join(bundle_dir, "diffs")))
        self.assertTrue(os.path.isdir(os.path.join(bundle_dir, "results")))
        self.assertFalse(os.path.exists(os.path.join(bundle_dir, "output")))

        self.assertTrue(
            os.path.isfile(os.path.join(bundle_dir, "specs", "REQUEST.md"))
        )
        self.assertTrue(
            os.path.isfile(os.path.join(bundle_dir, "specs", "SPEC.md"))
        )
        self.assertTrue(
            os.path.isfile(os.path.join(bundle_dir, "diffs", "implementation.diff"))
        )
        self.assertTrue(
            os.path.isfile(os.path.join(bundle_dir, "README.txt"))
        )

        with open(os.path.join(bundle_dir, "README.txt")) as f:
            readme = f.read()
        self.assertIn("test-1", readme)
        self.assertIn("final response only", readme)

        shutil.rmtree(bundle_dir, ignore_errors=True)

    def test_isolation_debug_creates_bundle(self):
        result = subprocess.run(
            ["bash", ISOLATION_SCRIPT, "debug", "task-d", "--worktree", self.tmpdir],
            cwd=self.tmpdir,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)

        output_lines = result.stdout.strip().split("\n")
        bundle_dir = output_lines[-1]
        self.assertTrue(os.path.isdir(bundle_dir))

        with open(os.path.join(bundle_dir, "README.txt")) as f:
            readme = f.read()
        self.assertIn("DEBUG", readme)

        shutil.rmtree(bundle_dir, ignore_errors=True)

    def test_isolation_bundle_no_source_files(self):
        result = subprocess.run(
            ["bash", ISOLATION_SCRIPT, "review", "task-src", "--worktree", self.tmpdir],
            cwd=self.tmpdir,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)

        output_lines = result.stdout.strip().split("\n")
        bundle_dir = output_lines[-1]

        source = os.path.join(bundle_dir, "test.py")
        self.assertFalse(os.path.exists(source))

        full_source = os.path.join(bundle_dir, os.path.basename(self.tmpdir))
        self.assertFalse(os.path.exists(full_source))

        shutil.rmtree(bundle_dir, ignore_errors=True)

    def test_isolation_rejects_invalid_phase(self):
        result = subprocess.run(
            ["bash", ISOLATION_SCRIPT, "invalid", "task-1", "--worktree", self.tmpdir],
            cwd=self.tmpdir,
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
