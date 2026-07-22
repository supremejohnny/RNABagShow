"""Tests for risk-based task router."""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from router import classify


class TestRouter(unittest.TestCase):

    def test_low_simple_task(self):
        text = "Fix typo in README.md"
        level, score, reasons = classify(text, ["README.md"])
        self.assertEqual(level, "LOW")
        self.assertLess(score, 15)

    def test_low_single_file_doc(self):
        text = "Update a docstring in one file"
        level, score, reasons = classify(text, ["lib/utils.py"])
        self.assertEqual(level, "LOW")

    def test_low_css_change(self):
        text = "Rename a CSS class in frontend"
        level, score, reasons = classify(text, ["frontend/style.css"])
        self.assertEqual(level, "LOW")

    def test_low_format_change(self):
        text = "Format code and fix lint warnings"
        level, score, reasons = classify(text, ["src/app.py"])
        self.assertEqual(level, "LOW")

    def test_medium_multiple_files(self):
        text = "Refactor the API endpoint handlers with improved error reporting"
        level, score, reasons = classify(text, ["backend/api/handlers.py", "backend/api/models.py", "tests/test_api.py"])
        self.assertIn(level, ["MEDIUM", "HIGH"])

    def test_medium_refactor(self):
        text = "Refactor preprocessing pipeline"
        level, score, reasons = classify(text, ["pipeline.py", "utils.py", "tests/test_pipeline.py"])
        self.assertIn(level, ["MEDIUM", "HIGH"])

    def test_high_security_never_low(self):
        text = "Fix credential handling in config"
        level, score, reasons = classify(text, ["config.py"])
        self.assertNotEqual(level, "LOW")

    def test_high_auth_single_file_not_low(self):
        text = "Add authentication middleware to API"
        level, score, reasons = classify(text, ["middleware/auth.py"])
        self.assertNotEqual(level, "LOW")

    def test_high_db_migration_not_low(self):
        text = "Run database migration to add a new column"
        level, score, reasons = classify(text, ["migrations/001.sql"])
        self.assertNotEqual(level, "LOW")

    def test_high_deployment_not_low(self):
        text = "Deploy new Docker compose file"
        level, score, reasons = classify(text, ["docker-compose.yml"])
        self.assertNotEqual(level, "LOW")

    def test_high_destructive_not_low(self):
        text = "Drop the users table and purge all data"
        level, score, reasons = classify(text, ["database.py"])
        self.assertNotEqual(level, "LOW")
        self.assertEqual(level, "HIGH")

    def test_high_security_keyword(self):
        text = "Implement password hashing for user accounts"
        level, score, reasons = classify(text, ["auth.py"])
        self.assertIn(level, ["MEDIUM", "HIGH"])
        self.assertNotEqual(level, "LOW")

    def test_high_architecture_and_security(self):
        text = "Refactor the authentication system architecture with new JWT tokens"
        level, score, reasons = classify(text, ["auth.py", "middleware.py", "config.py"])
        self.assertEqual(level, "HIGH")

    def test_empty_text(self):
        level, score, reasons = classify("")
        self.assertEqual(level, "LOW")
        self.assertEqual(score, 0)

    def test_return_types(self):
        level, score, reasons = classify("Fix a simple bug")
        self.assertIsInstance(level, str)
        self.assertIsInstance(score, int)
        self.assertIsInstance(reasons, list)

    def test_levels_are_valid(self):
        for text in ["fix typo", "refactor system", "deploy and migrate"]:
            level, _, _ = classify(text)
            self.assertIn(level, ["LOW", "MEDIUM", "HIGH"])

    def test_file_count_over_five(self):
        files = ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"]
        level, score, reasons = classify("Update many files", files)
        self.assertGreaterEqual(score, 20)

    def test_privacy_keyword_not_low(self):
        text = "Fix PII handling in the upload endpoint"
        level, score, reasons = classify(text, ["upload.py"])
        self.assertNotEqual(level, "LOW")

    def test_token_keyword_not_low(self):
        text = "Add API token validation"
        level, score, reasons = classify(text, ["api.py"])
        self.assertNotEqual(level, "LOW")

    def test_encrypt_keyword_not_low(self):
        text = "Encrypt user data at rest"
        level, score, reasons = classify(text, ["storage.py"])
        self.assertNotEqual(level, "LOW")

    def test_production_keyword_not_low(self):
        text = "Update production Nginx configuration"
        level, score, reasons = classify(text, ["nginx.conf"])
        self.assertNotEqual(level, "LOW")

    def test_kubernetes_keyword_not_low(self):
        text = "Fix Kubernetes deployment manifest"
        level, score, reasons = classify(text, ["k8s/deploy.yaml"])
        self.assertNotEqual(level, "LOW")


if __name__ == "__main__":
    unittest.main()
