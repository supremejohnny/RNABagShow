import unittest
import json
import os
import re


class TestPublicPreviewNginxContract(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        conf_path = os.path.join(
            repo_root, "deploy", "public-preview", "nginx-rnabag-preview.conf"
        )
        with open(conf_path) as f:
            self.conf = f.read()

        js_path = os.path.join(
            repo_root, "deploy", "public-preview", "rnabag-runtime-config.js"
        )
        with open(js_path) as f:
            self.runtime_js = f.read()

        variant_js_path = os.path.join(repo_root, "frontend", "rnabag-variant.js")
        with open(variant_js_path) as f:
            self.variant_js = f.read()

        with open(os.path.join(repo_root, "frontend", "index.html")) as handle:
            self.index_html = handle.read()
        with open(os.path.join(repo_root, "frontend", "ranbag_lab.html")) as handle:
            self.lab_html = handle.read()

    def test_probe_location_exists(self):
        self.assertIn("location = /probe/ping", self.conf)

    def test_probe_upstream_address(self):
        self.assertIn("proxy_pass http://100.113.222.1:18080/probe/ping", self.conf)

    def test_probe_method_restriction(self):
        self.assertIn("limit_except GET HEAD", self.conf)
        self.assertIn("deny all", self.conf)

    def test_probe_cache_disabled(self):
        self.assertIn("proxy_cache off", self.conf)
        self.assertIn("proxy_no_cache 1", self.conf)
        self.assertIn("proxy_cache_bypass 1", self.conf)

    def test_probe_buffering_disabled(self):
        self.assertIn("proxy_request_buffering off", self.conf)
        self.assertIn("proxy_buffering off", self.conf)

    def test_probe_timeouts_set(self):
        self.assertIn("proxy_connect_timeout 5s", self.conf)
        self.assertIn("proxy_read_timeout 5s", self.conf)
        self.assertIn("proxy_send_timeout 5s", self.conf)

    def test_probe_access_log_off(self):
        self.assertIn("access_log off", self.conf)

    def test_probe_no_duplicate_cache_control(self):
        location_block = self._extract_location_block("/probe/ping")
        self.assertIsNotNone(location_block)
        add_headers = re.findall(
            r"add_header\s+Cache-Control\s+\"no-store\"", location_block
        )
        self.assertEqual(
            len(add_headers),
            0,
            "Probe location must not override Cache-Control; upstream already supplies it",
        )

    def test_api_v1_blocked(self):
        self.assertIn("location ^~ /api/v1/", self.conf)
        self.assertIn("503", self.conf)
        self.assertIn("API_NOT_ENABLED", self.conf)

    def test_api_v1_returns_503_json(self):
        match = re.search(
            r"return\s+503\s+'([^']+)'", self.conf
        )
        self.assertIsNotNone(match)
        body = json.loads(match.group(1))
        self.assertEqual(body["detail"]["code"], "API_NOT_ENABLED")
        self.assertIn("inference", body["detail"]["message"].lower())

    def test_same_origin_csp(self):
        self.assertIn("connect-src 'self'", self.conf)

    def test_no_upload_enablement(self):
        self.assertNotIn("uploads", self.conf.lower())
        self.assertNotIn("demo-data", self.conf.lower())
        self.assertNotIn("sample-data", self.conf.lower())
        self.assertNotIn("checkpoints", self.conf.lower())
        self.assertNotIn("persistence", self.conf.lower())

    def test_frontend_probe_path_config(self):
        self.assertIn("probePath", self.runtime_js)
        self.assertIn("/probe/ping", self.runtime_js)

    def test_frontend_public_preview_mode(self):
        self.assertIn('"public-preview"', self.runtime_js)

    def test_preview_server_sets_no_store_at_server_level(self):
        self.assertRegex(self.conf, r'add_header\s+Cache-Control\s+"no-store"\s+always;')
        location_block = self._extract_location_block("/api/v1/")
        self.assertIsNotNone(location_block)
        self.assertNotIn("add_header Cache-Control", location_block)

    def test_canonical_frontend_assets_use_shared_new_version(self):
        for page in (self.index_html, self.lab_html):
            self.assertIn("rnabag-runtime-config.js?v=20260721", page)
            self.assertIn("rnabag-variant.js?v=20260721", page)
            self.assertNotIn("20260717", page)
            self.assertNotIn("20260720", page)

    # -- rnabag-variant.js public preview probe contract --

    def test_variant_js_appends_banner_indicator(self):
        self.assertIn(".public-preview-banner", self.variant_js)
        self.assertIn("pong-indicator", self.variant_js)

    def test_variant_js_uses_textContent_not_innerHTML_for_response(self):
        self.assertIn("textContent", self.variant_js)
        fetch_section = self.variant_js[self.variant_js.index("function applyPublicPreview"):self.variant_js.index("ensureDemoControls")] if "function applyPublicPreview" in self.variant_js else self.variant_js
        self.assertNotIn("innerHTML", fetch_section)

    def test_variant_js_checks_response_ok(self):
        self.assertIn("response.ok", self.variant_js)

    def test_variant_js_requires_exact_trimmed_pong(self):
        self.assertIn('text.trim() === "pong"', self.variant_js)

    def test_variant_js_uses_cache_no_store(self):
        self.assertIn('cache: "no-store"', self.variant_js)

    def test_variant_js_uses_abort_controller(self):
        self.assertIn("AbortController", self.variant_js)
        self.assertIn("controller.abort()", self.variant_js)
        self.assertIn("5000", self.variant_js[self.variant_js.index("AbortController"):self.variant_js.index("AbortController") + 120])

    def test_variant_js_clears_timer(self):
        self.assertIn(".finally(() => clearTimeout(timer))", self.variant_js)

    def test_variant_js_generic_unavailable_message(self):
        unavailable_count = self.variant_js.count("unavailable")
        self.assertGreaterEqual(unavailable_count, 2)

    # -- Docker/Compose static contract --

    def test_dockerfile_no_adduser(self):
        repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        dockerfile_path = os.path.join(
            repo_root, "deploy", "pong_probe", "Dockerfile"
        )
        with open(dockerfile_path) as f:
            content = f.read()
        self.assertNotIn("adduser", content)
        self.assertNotIn("adduser", content.lower())

    def test_dockerfile_numeric_non_root_user(self):
        repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        dockerfile_path = os.path.join(
            repo_root, "deploy", "pong_probe", "Dockerfile"
        )
        with open(dockerfile_path) as f:
            content = f.read()
        self.assertIn("USER 65534:65534", content)

    def test_compose_no_volumes(self):
        repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        compose_path = os.path.join(
            repo_root, "deploy", "compose.pong-probe.yml"
        )
        with open(compose_path) as f:
            content = f.read()
        self.assertNotIn("volumes", content)

    def test_compose_build_context_points_to_pong_probe(self):
        repo_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        compose_path = os.path.join(
            repo_root, "deploy", "compose.pong-probe.yml"
        )
        with open(compose_path) as f:
            content = f.read()
        self.assertIn("context: pong_probe", content)

    def _extract_location_block(self, location_pattern):
        lines = self.conf.split("\n")
        in_block = False
        block_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("location") and location_pattern in stripped:
                in_block = True
                block_lines = [stripped]
                continue
            if in_block:
                block_lines.append(stripped)
                if stripped == "}":
                    return "\n".join(block_lines)
        return None
