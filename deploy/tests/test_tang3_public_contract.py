import json
import os
import re
import unittest


ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class TestTang3ComposeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = read("deploy", "compose.app-gpu.yml")
        cls.dockerfile = read("deploy", "Dockerfile.app-gpu")

    def test_cuda_runtime_and_pinned_torch(self):
        self.assertIn("nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04", self.dockerfile)
        self.assertIn('"torch==2.2.2"', self.dockerfile)
        self.assertIn("RNABAG_PIP_INDEX_URL", self.dockerfile)
        self.assertRegex(
            self.dockerfile,
            r'pip install\s+\\\n\s+--index-url "\$RNABAG_PIP_INDEX_URL"\s+\\\n\s+--upgrade pip',
        )
        self.assertIn("PIP_RETRIES=10", self.dockerfile)
        self.assertNotIn("assert torch.cuda.is_available()", self.dockerfile)

    def test_one_gpu_is_reserved_and_logical_device_is_zero(self):
        self.assertIn("device_ids: [\"${RNABAG_GPU_DEVICE_ID:?RNABAG_GPU_DEVICE_ID is required}\"]", self.compose)
        self.assertIn("capabilities: [gpu]", self.compose)
        self.assertIn("RNABAG_DEVICE: cuda:0", self.compose)
        self.assertNotIn("CUDA_VISIBLE_DEVICES", self.compose)
        self.assertEqual(self.compose.count("capabilities: [gpu]"), 1)

    def test_mounts_and_hardening(self):
        self.assertIn('${RNABAG_CODE_DIR:?RNABAG_CODE_DIR is required}:/app:ro', self.compose)
        self.assertIn('${RNABAG_TEMP_DIR:?RNABAG_TEMP_DIR is required}:${RNABAG_TEMP_DIR}:rw', self.compose)
        self.assertIn("read_only: true", self.compose)
        self.assertIn("cap_drop: [ALL]", self.compose)
        self.assertIn("no-new-privileges:true", self.compose)
        self.assertEqual(self.compose.count("/app:ro"), 1)
        self.assertEqual(self.compose.count(":rw\""), 1)

    def test_bind_and_single_worker(self):
        self.assertIn('${RNABAG_APP_BIND_IP:?RNABAG_APP_BIND_IP is required}', self.compose)
        self.assertIn("os.environ['RNABAG_APP_BIND_IP']", self.compose)
        self.assertNotIn("http://127.0.0.1:${RNABAG_APP_PORT", self.compose)
        self.assertIn('"1"', self.compose)
        self.assertNotIn('"0.0.0.0"', self.compose)
        self.assertIn("network_mode: host", self.compose)

    def test_no_persistence_ports_in_gpu_project(self):
        self.assertNotIn("postgres", self.compose.lower())
        self.assertNotIn("minio", self.compose.lower())
        self.assertNotIn("ports:", self.compose)

    def test_persistence_migrate_has_stable_fallback_image_name(self):
        persistence = read("deploy", "compose.persistence.yml")
        self.assertIn("image: rnabag-persistence:local", persistence)


class TestTang3ScriptContract(unittest.TestCase):
    def test_bootstrap_defaults_and_secret_hygiene(self):
        script = read("deploy", "bootstrap-tang3-config.sh")
        self.assertIn("/home/johnny/services/rnabag", script)
        self.assertIn("/mnt/nas/johnny/rnabag/RNABagShow", script)
        self.assertIn("chmod 600", script)
        self.assertIn("https://mirrors.aliyun.com/pypi/simple", script)
        self.assertIn('chmod 700 "$CONFIG_DIR" "$DEPLOY_ROOT/postgres"', script)
        self.assertIn("Refusing to overwrite", script)
        self.assertNotRegex(script, r"echo\s+.*PASSWORD")

    def test_start_checks_dependencies_and_gpu(self):
        script = read("deploy", "tang3-up.sh")
        for required in ("docker info", "nvidia-smi", "PostgreSQL and MinIO must be running first", "RNABAG_CODE_DIR", "RNABAG_TEMP_DIR"):
            self.assertIn(required, script)
        self.assertIn("is not assigned to this host", script)
        self.assertIn("compose_build_supported", script)
        self.assertIn("DOCKER_BUILDKIT=0 docker build", script)
        self.assertIn("--build-arg \"RNABAG_PIP_INDEX_URL=$PIP_INDEX_URL\"", script)
        self.assertIn("--no-build", script)
        self.assertIn("compose.app-gpu.yml", script)

    def test_persistence_start_has_old_buildx_fallback(self):
        script = read("deploy", "persistence-up.sh")
        self.assertIn("compose_build_supported", script)
        self.assertIn("DOCKER_BUILDKIT=0 docker build", script)
        self.assertIn("--tag rnabag-persistence:local", script)
        self.assertIn("--build-arg \"RNABAG_PIP_INDEX_URL=$PIP_INDEX_URL\"", script)
        self.assertIn("run --rm migrate", script)
        self.assertNotIn("run --rm --build migrate", script)

    def test_smoke_uses_tailnet_bind_address(self):
        script = read("deploy", "tang3-smoke-test.sh")
        self.assertIn("RNABAG_APP_BIND_IP", script)
        self.assertIn("/api/v1/health/live", script)
        self.assertIn("/api/v1/health/ready", script)
        self.assertIn("/api/v1/tasks", script)
        self.assertIn('"$BASE_URL/"', script)

    def test_status_and_down_supply_compose_user_ids(self):
        for name in ("tang3-status.sh", "tang3-down.sh"):
            script = read("deploy", name)
            self.assertIn('export RNABAG_UID="${RNABAG_UID:-$(id -u)}"', script)
            self.assertIn('export RNABAG_GID="${RNABAG_GID:-$(id -g)}"', script)
            self.assertIn("Tang3 config is missing", script)


class TestPublicProxyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conf = read("deploy", "public-proxy", "nginx-rnabag-public.conf")
        cls.limits = read("deploy", "public-proxy", "nginx-rnabag-limits.conf")

    def test_public_listener_and_upstream(self):
        self.assertIn("listen 80 default_server", self.conf)
        self.assertIn("server_name _ rnabag.com www.rnabag.com", self.conf)
        self.assertIn("proxy_pass http://127.0.0.1:18000", self.conf)
        self.assertNotIn("root ", self.conf)
        self.assertNotIn("API_NOT_ENABLED", self.conf)
        self.assertNotIn("events {", self.conf)
        self.assertNotIn("http {", self.conf)

    def test_proxy_does_not_buffer_or_spill(self):
        for directive in ("proxy_request_buffering off", "proxy_buffering off", "proxy_cache off", "proxy_max_temp_file_size 0", "access_log off"):
            self.assertIn(directive, self.conf)

    def test_limits_and_long_inference_timeouts(self):
        self.assertIn("client_max_body_size 64m", self.conf)
        self.assertIn("limit_conn_zone", self.limits)
        self.assertIn("limit_req_zone", self.limits)
        self.assertIn("proxy_read_timeout 300s", self.conf)
        self.assertIn("proxy_send_timeout 300s", self.conf)

    def test_health_and_standard_headers(self):
        self.assertIn("location = /healthz", self.conf)
        self.assertRegex(self.conf, r'add_header\s+Cache-Control\s+"no-store"\s+always;')
        for header in ("Host", "X-Real-IP", "X-Forwarded-For", "X-Forwarded-Proto"):
            self.assertRegex(self.conf, rf"proxy_set_header {re.escape(header)}")
        self.assertNotIn("9000", self.conf)
        self.assertNotIn("5432", self.conf)


class TestPublicFrontendContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = read("frontend", "index.html")
        cls.lab = read("frontend", "ranbag_lab.html")
        cls.runtime = read("frontend", "rnabag-runtime-config.js")
        cls.variant = read("frontend", "rnabag-variant.js")

    def test_canonical_entries_share_new_asset_version(self):
        for page in (self.index, self.lab):
            self.assertIn('rnabag-runtime-config.js?v=20260721', page)
            self.assertIn('rnabag-variant.js?v=20260721', page)
            self.assertNotIn('v=20260717', page)
            self.assertNotIn('v=20260720', page)

    def test_full_runtime_config_has_exact_immutable_public_host_allowlist(self):
        self.assertIn('mode: "full"', self.runtime)
        match = re.search(r"publicHosts: Object\.freeze\(\[(.*?)\]\)", self.runtime)
        self.assertIsNotNone(match)
        self.assertEqual(
            json.loads(f"[{match.group(1)}]"),
            ["47.116.63.212", "rnabag.com", "www.rnabag.com"],
        )

    def test_public_app_requires_exact_configured_host_membership(self):
        self.assertIn('runtimeConfig.mode === "full"', self.variant)
        self.assertIn('["http:", "https:"].includes(window.location.protocol)', self.variant)
        self.assertIn('publicHosts.includes(window.location.hostname)', self.variant)
        self.assertNotIn('!localHostname', self.variant)
        self.assertIn('document.body.classList.toggle("public-app", publicApp)', self.variant)

        match = re.search(r"publicHosts: Object\.freeze\(\[(.*?)\]\)", self.runtime)
        configured = set(json.loads(f"[{match.group(1)}]"))
        allowed = ["47.116.63.212", "rnabag.com", "www.rnabag.com"]
        blocked = ["127.0.0.1", "localhost", "::1", "172.16.17.4", "100.113.222.1"]
        for hostname in allowed:
            self.assertIn(hostname, configured)
        for hostname in blocked:
            self.assertNotIn(hostname, configured)

    def test_public_app_warning_and_controls_remain_enabled(self):
        self.assertIn("临时公共上传已开放", self.variant)
        self.assertIn("私密保存在 tang3", self.variant)
        self.assertIn("无登录或 TLS", self.variant)
        self.assertIn("PHI", self.variant)
        self.assertIn("不用于临床诊断", self.variant)
        self.assertIn('button.disabled = publicPreview', self.variant)
        self.assertIn('button.textContent = publicPreview ? "推理服务暂未开放" : publicApp ? "提交公共分析"', self.variant)
        self.assertIn('.stage-subtitle, .js-dropzone span, .story-chapter p', self.variant)

    def test_public_preview_still_gates_upload_and_inference(self):
        self.assertIn('if (publicPreview) return false;', self.variant)
        self.assertIn('if (publicPreview) return;', self.variant)
        self.assertIn('input.disabled = true', self.variant)
