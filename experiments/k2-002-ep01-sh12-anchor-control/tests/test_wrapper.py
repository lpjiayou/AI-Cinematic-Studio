from __future__ import annotations

from contextlib import ExitStack
import binascii
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import zlib


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_controlled_experiment as wrapper  # noqa: E402
from control_runner_core import ControlError, canonical_sha256, text_sha256  # noqa: E402


def png_bytes(rgb: tuple[int, int, int], width: int = 704, height: int = 1280) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * width
    image = zlib.compress(row * height, level=9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", image) + chunk(b"IEND", b"")


class Fixture:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.package = self.root / "package"
        self.evidence = self.root / "evidence"
        self.models = self.root / "models"
        self.comfy = self.root / "ComfyUI"
        self.runner = self.root / "runner"
        for path in (
            self.package / "materialized",
            self.package / "anchors",
            self.evidence / "inputs",
            self.models / "diffusion_models",
            self.models / "text_encoders",
            self.models / "vae",
            self.comfy / "input",
            self.comfy / "output",
            self.runner / "experiments",
        ):
            path.mkdir(parents=True, mode=0o700)
        os.chmod(self.evidence, 0o700)
        os.chmod(self.comfy / "input", 0o700)
        os.chmod(self.comfy / "output", 0o700)

        old = png_bytes((12, 34, 56))
        new = png_bytes((13, 34, 56))
        self.old_sha = sha256(old).hexdigest()
        self.new_sha = sha256(new).hexdigest()
        (self.package / "anchors" / "EP01_SH12_anchor_v2.png").write_bytes(old)
        self.new_anchor = self.evidence / "inputs" / "EP01_SH12_anchor_pre_step_r5.png"
        self.new_anchor.write_bytes(new)

        self.positive = "frozen R3 positive"
        self.negative = "frozen R3 negative"
        self.workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "device": "default", "type": "wan"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
            "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": self.positive}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": self.negative}},
            "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"batch_size": 1, "height": 1280, "length": 49, "start_image": ["12", 0], "vae": ["3", 0], "width": 704}},
            "8": {"class_type": "KSampler", "inputs": {"cfg": 5.0, "denoise": 1.0, "latent_image": ["7", 0], "model": ["4", 0], "negative": ["6", 0], "positive": ["5", 0], "sampler_name": "uni_pc", "scheduler": "simple", "seed": 596974677755723, "steps": 20}},
            "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
            "10": {"class_type": "CreateVideo", "inputs": {"bit_depth": 8, "fps": 24, "images": ["9", 0]}},
            "11": {"class_type": "SaveVideo", "inputs": {"codec": "h264", "filename_prefix": "k2-002-ep01-i2v-v2/EP01_SH12-v2-technical-evidence", "format": "mp4", "video": ["10", 0]}},
            "12": {"class_type": "LoadImage", "inputs": {"image": f"k2-002-ep01-i2v-v2/{self.old_sha}.png"}},
        }
        self.workflow_path = self.package / "materialized" / "EP01_SH12.workflow.json"
        self.workflow_path.write_text(
            json.dumps(self.workflow, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        rows = [{"shotId": f"EP01_SH{i:02d}"} for i in range(1, 19)]
        rows[11].update(
            {
                "startAnchorPath": "anchors/EP01_SH12_anchor_v2.png",
                "startAnchorSha256": self.old_sha,
                "seed": 596974677755723,
                "positivePrompt": self.positive,
                "negativePrompt": self.negative,
            }
        )
        self.shots_path = self.package / "shots.json"
        self.shots_path.write_text(
            json.dumps({"shots": rows}, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

        model_payloads = {"UNET": b"unet", "TEXT_ENCODER": b"text", "VAE": b"vae"}
        self.model_hashes = {}
        for role, (_, _, filename) in wrapper.EXPECTED_MODEL_LOADERS.items():
            folder = {"UNET": "diffusion_models", "TEXT_ENCODER": "text_encoders", "VAE": "vae"}[role]
            payload = model_payloads[role]
            (self.models / folder / filename).write_bytes(payload)
            self.model_hashes[role] = sha256(payload).hexdigest()

        self.manifest_path = self.runner / "experiments" / "EP01_SH12_R5_ANCHOR_ONLY.json"
        self.policy = wrapper.RunnerPolicy(
            package_root=self.package,
            evidence_root=self.evidence,
            model_root=self.models,
            comfyui_root=self.comfy,
            manifest_path=self.manifest_path,
            base_url="http://127.0.0.1:18188",
            shots_sha256=sha256(self.shots_path.read_bytes()).hexdigest(),
            workflow_file_sha256=sha256(self.workflow_path.read_bytes()).hexdigest(),
            workflow_canonical_sha256=canonical_sha256(self.workflow),
            old_anchor_sha256=self.old_sha,
            positive_prompt_sha256=text_sha256(self.positive),
            negative_prompt_sha256=text_sha256(self.negative),
            model_sha256=self.model_hashes,
            comfyui_commit="a" * 40,
            poll_seconds=0.001,
            timeout_seconds=2,
            strict_deployment_paths=False,
        )
        manifest = {
            "schemaVersion": 1,
            "experimentId": "K2-002-EP01-SH12-R5-ANCHOR-ONLY",
            "authorityState": "TECHNICAL_EVIDENCE_ONLY",
            "publicationAllowed": False,
            "canonicalMutations": 0,
            "shotId": "EP01_SH12",
            "changedVariable": "START_ANCHOR_ONLY",
            "maxRuns": 1,
            "baseline": {
                "shotsSha256": self.policy.shots_sha256,
                "workflowFileSha256": self.policy.workflow_file_sha256,
                "workflowCanonicalSha256": self.policy.workflow_canonical_sha256,
                "anchorSha256": self.old_sha,
                "seed": 596974677755723,
                "positivePromptSha256": self.policy.positive_prompt_sha256,
                "negativePromptSha256": self.policy.negative_prompt_sha256,
                "modelSha256": dict(self.model_hashes),
                "comfyuiCommit": self.policy.comfyui_commit,
            },
            "variant": {
                "anchorPath": str(self.new_anchor),
                "anchorSha256": self.new_sha,
                "seedPolicy": "FIXED_BASELINE_SEED",
                "seed": 596974677755723,
            },
            "allowedWorkflowDiffPointers": ["/12/inputs/image"],
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        provenance = {
            "schemaVersion": 1,
            "experimentId": "K2-002-EP01-SH12-R5-ANCHOR-ONLY",
            "authorityState": "TECHNICAL_EVIDENCE_ONLY",
            "publicationAllowed": False,
            "canonicalMutations": 0,
            "assetState": "DERIVED_TECHNICAL_CANDIDATE_NOT_CANONICAL",
            "source": {"path": "anchors/EP01_SH12_anchor_v2.png", "sha256": self.old_sha},
            "output": {"path": str(self.new_anchor), "sha256": self.new_sha, "width": 704, "height": 1280},
            "editMethod": "controlled local pose edit",
            "reviewer": "test-reviewer",
            "reviewedAt": "2026-08-28T00:00:00Z",
            "anchorReadiness": {
                "passed": True,
                "score": "12/12",
                "checks": [{"id": i, "criterion": wrapper.READINESS_CRITERIA[i - 1], "passed": True, "finding": f"check {i} passed"} for i in range(1, 13)],
            },
        }
        self.provenance_path = self.new_anchor.with_suffix(".provenance.json")
        self.provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    def close(self):
        self.temporary.cleanup()

    def patches(self, listeners=None):
        return ExitStack()


class FakeComfy:
    def __init__(
        self,
        fixture: Fixture,
        fail_post: bool = False,
        output_freshness: str = "new",
    ):
        self.fixture = fixture
        self.fail_post = fail_post
        self.post_count = 0
        self.queue_get_count = 0
        self.last_prompt = None
        self.prompt_id = "prompt-r5"
        output_dir = fixture.comfy / "output" / "k2-002-ep01-i2v-v2"
        output_dir.mkdir(parents=True, exist_ok=True)
        self.output_name = "EP01_SH12-v2-technical-evidence_00001_.mp4"
        self.output_path = output_dir / self.output_name
        if output_freshness not in {
            "new",
            "new_rounded",
            "new_stale",
            "preexisting_recent",
        }:
            raise ValueError(f"unknown output freshness fixture: {output_freshness}")
        self.output_freshness = output_freshness
        if output_freshness == "preexisting_recent":
            self.output_path.write_bytes(
                b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
            )

        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                del format, args

            def _json(self, value, status=200):
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path != "/prompt":
                    self._json({}, 404)
                    return
                owner.post_count += 1
                length = int(self.headers.get("Content-Length", "0"))
                owner.last_prompt = json.loads(self.rfile.read(length))
                if owner.fail_post:
                    self._json({"error": "fail"}, 500)
                else:
                    if owner.output_freshness != "preexisting_recent":
                        owner.output_path.write_bytes(
                            b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
                        )
                        if owner.output_freshness == "new_rounded":
                            rounded_ns = (time.time_ns() // 1_000_000_000) * 1_000_000_000
                            os.utime(owner.output_path, ns=(rounded_ns, rounded_ns))
                        elif owner.output_freshness == "new_stale":
                            stale_ns = time.time_ns() - 60_000_000_000
                            os.utime(owner.output_path, ns=(stale_ns, stale_ns))
                    self._json({"prompt_id": owner.prompt_id})

            def do_GET(self):
                if self.path == "/system_stats":
                    self._json({"system": {"comfyui_version": "0.28.0", "python_version": "3.12.7", "pytorch_version": "2.11.0+cu126"}, "devices": [{"type": "cuda", "name": "NVIDIA A100-PCIE-40GB"}]})
                elif self.path == "/object_info":
                    value = {name: {} for name in wrapper.REQUIRED_NODES}
                    value["UNETLoader"] = {"input": {"required": {"unet_name": [["wan2.2_ti2v_5B_fp16.safetensors"]]}}}
                    value["CLIPLoader"] = {"input": {"required": {"clip_name": [["umt5_xxl_fp8_e4m3fn_scaled.safetensors"]]}}}
                    value["VAELoader"] = {"input": {"required": {"vae_name": [["wan2.2_vae.safetensors"]]}}}
                    self._json(value)
                elif self.path == "/queue":
                    owner.queue_get_count += 1
                    self._json({"queue_running": [], "queue_pending": []})
                elif self.path == f"/history/{owner.prompt_id}":
                    self._json({owner.prompt_id: {"prompt": [0, owner.last_prompt["prompt"], {"client_id": wrapper.CLIENT_ID}, ["11"]], "status": {"completed": True, "messages": []}, "outputs": {"11": {"gifs": [{"filename": owner.output_name, "subfolder": "k2-002-ep01-i2v-v2", "type": "output"}]}}}})
                else:
                    self._json({}, 404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self.server.server_address
        self.fixture.policy = wrapper.RunnerPolicy(
            **{**self.fixture.policy.__dict__, "base_url": f"http://{host}:{port}"}
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.env = mock.patch.dict(
            os.environ,
            {
                "K2_EP01_I2V_ACK": "TECHNICAL_EVIDENCE_ONLY",
                "K2_EP01_EXPERIMENT_ACK": "ANCHOR_ONLY_FIXED_BASELINE_SEED",
            },
            clear=False,
        )
        self.env.start()
        self.git = mock.patch.object(
            wrapper,
            "_git_facts",
            return_value={"commit": self.fx.policy.comfyui_commit, "branch": "master", "trackedWorktreeClean": True},
        )
        self.git.start()
        self.processes = mock.patch.object(wrapper, "_find_conflicting_processes", return_value=[])
        self.processes.start()

    def tearDown(self):
        self.processes.stop()
        self.git.stop()
        self.env.stop()
        self.fx.close()

    def dry(self):
        with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=[]), mock.patch.object(wrapper, "_gpu_compute_pids", return_value=[]):
            return wrapper.run_dry_run(self.fx.manifest_path, self.fx.policy)

    def test_w01_valid_dry_run_is_zero_network_zero_lock_zero_stage_and_23_gates(self):
        with mock.patch.object(wrapper, "ComfyTransport", side_effect=AssertionError("network")):
            receipt = self.dry()
        self.assertEqual(receipt["networkCalls"], 0)
        self.assertEqual(receipt["gpuOrProviderCalls"], 0)
        self.assertFalse((self.fx.evidence / "RUN_ATTEMPT_1.json").exists())
        self.assertFalse((self.fx.comfy / "input" / "k2-002-ep01-i2v-r5-anchor-only").exists())
        self.assertEqual(len(receipt["gates"]), 23)
        self.assertEqual(set(receipt["gates"].values()), {"PASS"})

    def test_w02_manifest_cannot_redefine_compiled_pins_or_add_fields(self):
        manifest = json.loads(self.fx.manifest_path.read_text())
        manifest["baseline"]["shotsSha256"] = "f" * 64
        manifest["unexpected"] = True
        self.fx.manifest_path.write_text(json.dumps(manifest))
        with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=[]), mock.patch.object(wrapper, "_gpu_compute_pids", return_value=[]), self.assertRaises(ControlError):
            wrapper.run_dry_run(self.fx.manifest_path, self.fx.policy)
        self.assertFalse((self.fx.evidence / "RUN_ATTEMPT_1.json").exists())

    def test_w03_each_baseline_file_mutation_fails_before_lock(self):
        for target in (self.fx.shots_path, self.fx.workflow_path, self.fx.package / "anchors" / "EP01_SH12_anchor_v2.png"):
            with self.subTest(target=target.name):
                original = target.read_bytes()
                target.write_bytes(original + b"x")
                with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=[]), mock.patch.object(wrapper, "_gpu_compute_pids", return_value=[]), self.assertRaises(ControlError):
                    wrapper.run_dry_run(self.fx.manifest_path, self.fx.policy)
                target.write_bytes(original)
                self.assertFalse((self.fx.evidence / "RUN_ATTEMPT_1.json").exists())

    def test_w04_variant_png_and_readiness_are_verified(self):
        provenance = json.loads(self.fx.provenance_path.read_text())
        provenance["anchorReadiness"]["checks"][11]["passed"] = False
        provenance["anchorReadiness"]["score"] = "11/12"
        self.fx.provenance_path.write_text(json.dumps(provenance))
        with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=[]), mock.patch.object(wrapper, "_gpu_compute_pids", return_value=[]), self.assertRaisesRegex(ControlError, "12/12"):
            wrapper.run_dry_run(self.fx.manifest_path, self.fx.policy)

    def test_w05_each_actual_model_digest_is_observed(self):
        for role, (_, _, filename) in wrapper.EXPECTED_MODEL_LOADERS.items():
            folder = {"UNET": "diffusion_models", "TEXT_ENCODER": "text_encoders", "VAE": "vae"}[role]
            model = self.fx.models / folder / filename
            original = model.read_bytes()
            with self.subTest(role=role):
                model.write_bytes(b"changed")
                with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=[]), mock.patch.object(wrapper, "_gpu_compute_pids", return_value=[]), self.assertRaisesRegex(ControlError, f"{role} model"):
                    wrapper.run_dry_run(self.fx.manifest_path, self.fx.policy)
                model.write_bytes(original)

    def test_w05b_comfyui_commit_pin_and_dirty_tree_fail(self):
        self.git.stop()
        try:
            with mock.patch.object(wrapper, "_git_command", side_effect=["b" * 40, "master", ""]), self.assertRaisesRegex(ControlError, "commit"):
                wrapper._git_facts(self.fx.comfy, self.fx.policy)
            with mock.patch.object(wrapper, "_git_command", side_effect=[self.fx.policy.comfyui_commit, "master", " M main.py"]), self.assertRaisesRegex(ControlError, "dirty"):
                wrapper._git_facts(self.fx.comfy, self.fx.policy)
        finally:
            self.git.start()

    def test_w06_wrong_evidence_path_and_existing_complete_fail_closed(self):
        wrong = wrapper.RunnerPolicy(**{**self.fx.policy.__dict__, "evidence_root": self.fx.root / "other"})
        with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=[]), mock.patch.object(wrapper, "_gpu_compute_pids", return_value=[]), self.assertRaises(ControlError):
            wrapper.run_dry_run(self.fx.manifest_path, wrong)
        (self.fx.evidence / "COMPLETE.json").write_text("{}")
        with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=[]), mock.patch.object(wrapper, "_gpu_compute_pids", return_value=[]), self.assertRaisesRegex(ControlError, "COMPLETE"):
            wrapper.run_dry_run(self.fx.manifest_path, self.fx.policy)

    def test_w07_execute_revalidates_after_staging_and_consumes_attempt_on_toctou(self):
        self.dry()
        original_stage = wrapper._stage_variant

        def mutate(prepared, policy):
            result = original_stage(prepared, policy)
            self.fx.shots_path.write_bytes(self.fx.shots_path.read_bytes() + b" ")
            return result

        with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=["127.0.0.1"]), mock.patch.object(wrapper, "_stage_variant", side_effect=mutate), mock.patch.object(wrapper, "_verify_live_runtime", return_value={}), mock.patch.object(wrapper, "_verify_queue_empty", return_value={}), self.assertRaises(ControlError):
            wrapper.run_execute(self.fx.manifest_path, self.fx.policy)
        self.assertTrue((self.fx.evidence / "RUN_ATTEMPT_1.json").is_file())
        self.assertFalse((self.fx.evidence / "COMPLETE.json").exists())

    def test_w08_execute_submits_exactly_once_copies_output_and_completes(self):
        self.dry()
        fake = FakeComfy(self.fx)
        fake.start()
        try:
            with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=["127.0.0.1"]):
                receipt = wrapper.run_execute(self.fx.manifest_path, self.fx.policy)
        finally:
            fake.close()
        self.assertEqual(fake.post_count, 1)
        self.assertGreaterEqual(fake.queue_get_count, 2)
        self.assertEqual(fake.last_prompt["prompt"], json.loads((self.fx.evidence / "materialized" / "EP01_SH12_R5.workflow.json").read_text()))
        self.assertEqual(receipt["transport"]["promptPostCount"], 1)
        self.assertEqual(Path(receipt["output"]["path"]).read_bytes(), b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2")
        self.assertTrue((self.fx.evidence / "COMPLETE.json").is_file())

    def test_w09_prompt_failure_is_never_retried_and_attempt_remains(self):
        self.dry()
        fake = FakeComfy(self.fx, fail_post=True)
        fake.start()
        try:
            with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=["127.0.0.1"]), self.assertRaises(ControlError):
                wrapper.run_execute(self.fx.manifest_path, self.fx.policy)
            self.assertEqual(fake.post_count, 1)
            with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=["127.0.0.1"]), self.assertRaises(ControlError):
                wrapper.run_execute(self.fx.manifest_path, self.fx.policy)
            self.assertEqual(fake.post_count, 1)
        finally:
            fake.close()
        self.assertTrue((self.fx.evidence / "RUN_ATTEMPT_1.json").exists())
        self.assertFalse((self.fx.evidence / "COMPLETE.json").exists())

    def test_w10_cli_is_closed_world(self):
        with self.assertRaises(SystemExit):
            wrapper._parse_args([str(self.fx.manifest_path)])
        with self.assertRaises(SystemExit):
            wrapper._parse_args([str(self.fx.manifest_path), "--dry-run", "--execute"])
        with self.assertRaises(SystemExit):
            wrapper._parse_args([str(self.fx.manifest_path), "--dry-run", "--batch"])

    def test_w11_strict_json_rejects_duplicate_keys_and_bool_as_integer(self):
        raw = self.fx.manifest_path.read_text()
        self.fx.manifest_path.write_text(raw.replace('"schemaVersion": 1,', '"schemaVersion": 1, "schemaVersion": 1,'))
        with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=[]), mock.patch.object(wrapper, "_gpu_compute_pids", return_value=[]), self.assertRaisesRegex(ControlError, "duplicate"):
            wrapper.run_dry_run(self.fx.manifest_path, self.fx.policy)

    def test_w12_variant_anchor_symlink_is_rejected(self):
        target = self.fx.new_anchor.with_name("real.png")
        self.fx.new_anchor.rename(target)
        self.fx.new_anchor.symlink_to(target)
        with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=[]), mock.patch.object(wrapper, "_gpu_compute_pids", return_value=[]), self.assertRaisesRegex(ControlError, "symlink"):
            wrapper.run_dry_run(self.fx.manifest_path, self.fx.policy)

    def test_w13_png_without_idat_is_rejected(self):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
        ihdr = struct.pack(">IIBBBBB", 704, 1280, 8, 2, 0, 0, 0)
        self.fx.new_anchor.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b""))
        with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=[]), mock.patch.object(wrapper, "_gpu_compute_pids", return_value=[]), self.assertRaisesRegex(ControlError, "incomplete"):
            wrapper.run_dry_run(self.fx.manifest_path, self.fx.policy)

    def test_w14_new_output_with_second_granularity_mtime_is_accepted(self):
        self.dry()
        fake = FakeComfy(self.fx, output_freshness="new_rounded")
        fake.start()
        try:
            with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=["127.0.0.1"]):
                receipt = wrapper.run_execute(self.fx.manifest_path, self.fx.policy)
        finally:
            fake.close()
        self.assertEqual(fake.post_count, 1)
        self.assertEqual(
            receipt["runtime"]["preSubmitOutputSnapshot"]["candidatePathCount"],
            0,
        )
        self.assertTrue((self.fx.evidence / "COMPLETE.json").exists())

    def test_w15_new_but_sixty_second_stale_output_is_rejected(self):
        self.dry()
        fake = FakeComfy(self.fx, output_freshness="new_stale")
        fake.start()
        try:
            with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=["127.0.0.1"]), self.assertRaisesRegex(ControlError, "older"):
                wrapper.run_execute(self.fx.manifest_path, self.fx.policy)
        finally:
            fake.close()
        self.assertEqual(fake.post_count, 1)
        self.assertFalse((self.fx.evidence / "COMPLETE.json").exists())

    def test_w16_recent_preexisting_output_path_is_rejected(self):
        self.dry()
        fake = FakeComfy(self.fx, output_freshness="preexisting_recent")
        fake.start()
        try:
            with mock.patch.object(wrapper, "_list_tcp_listeners", return_value=["127.0.0.1"]), self.assertRaisesRegex(ControlError, "existed before submission"):
                wrapper.run_execute(self.fx.manifest_path, self.fx.policy)
        finally:
            fake.close()
        self.assertEqual(fake.post_count, 1)
        self.assertFalse((self.fx.evidence / "COMPLETE.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
