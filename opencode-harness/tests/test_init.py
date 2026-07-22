"""Tests for project initializer."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from init_project import init_project


class TestInit(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_creates_directory_structure(self):
        result = init_project(self.tmpdir)
        self.assertTrue(result)

        ai_dir = os.path.join(self.tmpdir, ".ai")
        self.assertTrue(os.path.isdir(ai_dir))
        self.assertTrue(os.path.isdir(os.path.join(ai_dir, "TASKS")))
        self.assertTrue(os.path.isdir(os.path.join(ai_dir, "REVIEWS")))
        self.assertTrue(os.path.isdir(os.path.join(ai_dir, "trace")))

    def test_init_creates_project_files(self):
        result = init_project(self.tmpdir)
        self.assertTrue(result)

        for name in ["PROJECT.md", "ARCHITECTURE.md", "CONVENTIONS.md"]:
            path = os.path.join(self.tmpdir, ".ai", name)
            self.assertTrue(os.path.isfile(path), f"Missing: {path}")

    def test_refuses_overwrite_existing(self):
        ai_dir = os.path.join(self.tmpdir, ".ai")
        os.makedirs(ai_dir)
        project_path = os.path.join(ai_dir, "PROJECT.md")
        with open(project_path, "w") as f:
            f.write("Custom content")

        result = init_project(self.tmpdir)
        self.assertFalse(result)

        with open(project_path) as f:
            content = f.read()
        self.assertEqual(content, "Custom content")

    def test_force_adds_missing_only(self):
        ai_dir = os.path.join(self.tmpdir, ".ai")
        os.makedirs(ai_dir)
        project_path = os.path.join(ai_dir, "PROJECT.md")
        custom = "Custom project overview"
        with open(project_path, "w") as f:
            f.write(custom)

        result = init_project(self.tmpdir, force=True)
        self.assertTrue(result)

        with open(project_path) as f:
            self.assertEqual(f.read(), custom)

        self.assertTrue(os.path.isfile(os.path.join(ai_dir, "ARCHITECTURE.md")))
        self.assertTrue(os.path.isfile(os.path.join(ai_dir, "CONVENTIONS.md")))

    def test_force_preserves_all_existing(self):
        ai_dir = os.path.join(self.tmpdir, ".ai")
        os.makedirs(ai_dir)
        for name in ["PROJECT.md", "ARCHITECTURE.md", "CONVENTIONS.md"]:
            path = os.path.join(ai_dir, name)
            with open(path, "w") as f:
                f.write(f"Custom {name}")

        result = init_project(self.tmpdir, force=True)
        self.assertTrue(result)

        for name in ["PROJECT.md", "ARCHITECTURE.md", "CONVENTIONS.md"]:
            path = os.path.join(ai_dir, name)
            with open(path) as f:
                self.assertEqual(f.read(), f"Custom {name}")

    def test_init_with_agents_md(self):
        with open(os.path.join(self.tmpdir, "AGENTS.md"), "w") as f:
            f.write("# AGENTS.md content\n")

        result = init_project(self.tmpdir)
        self.assertTrue(result)

        project_path = os.path.join(self.tmpdir, ".ai", "PROJECT.md")
        with open(project_path) as f:
            content = f.read()
        self.assertIn("AGENTS.md", content)


if __name__ == "__main__":
    unittest.main()
