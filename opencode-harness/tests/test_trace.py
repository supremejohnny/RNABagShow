"""Tests for structured execution trace generator."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from trace import (
    make_filename,
    validate_trace,
    generate_run_id,
    timestamp,
    TRACE_SCHEMA_VERSION,
)


class TestTrace(unittest.TestCase):

    def setUp(self):
        self.minimal_trace = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "run_id": "abcd1234abcd1234",
            "task_id": "test-task-1",
            "phase": "coding",
            "agent": "coding",
            "provider": "deepseek",
            "model": "deepseek/deepseek-v4-pro",
            "started_at": "2026-07-22T12:00:00+00:00",
            "finished_at": "",
            "git_head": "abc123def456",
            "baseline_diff_hash": "1234567890abcdef",
            "input_artifacts": [],
            "output_artifacts": [],
            "actions": [],
            "commands": [],
            "validation": [],
            "usage": {
                "input_tokens": None,
                "output_tokens": None,
                "cache_read_tokens": None,
                "cost": None,
            },
            "result": "success",
            "failure_reason": "",
            "next_action": "",
        }

    def test_minimal_valid_trace(self):
        errors = validate_trace(self.minimal_trace)
        self.assertEqual(errors, [])

    def test_missing_required_field(self):
        trace = dict(self.minimal_trace)
        del trace["run_id"]
        errors = validate_trace(trace)
        self.assertIn("missing required field: run_id", errors)

    def test_missing_multiple_fields(self):
        trace = {"schema_version": TRACE_SCHEMA_VERSION}
        errors = validate_trace(trace)
        self.assertTrue(len(errors) > 1)
        self.assertIn("missing required field: run_id", errors)
        self.assertIn("missing required field: task_id", errors)

    def test_wrong_schema_version(self):
        trace = dict(self.minimal_trace)
        trace["schema_version"] = 999
        errors = validate_trace(trace)
        self.assertTrue(any("schema_version" in e for e in errors))

    def test_invalid_phase_and_agent_fail(self):
        trace = dict(self.minimal_trace)
        trace["phase"] = "chatting"
        trace["agent"] = "unbounded-agent"
        errors = validate_trace(trace)
        self.assertTrue(any("invalid phase" in error for error in errors))
        self.assertTrue(any("invalid agent" in error for error in errors))

    def test_null_usage_values_are_valid(self):
        errors = validate_trace(self.minimal_trace)
        self.assertEqual(errors, [])

    def test_non_null_numeric_usage_values(self):
        trace = dict(self.minimal_trace)
        trace["usage"] = {
            "input_tokens": 1500,
            "output_tokens": 500,
            "cache_read_tokens": 0,
            "cost": 0.003,
        }
        errors = validate_trace(trace)
        self.assertEqual(errors, [])

    def test_string_usage_value_invalid(self):
        trace = dict(self.minimal_trace)
        trace["usage"] = {
            "input_tokens": "many",
            "output_tokens": None,
            "cache_read_tokens": None,
            "cost": None,
        }
        errors = validate_trace(trace)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("input_tokens" in e for e in errors))

    def test_non_dict_input(self):
        errors = validate_trace("not a dict")
        self.assertTrue(len(errors) > 0)

    def test_non_dict_usage(self):
        trace = dict(self.minimal_trace)
        trace["usage"] = "not a dict"
        errors = validate_trace(trace)
        self.assertTrue(any("usage" in e for e in errors))

    def test_list_fields_must_be_lists(self):
        trace = dict(self.minimal_trace)
        trace["input_artifacts"] = "not a list"
        errors = validate_trace(trace)
        self.assertTrue(any("input_artifacts" in e for e in errors))

    def test_run_id_generation(self):
        rid1 = generate_run_id()
        rid2 = generate_run_id()
        self.assertNotEqual(rid1, rid2)
        self.assertEqual(len(rid1), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in rid1))

    def test_timestamp_format(self):
        ts = timestamp()
        self.assertRegex(ts, r"^\d{8}T\d{6}$")

    def test_filename_generation(self):
        name = make_filename("20260722T120000", "task-1", "coding", "abcd1234")
        self.assertTrue(name.startswith("20260722T120000"))
        self.assertTrue(name.endswith(".json"))
        self.assertIn("task-1", name)
        self.assertIn("coding", name)
        self.assertIn("abcd1234", name)

    def test_filename_unique_per_role(self):
        name_coding = make_filename("20260722T120000", "task-1", "coding", "abcd")
        name_review = make_filename("20260722T120000", "task-1", "review", "abcd")
        self.assertNotEqual(name_coding, name_review)

    def test_filename_sanitizes_special_chars(self):
        name = make_filename("20260722T120000", "task/with spaces", "coding", "abcd")
        self.assertNotIn("/", name)
        self.assertNotIn(" ", name)

    def test_full_trace_roundtrip(self):
        trace = dict(self.minimal_trace)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(trace, f)
            tmp_path = f.name
        try:
            errors = validate_trace(trace)
            self.assertEqual(errors, [])
        finally:
            os.unlink(tmp_path)

    def test_no_secrets_in_trace(self):
        trace = dict(self.minimal_trace)
        json_str = json.dumps(trace)
        self.assertNotIn("password", json_str.lower())
        self.assertNotIn("secret", json_str.lower())
        self.assertNotIn("apikey", json_str.lower())
        self.assertNotIn("api_key", json_str.lower())


if __name__ == "__main__":
    unittest.main()
