from dataclasses import replace
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
from threading import Thread
import unittest

from services.v4_platform import (
    COMFYUI_ADAPTER_ID,
    ComfyUIConfigurationError,
    ComfyUIWan22Config,
    ComfyUIWan22VideoAdapter,
    InMemoryMediaJobAdapter,
    MediaJobCoordinator,
    MediaJobError,
    build_comfyui_runtime_attestation,
    create_comfyui_wan22_adapter_from_environment,
)
from services.v5_core_os.episode_production import (
    create_local_development_boundary_from_environment,
)


UNET = "wan2.2_ti2v_5B_fp16.safetensors"
UNET_SHA = "456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e"
CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
CLIP_SHA = "c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68"
VAE = "wan2.2_vae.safetensors"
VAE_SHA = "e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156"


def digest(value):
    return sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def live_request():
    value = {
        "schemaVersion": "v5.provider-experiment-request.v1",
        "workspaceRef": "workspace-k2",
        "productionRunRef": "production-run-k2",
        "generationRequestRef": "generation-request-live-video-1",
        "generationRequestVersionRef": "generation-request-live-video-1-v1",
        "version": 1,
        "ordinal": 1,
        "assetRequirementRef": "asset-requirement-live-video-1",
        "creativeShotRef": "creative-shot-k2-1",
        "creativeShotVersionRef": "creative-shot-k2-1-v1",
        "mediaKind": "video",
        "mediaType": "video/mp4",
        "adapterCapability": "comfyui-wan22-ti2v-v1",
        "providerSelection": {
            "providerId": "self-hosted-comfyui",
            "modelId": "wan2.2-ti2v-5b-fp16",
            "region": "test-a100-region",
            "endpointClass": "ssh-loopback-tunnel",
            "providerCapabilityRef": "provider-capability-wan22-v1",
            "providerExecutionPolicyRef": "provider-policy-k2-v1",
            "providerExecutionPolicyDigest": "1" * 64,
            "rightsManifestRef": "rights-manifest-k2-v1",
            "rightsManifestDigest": "2" * 64,
            "productionPolicyRef": "production-policy-k2-v1",
            "productionPolicyDigest": "3" * 64,
            "credentialSourceRef": "credential-source-test-runtime-v1",
            "usageTermsRef": "usage-terms-wan22-v1",
            "budgetAuthorityRef": "budget-authority-k2-v1",
            "runtimeAttestationRef": "runtime-attestation-test-a100-v1",
            "runtimeAttestationDigest": "4" * 64,
            "costCurrency": "CNY",
            "maxCostMinor": 100,
            "timeoutSeconds": 1800,
        },
        "parameters": {
            "durationFrames": 5,
            "frameRate": 4,
            "width": 64,
            "height": 64,
            "prompt": "A rights-cleared cinematic test subject walks through rain.",
            "negativePrompt": "text, watermark, malformed anatomy",
            "seed": 20260818,
            "steps": 20,
            "cfg": 5.0,
            "samplerName": "uni_pc",
            "scheduler": "simple",
            "modelShift": 8.0,
        },
        "state": "READY_FOR_DISPATCH",
        "requestedProvenance": "LIVE_PROVIDER",
        "publicationAllowed": False,
    }
    value["payloadDigest"] = digest(value)
    return value


def internal_request():
    value = live_request()
    value["schemaVersion"] = (
        "v5.k2-internal-self-hosted-experiment-request.v1"
    )
    value["providerSelection"] = {
        "executionMode": "INTERNAL_SELF_HOSTED",
        "executionGrantRef": "k2-internal-execution-grant-test",
        "executionGrantDigest": "6" * 64,
        "providerId": "self-hosted-comfyui",
        "modelId": "wan2.2-ti2v-5b-fp16",
        "region": "test-a100-region",
        "endpointClass": "ssh-loopback-tunnel",
        "runtimeAttestationRef": "runtime-attestation-test-a100-v1",
        "runtimeAttestationDigest": "4" * 64,
        "costCurrency": "CNY",
        "maxCostMinor": 100,
        "timeoutSeconds": 1800,
    }
    unsigned = {
        key: item for key, item in value.items() if key != "payloadDigest"
    }
    value["payloadDigest"] = digest(unsigned)
    return value


class FakeComfyUIHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        del args

    def _json(self, status, value):
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/prompt":
            self._json(404, {})
            return
        length = int(self.headers.get("Content-Length", "0"))
        self.server.last_prompt = json.loads(self.rfile.read(length))
        self._json(200, {"prompt_id": "prompt-live-1", "number": 1})

    def do_GET(self):
        if self.path == "/system_stats":
            self._json(
                200,
                {
                    "system": {
                        "comfyui_version": "0.28.0",
                        "python_version": "3.12.7",
                        "pytorch_version": "2.13.0+cu126",
                    },
                    "devices": [
                        {
                            "name": "cuda:0 NVIDIA A100-PCIE-40GB : cudaMallocAsync",
                            "type": "cuda",
                            "vram_total": 42405855232,
                        }
                    ],
                },
            )
            return
        if self.path == "/object_info":
            def node(*fields, optional=()):
                return {
                    "input": {
                        "required": {field: ["VALUE"] for field in fields},
                        "optional": {field: ["VALUE"] for field in optional},
                    }
                }

            object_info = {
                "UNETLoader": node("unet_name", "weight_dtype"),
                "CLIPLoader": node("clip_name", "type", optional=("device",)),
                "VAELoader": node("vae_name"),
                "ModelSamplingSD3": node("model", "shift"),
                "CLIPTextEncode": node("text", "clip"),
                "Wan22ImageToVideoLatent": node(
                    "vae", "width", "height", "length", "batch_size"
                ),
                "KSampler": node(
                    "model", "seed", "steps", "cfg", "sampler_name",
                    "scheduler", "positive", "negative", "latent_image", "denoise",
                ),
                "VAEDecode": node("samples", "vae"),
                "CreateVideo": node("images", "fps", optional=("bit_depth",)),
                "SaveVideo": node("video", "filename_prefix", "format", "codec"),
            }
            def required(node_name):
                return object_info[node_name]["input"]["required"]
            required("UNETLoader")["unet_name"] = [[UNET]]
            required("UNETLoader")["weight_dtype"] = [["default"]]
            required("CLIPLoader")["clip_name"] = [[CLIP]]
            required("CLIPLoader")["type"] = [["wan"]]
            required("VAELoader")["vae_name"] = [[VAE]]
            required("KSampler")["sampler_name"] = [["uni_pc", "uni_pc_bh2"]]
            required("KSampler")["scheduler"] = [["simple"]]
            required("SaveVideo")["format"] = [
                "COMBO", {"options": ["auto", "mp4"]}
            ]
            required("SaveVideo")["codec"] = [
                "COMBO", {"options": ["auto", "h264"]}
            ]
            if self.server.omit_unet:
                required("UNETLoader")["unet_name"] = [[]]
            self._json(200, object_info)
            return
        if self.path == "/history/prompt-live-1":
            prefix = self.server.last_prompt["prompt"]["11"]["inputs"][
                "filename_prefix"
            ].split("/")[-1]
            self._json(
                200,
                {
                    "prompt-live-1": {
                        "outputs": {
                            "11": {
                                "videos": [
                                    {
                                        "filename": f"{prefix}_00001.mp4",
                                        "subfolder": "acs-k2",
                                        "type": "output",
                                    }
                                ]
                            }
                        },
                        "status": {"completed": True, "messages": []},
                    }
                },
            )
            return
        if self.path.startswith("/view?"):
            body = self.server.video_bytes
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(404, {})


def create_video(path):
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
            "color=c=0x102030:s=64x64:r=4:d=1.25",
            "-frames:v", "5", "-an", "-c:v", "libx264", "-pix_fmt",
            "yuv420p", "-y", str(path),
        ],
        check=True,
        capture_output=True,
    )


class V4ComfyUIWan22AdapterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        video = Path(self.directory.name) / "provider.mp4"
        create_video(video)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeComfyUIHandler)
        self.server.video_bytes = video.read_bytes()
        self.server.last_prompt = None
        self.server.omit_unet = False
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.directory.cleanup()

    def config(self):
        return ComfyUIWan22Config(
            base_url=f"http://127.0.0.1:{self.server.server_port}",
            provider_id="self-hosted-comfyui",
            model_id="wan2.2-ti2v-5b-fp16",
            region="test-a100-region",
            endpoint_class="ssh-loopback-tunnel",
            unet_name=UNET,
            unet_sha256=UNET_SHA,
            clip_name=CLIP,
            clip_sha256=CLIP_SHA,
            vae_name=VAE,
            vae_sha256=VAE_SHA,
            runtime_attestation_ref="runtime-attestation-test-a100-v1",
            runtime_attestation_digest="4" * 64,
            cost_currency="CNY",
            cost_minor_per_attempt=100,
            poll_interval_seconds=0.001,
        )

    def test_executes_through_existing_job_contract_and_records_safe_gpu_facts(self):
        adapter = ComfyUIWan22VideoAdapter(self.config())
        request = live_request()
        artifacts = Path(self.directory.name) / "artifacts"
        queue = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            adapter,
            artifacts,
            ref_factory=lambda prefix: f"{prefix}-test",
            clock=lambda: "2026-08-18T00:00:00Z",
            max_attempts=1,
        )

        jobs = queue.execute_batch(
            request["workspaceRef"],
            request["productionRunRef"],
            [request],
            batch_idempotency_key="live-wan22-one",
        )

        job = jobs[0]
        self.assertEqual(job["state"], "SUCCEEDED")
        self.assertEqual(job["artifact"]["adapterIdentity"], COMFYUI_ADAPTER_ID)
        self.assertEqual(job["artifact"]["provenance"], "LIVE_PROVIDER")
        self.assertTrue(job["artifact"]["gpuUsed"])
        execution = job["artifact"]["providerExecution"]
        self.assertEqual(execution["providerRequestRef"], "prompt-live-1")
        self.assertIn("A100-PCIE-40GB", execution["executionDevice"])
        self.assertEqual(execution["runtimeFacts"]["modelFiles"][0]["sha256"], UNET_SHA)
        self.assertEqual(job["artifact"]["probe"]["streams"][0]["nb_read_frames"], "5")
        serialized = json.dumps(job, ensure_ascii=False)
        self.assertNotIn(self.config().base_url, serialized)
        self.assertNotIn("credential-source-test-runtime-v1", json.dumps(execution))
        workflow = self.server.last_prompt["prompt"]
        self.assertEqual(workflow["1"]["inputs"]["unet_name"], UNET)
        self.assertEqual(workflow["7"]["inputs"]["length"], 5)
        self.assertEqual(workflow["8"]["inputs"]["seed"], 20260818)

    def test_internal_self_hosted_request_uses_same_v4_job_without_external_authorities(self):
        request = internal_request()
        queue = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            ComfyUIWan22VideoAdapter(self.config()),
            Path(self.directory.name) / "internal-artifacts",
            ref_factory=lambda prefix: f"{prefix}-internal-test",
            clock=lambda: "2026-08-18T00:00:00Z",
            max_attempts=1,
        )

        jobs = queue.execute_batch(
            request["workspaceRef"],
            request["productionRunRef"],
            [request],
            batch_idempotency_key="internal-wan22-one",
        )

        self.assertEqual(jobs[0]["state"], "SUCCEEDED")
        self.assertTrue(jobs[0]["artifact"]["gpuUsed"])
        serialized = json.dumps(jobs[0], ensure_ascii=False)
        for forbidden in (
            "rightsManifestRef",
            "providerExecutionPolicyRef",
            "providerCapabilityRef",
            "credentialSourceRef",
            "usageTermsRef",
            "budgetAuthorityRef",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_capability_probe_fails_closed_when_model_is_not_recognized(self):
        self.server.omit_unet = True
        adapter = ComfyUIWan22VideoAdapter(self.config())
        with self.assertRaises(ComfyUIConfigurationError):
            adapter.probe_capability()

    def test_configured_attempt_cost_over_policy_cap_blocks_before_submission(self):
        queue = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            ComfyUIWan22VideoAdapter(
                replace(self.config(), cost_minor_per_attempt=101)
            ),
            Path(self.directory.name) / "artifacts",
            ref_factory=lambda prefix: f"{prefix}-test",
            clock=lambda: "2026-08-18T00:00:00Z",
            max_attempts=1,
        )

        with self.assertRaises(MediaJobError):
            queue.execute_batch(
                "workspace-k2",
                "production-run-k2",
                [live_request()],
                batch_idempotency_key="cost-cap-before-provider-call",
            )
        self.assertIsNone(self.server.last_prompt)

    def test_insecure_remote_endpoint_and_incomplete_environment_are_rejected(self):
        with self.assertRaises(ComfyUIConfigurationError):
            ComfyUIWan22Config(
                base_url="http://gpu.example.invalid:8188",
                provider_id="provider", model_id="model", region="region",
                endpoint_class="remote", unet_name=UNET, unet_sha256=UNET_SHA,
                clip_name=CLIP, clip_sha256=CLIP_SHA, vae_name=VAE,
                vae_sha256=VAE_SHA, runtime_attestation_ref="attestation-ref",
                runtime_attestation_digest="4" * 64, cost_currency="CNY",
                cost_minor_per_attempt=1,
            )
        with self.assertRaises(ComfyUIConfigurationError):
            create_comfyui_wan22_adapter_from_environment({})

    def test_partial_comfyui_environment_fails_core_composition_closed(self):
        with self.assertRaises(ComfyUIConfigurationError):
            create_local_development_boundary_from_environment(
                project_boundary=object(),
                series_episode_boundary=object(),
                series_planning_boundary=object(),
                script_studio_boundary=object(),
                environ={
                    "CREATOR_EPISODE_PRODUCTION_DATA_PATH": str(
                        Path(self.directory.name) / "episode.sqlite3"
                    ),
                    "COMFYUI_MODEL_ID": "partial-configuration-must-not-be-ignored",
                },
            )

    def test_live_request_without_exact_policy_authority_is_rejected_before_dispatch(self):
        request = live_request()
        request["providerSelection"].pop("rightsManifestRef")
        unsigned = {key: value for key, value in request.items() if key != "payloadDigest"}
        request["payloadDigest"] = digest(unsigned)
        queue = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            ComfyUIWan22VideoAdapter(self.config()),
            Path(self.directory.name) / "artifacts",
            ref_factory=lambda prefix: f"{prefix}-test",
            clock=lambda: "2026-08-18T00:00:00Z",
        )
        with self.assertRaises(MediaJobError):
            queue.dispatch(request, idempotency_key="invalid-live-policy")

    def test_runtime_attestation_mismatch_blocks_before_provider_submission(self):
        request = live_request()
        request["providerSelection"]["runtimeAttestationDigest"] = "9" * 64
        unsigned = {
            key: value for key, value in request.items() if key != "payloadDigest"
        }
        request["payloadDigest"] = digest(unsigned)
        queue = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            ComfyUIWan22VideoAdapter(self.config()),
            Path(self.directory.name) / "artifacts",
            ref_factory=lambda prefix: f"{prefix}-test",
            clock=lambda: "2026-08-18T00:00:00Z",
            max_attempts=1,
        )

        with self.assertRaises(MediaJobError):
            queue.execute_batch(
                "workspace-k2",
                "production-run-k2",
                [request],
                batch_idempotency_key="mismatched-runtime-attestation",
            )
        self.assertIsNone(self.server.last_prompt)

    def test_runtime_attestation_hashes_real_model_files_and_discloses_no_paths(self):
        model_root = Path(self.directory.name) / "models"
        model_files = (
            ("diffusion_models", UNET, b"verified-unet"),
            ("text_encoders", CLIP, b"verified-clip"),
            ("vae", VAE, b"verified-vae"),
        )
        digests = []
        for directory, name, content in model_files:
            path = model_root / directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            digests.append(sha256(content).hexdigest())
        config = replace(
            self.config(),
            unet_sha256=digests[0],
            clip_sha256=digests[1],
            vae_sha256=digests[2],
            runtime_attestation_digest="0" * 64,
        )

        attestation = build_comfyui_runtime_attestation(
            config,
            model_root,
            observed_at="2026-08-18T00:00:00Z",
        )

        self.assertEqual(
            attestation["facts"]["modelDigestVerification"],
            "LOCAL_FILE_SHA256_VERIFIED",
        )
        self.assertEqual(attestation["facts"]["modelFiles"][0]["sha256"], digests[0])
        self.assertEqual(attestation["authorityState"], "TECHNICAL_EVIDENCE_ONLY")
        self.assertFalse(attestation["publicationAllowed"])
        unsigned = dict(attestation)
        embedded = unsigned.pop("payloadDigest")
        self.assertEqual(embedded, digest(unsigned))
        serialized = json.dumps(attestation)
        self.assertNotIn(str(model_root), serialized)
        self.assertNotIn(config.base_url, serialized)

        (model_root / "vae" / VAE).write_bytes(b"tampered")
        with self.assertRaises(ComfyUIConfigurationError):
            build_comfyui_runtime_attestation(
                config,
                model_root,
                observed_at="2026-08-18T00:00:00Z",
            )

    def test_model_filename_cannot_escape_model_root(self):
        with self.assertRaises(ComfyUIConfigurationError):
            replace(self.config(), unet_name="../outside.safetensors")


if __name__ == "__main__":
    unittest.main()
