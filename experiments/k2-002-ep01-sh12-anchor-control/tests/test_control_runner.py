from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_runner_core import (  # noqa: E402
    ANCHOR_DERIVED,
    ControlError,
    BaselineFacts,
    FIXED_BASELINE_SEED,
    RunCountLock,
    canonical_sha256,
    derived_anchor_seed,
    enforce_seed_policy,
    prepare_fixed_baseline_run,
    text_sha256,
    validate_allowed_diff,
)


OLD_ANCHOR = "21ef1ff9b874bf8be850702afd34acc1885bb22cd909b8587097b092eaea2827"
NEW_ANCHOR = "a" * 64
SHOTS_SHA = "1" * 64
WORKFLOW_FILE_SHA = "2" * 64
MODEL_SHA = {"UNET": "3" * 64, "TEXT_ENCODER": "4" * 64, "VAE": "5" * 64}


def fixture():
    workflow = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "device": "default", "type": "wan"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
        "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "frozen positive"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": "frozen negative"}},
        "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"batch_size": 1, "height": 1280, "length": 49, "start_image": ["12", 0], "vae": ["3", 0], "width": 704}},
        "8": {"class_type": "KSampler", "inputs": {"cfg": 5.0, "denoise": 1.0, "latent_image": ["7", 0], "model": ["4", 0], "negative": ["6", 0], "positive": ["5", 0], "sampler_name": "uni_pc", "scheduler": "simple", "seed": 596974677755723, "steps": 20}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "CreateVideo", "inputs": {"bit_depth": 8, "fps": 24, "images": ["9", 0]}},
        "11": {"class_type": "SaveVideo", "inputs": {"codec": "h264", "filename_prefix": "k2-002-ep01-i2v-v2/EP01_SH12-v2-technical-evidence", "format": "mp4", "video": ["10", 0]}},
        "12": {"class_type": "LoadImage", "inputs": {"image": f"k2-002-ep01-i2v-v2/{OLD_ANCHOR}.png"}},
    }
    facts = BaselineFacts(
        shots_sha256=SHOTS_SHA,
        workflow_file_sha256=WORKFLOW_FILE_SHA,
        workflow_canonical_sha256=canonical_sha256(workflow),
        anchor_sha256=OLD_ANCHOR,
        model_sha256=MODEL_SHA,
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
            "shotsSha256": SHOTS_SHA,
            "workflowFileSha256": WORKFLOW_FILE_SHA,
            "workflowCanonicalSha256": facts.workflow_canonical_sha256,
            "anchorSha256": OLD_ANCHOR,
            "seed": 596974677755723,
            "positivePromptSha256": text_sha256("frozen positive"),
            "negativePromptSha256": text_sha256("frozen negative"),
            "modelSha256": dict(MODEL_SHA),
        },
        "variant": {
            "anchorPath": "/isolated/evidence/inputs/new-anchor.png",
            "anchorSha256": NEW_ANCHOR,
            "seedPolicy": "FIXED_BASELINE_SEED",
            "seed": 596974677755723,
        },
        "allowedWorkflowDiffPointers": ["/12/inputs/image"],
    }
    environ = {
        "K2_EP01_I2V_ACK": "TECHNICAL_EVIDENCE_ONLY",
        "K2_EP01_EXPERIMENT_ACK": "ANCHOR_ONLY_FIXED_BASELINE_SEED",
    }
    return manifest, workflow, facts, environ


def prepare(manifest, workflow, facts, environ):
    return prepare_fixed_baseline_run(
        manifest=manifest,
        baseline_workflow=workflow,
        facts=facts,
        environ=environ,
    )


class ExactSixteenTestMatrix(unittest.TestCase):
    def test_01_default_anchor_derived_behavior_is_unchanged(self):
        seed = derived_anchor_seed(NEW_ANCHOR)
        enforce_seed_policy(policy=ANCHOR_DERIVED, anchor_sha256=NEW_ANCHOR, seed=seed)
        with self.assertRaises(ControlError):
            enforce_seed_policy(
                policy=ANCHOR_DERIVED,
                anchor_sha256=NEW_ANCHOR,
                seed=596974677755723,
            )

    def test_02_fixed_seed_without_experiment_ack_is_rejected(self):
        m, w, f, e = fixture()
        e.pop("K2_EP01_EXPERIMENT_ACK")
        with self.assertRaisesRegex(ControlError, "experiment ACK"):
            prepare(m, w, f, e)

    def test_03_wrong_authority_state_is_rejected(self):
        m, w, f, e = fixture()
        m["authorityState"] = "PRODUCTION"
        with self.assertRaisesRegex(ControlError, "authorityState"):
            prepare(m, w, f, e)

    def test_04_publication_allowed_true_is_rejected(self):
        m, w, f, e = fixture()
        m["publicationAllowed"] = True
        with self.assertRaisesRegex(ControlError, "publicationAllowed"):
            prepare(m, w, f, e)

    def test_05_nonzero_canonical_mutations_is_rejected(self):
        m, w, f, e = fixture()
        m["canonicalMutations"] = 1
        with self.assertRaisesRegex(ControlError, "canonicalMutations"):
            prepare(m, w, f, e)

    def test_06_non_sh12_shot_is_rejected(self):
        m, w, f, e = fixture()
        m["shotId"] = "EP01_SH11"
        with self.assertRaisesRegex(ControlError, "EP01_SH12"):
            prepare(m, w, f, e)

    def test_07_max_runs_greater_than_one_is_rejected(self):
        m, w, f, e = fixture()
        m["maxRuns"] = 2
        with self.assertRaisesRegex(ControlError, "maxRuns"):
            prepare(m, w, f, e)

    def test_08_positive_prompt_change_is_rejected(self):
        m, w, f, e = fixture()
        w["5"]["inputs"]["text"] = "changed positive"
        f = BaselineFacts(f.shots_sha256, f.workflow_file_sha256, canonical_sha256(w), f.anchor_sha256, f.model_sha256)
        m["baseline"]["workflowCanonicalSha256"] = f.workflow_canonical_sha256
        with self.assertRaisesRegex(ControlError, "positive prompt"):
            prepare(m, w, f, e)

    def test_09_negative_prompt_change_is_rejected(self):
        m, w, f, e = fixture()
        w["6"]["inputs"]["text"] = "changed negative"
        f = BaselineFacts(f.shots_sha256, f.workflow_file_sha256, canonical_sha256(w), f.anchor_sha256, f.model_sha256)
        m["baseline"]["workflowCanonicalSha256"] = f.workflow_canonical_sha256
        with self.assertRaisesRegex(ControlError, "negative prompt"):
            prepare(m, w, f, e)

    def test_10_each_ksampler_parameter_change_is_rejected(self):
        mutations = {
            "seed": 1,
            "steps": 21,
            "cfg": 6.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 0.9,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                m, w, f, e = fixture()
                w["8"]["inputs"][field] = value
                f = BaselineFacts(f.shots_sha256, f.workflow_file_sha256, canonical_sha256(w), f.anchor_sha256, f.model_sha256)
                m["baseline"]["workflowCanonicalSha256"] = f.workflow_canonical_sha256
                with self.assertRaisesRegex(ControlError, f"KSampler {field}"):
                    prepare(m, w, f, e)

    def test_11_model_sampling_shift_change_is_rejected(self):
        m, w, f, e = fixture()
        w["4"]["inputs"]["shift"] = 7.0
        f = BaselineFacts(f.shots_sha256, f.workflow_file_sha256, canonical_sha256(w), f.anchor_sha256, f.model_sha256)
        m["baseline"]["workflowCanonicalSha256"] = f.workflow_canonical_sha256
        with self.assertRaisesRegex(ControlError, "shift"):
            prepare(m, w, f, e)

    def test_12_model_digest_change_is_rejected(self):
        m, w, f, e = fixture()
        f = BaselineFacts(f.shots_sha256, f.workflow_file_sha256, f.workflow_canonical_sha256, f.anchor_sha256, {**f.model_sha256, "UNET": "f" * 64})
        with self.assertRaisesRegex(ControlError, "UNET model SHA-256"):
            prepare(m, w, f, e)

    def test_13_non_anchor_workflow_diff_is_rejected(self):
        m, w, f, e = fixture()
        variant, _ = prepare(m, w, f, e)
        variant["11"]["inputs"]["filename_prefix"] = "changed"
        with self.assertRaisesRegex(ControlError, "not anchor-only"):
            validate_allowed_diff(w, variant)

    def test_14_same_anchor_digest_is_rejected(self):
        m, w, f, e = fixture()
        m["variant"]["anchorSha256"] = OLD_ANCHOR
        with self.assertRaisesRegex(ControlError, "must differ"):
            prepare(m, w, f, e)

    def test_15_legal_anchor_fixed_seed_dry_run_passes_with_zero_gpu_calls(self):
        m, w, f, e = fixture()
        variant, receipt = prepare(m, w, f, e)
        self.assertEqual(receipt["gpuOrProviderCalls"], 0)
        self.assertEqual(receipt["workflowDiff"], ["/12/inputs/image"])
        self.assertEqual(receipt["anchorOnlyControl"], "PASS")
        self.assertEqual(variant["8"]["inputs"], w["8"]["inputs"])

    def test_16_second_run_is_rejected_after_first_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            lock = RunCountLock(Path(temporary))
            lock.reserve()
            with self.assertRaises(ControlError):
                RunCountLock(Path(temporary)).reserve()
            lock.complete({"videoSha256": "6" * 64})
            with self.assertRaises(ControlError):
                RunCountLock(Path(temporary)).reserve()


if __name__ == "__main__":
    unittest.main(verbosity=2)
