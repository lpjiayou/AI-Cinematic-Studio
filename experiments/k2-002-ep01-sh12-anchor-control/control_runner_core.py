"""Pure, fail-closed core for the proposed SH12 R5 anchor-only control runner.

This is a local design prototype.  It deliberately performs no ComfyUI or GPU
operation.  The production wrapper must finish every check in
``prepare_fixed_baseline_run`` before it stages an image or sends ``/prompt``.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping


AUTHORITY_STATE = "TECHNICAL_EVIDENCE_ONLY"
EXPERIMENT_ACK = "ANCHOR_ONLY_FIXED_BASELINE_SEED"
EXPERIMENT_ID = "K2-002-EP01-SH12-R5-ANCHOR-ONLY"
SHOT_ID = "EP01_SH12"
CHANGED_VARIABLE = "START_ANCHOR_ONLY"
ANCHOR_DERIVED = "ANCHOR_DERIVED"
FIXED_BASELINE_SEED = "FIXED_BASELINE_SEED"
ALLOWED_DIFF = ("/12/inputs/image",)

EXPECTED_KSAMPLER = {
    "seed": 596974677755723,
    "steps": 20,
    "cfg": 5.0,
    "sampler_name": "uni_pc",
    "scheduler": "simple",
    "denoise": 1.0,
}
EXPECTED_SHIFT = 8.0
EXPECTED_LATENT = {"width": 704, "height": 1280, "length": 49, "batch_size": 1}
EXPECTED_FPS = 24
EXPECTED_MODEL_LOADERS = {
    "UNET": ("1", "unet_name", "wan2.2_ti2v_5B_fp16.safetensors"),
    "TEXT_ENCODER": (
        "2",
        "clip_name",
        "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    ),
    "VAE": ("3", "vae_name", "wan2.2_vae.safetensors"),
}


class ControlError(RuntimeError):
    """A pre-submit control invariant failed."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def text_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def derived_anchor_seed(anchor_sha256: str) -> int:
    _require_digest(anchor_sha256, "anchor SHA-256")
    return int(anchor_sha256[:13], 16)


def enforce_seed_policy(
    *,
    policy: str = ANCHOR_DERIVED,
    anchor_sha256: str,
    seed: int,
    baseline_seed: int | None = None,
) -> None:
    """Keep the default contract strict; fixed seed is a separate branch."""
    if policy == ANCHOR_DERIVED:
        if type(seed) is not int or seed != derived_anchor_seed(anchor_sha256):
            raise ControlError("ANCHOR_DERIVED requires seed=int(anchor_sha256[:13],16)")
        return
    if policy == FIXED_BASELINE_SEED:
        if type(baseline_seed) is not int or type(seed) is not int:
            raise ControlError("FIXED_BASELINE_SEED requires integer baseline and variant seeds")
        if seed != baseline_seed:
            raise ControlError("FIXED_BASELINE_SEED requires variant seed == baseline seed")
        return
    raise ControlError("unknown seed policy")


def _require_digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.lower() != value
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ControlError(f"{label} is not a lowercase SHA-256")
    return value


def _require_exact_int(value: Any, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        raise ControlError(f"{label} must be integer {expected}")


def _node_inputs(workflow: Mapping[str, Any], node_id: str) -> Mapping[str, Any]:
    node = workflow.get(node_id)
    inputs = node.get("inputs") if isinstance(node, Mapping) else None
    if not isinstance(inputs, Mapping):
        raise ControlError(f"workflow node {node_id} inputs are unavailable")
    return inputs


def _escape_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def json_pointer_diff(before: Any, after: Any, pointer: str = "") -> list[str]:
    """Return leaf/key JSON Pointer differences in deterministic order."""
    if type(before) is not type(after):
        return [pointer or "/"]
    if isinstance(before, Mapping):
        paths: list[str] = []
        keys = sorted(set(before) | set(after), key=str)
        for key in keys:
            child = f"{pointer}/{_escape_pointer_token(str(key))}"
            if key not in before or key not in after:
                paths.append(child)
            else:
                paths.extend(json_pointer_diff(before[key], after[key], child))
        return paths
    if isinstance(before, list):
        paths = []
        maximum = max(len(before), len(after))
        for index in range(maximum):
            child = f"{pointer}/{index}"
            if index >= len(before) or index >= len(after):
                paths.append(child)
            else:
                paths.extend(json_pointer_diff(before[index], after[index], child))
        return paths
    return [] if before == after else [pointer or "/"]


def validate_allowed_diff(
    baseline_workflow: Mapping[str, Any], variant_workflow: Mapping[str, Any]
) -> list[str]:
    changed = json_pointer_diff(baseline_workflow, variant_workflow)
    if changed != list(ALLOWED_DIFF):
        raise ControlError(f"workflow diff is not anchor-only: {changed}")
    return changed


@dataclass(frozen=True)
class BaselineFacts:
    shots_sha256: str
    workflow_file_sha256: str
    workflow_canonical_sha256: str
    anchor_sha256: str
    model_sha256: Mapping[str, str]


def _validate_manifest_boundary(manifest: Mapping[str, Any], environ: Mapping[str, str]) -> None:
    if environ.get("K2_EP01_I2V_ACK") != AUTHORITY_STATE:
        raise ControlError("technical-evidence ACK is missing")
    if environ.get("K2_EP01_EXPERIMENT_ACK") != EXPERIMENT_ACK:
        raise ControlError("anchor-only fixed-seed experiment ACK is missing")
    _require_exact_int(manifest.get("schemaVersion"), 1, "schemaVersion")
    if manifest.get("experimentId") != EXPERIMENT_ID:
        raise ControlError("experimentId changed")
    if manifest.get("authorityState") != AUTHORITY_STATE:
        raise ControlError("authorityState is not TECHNICAL_EVIDENCE_ONLY")
    if manifest.get("publicationAllowed") is not False:
        raise ControlError("publicationAllowed must be false")
    _require_exact_int(manifest.get("canonicalMutations"), 0, "canonicalMutations")
    if manifest.get("shotId") != SHOT_ID:
        raise ControlError("controlled runner only permits EP01_SH12")
    if manifest.get("changedVariable") != CHANGED_VARIABLE:
        raise ControlError("changedVariable must be START_ANCHOR_ONLY")
    _require_exact_int(manifest.get("maxRuns"), 1, "maxRuns")
    if manifest.get("allowedWorkflowDiffPointers") != list(ALLOWED_DIFF):
        raise ControlError("allowedWorkflowDiffPointers changed")


def _validate_baseline(
    manifest: Mapping[str, Any],
    workflow: Mapping[str, Any],
    facts: BaselineFacts,
) -> None:
    baseline = manifest.get("baseline")
    if not isinstance(baseline, Mapping):
        raise ControlError("baseline manifest object is missing")
    pinned = {
        "shotsSha256": facts.shots_sha256,
        "workflowFileSha256": facts.workflow_file_sha256,
        "workflowCanonicalSha256": facts.workflow_canonical_sha256,
        "anchorSha256": facts.anchor_sha256,
    }
    for field, actual in pinned.items():
        _require_digest(actual, f"observed {field}")
        if baseline.get(field) != actual:
            raise ControlError(f"baseline {field} no longer matches the observed file")
    if canonical_sha256(workflow) != facts.workflow_canonical_sha256:
        raise ControlError("baseline workflow canonical SHA-256 changed")

    _require_exact_int(baseline.get("seed"), EXPECTED_KSAMPLER["seed"], "baseline seed")
    ks = _node_inputs(workflow, "8")
    for field, expected in EXPECTED_KSAMPLER.items():
        if type(ks.get(field)) is not type(expected) or ks.get(field) != expected:
            raise ControlError(f"KSampler {field} changed")
    sampling = _node_inputs(workflow, "4")
    if type(sampling.get("shift")) is not float or sampling.get("shift") != EXPECTED_SHIFT:
        raise ControlError("ModelSamplingSD3 shift changed")
    latent = _node_inputs(workflow, "7")
    for field, expected in EXPECTED_LATENT.items():
        if type(latent.get(field)) is not int or latent.get(field) != expected:
            raise ControlError(f"I2V latent {field} changed")
    if (
        type(_node_inputs(workflow, "10").get("fps")) is not int
        or _node_inputs(workflow, "10").get("fps") != EXPECTED_FPS
    ):
        raise ControlError("video fps changed")

    positive = _node_inputs(workflow, "5").get("text")
    negative = _node_inputs(workflow, "6").get("text")
    if not isinstance(positive, str) or text_sha256(positive) != baseline.get(
        "positivePromptSha256"
    ):
        raise ControlError("positive prompt changed")
    if not isinstance(negative, str) or text_sha256(negative) != baseline.get(
        "negativePromptSha256"
    ):
        raise ControlError("negative prompt changed")

    baseline_models = baseline.get("modelSha256")
    if not isinstance(baseline_models, Mapping):
        raise ControlError("baseline model digests are missing")
    if set(baseline_models) != set(EXPECTED_MODEL_LOADERS):
        raise ControlError("baseline model roles changed")
    if set(facts.model_sha256) != set(EXPECTED_MODEL_LOADERS):
        raise ControlError("observed model roles changed")
    for role, (node_id, field, filename) in EXPECTED_MODEL_LOADERS.items():
        expected_digest = _require_digest(baseline_models.get(role), f"baseline {role}")
        actual_digest = _require_digest(facts.model_sha256.get(role), f"observed {role}")
        if actual_digest != expected_digest:
            raise ControlError(f"{role} model SHA-256 changed")
        if _node_inputs(workflow, node_id).get(field) != filename:
            raise ControlError(f"{role} model path changed")

    baseline_image = _node_inputs(workflow, "12").get("image")
    if not isinstance(baseline_image, str) or not baseline_image.endswith(
        f"/{facts.anchor_sha256}.png"
    ):
        raise ControlError("baseline workflow anchor binding changed")


def prepare_fixed_baseline_run(
    *,
    manifest: Mapping[str, Any],
    baseline_workflow: Mapping[str, Any],
    facts: BaselineFacts,
    environ: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate every invariant and build, but do not submit, the R5 workflow."""
    _validate_manifest_boundary(manifest, environ)
    _validate_baseline(manifest, baseline_workflow, facts)
    baseline = manifest["baseline"]
    variant = manifest.get("variant")
    if not isinstance(variant, Mapping):
        raise ControlError("variant manifest object is missing")
    if variant.get("seedPolicy") != FIXED_BASELINE_SEED:
        raise ControlError("variant seed policy must be FIXED_BASELINE_SEED")
    anchor_path = variant.get("anchorPath")
    if not isinstance(anchor_path, str) or not anchor_path.strip():
        raise ControlError("variant anchorPath is missing")
    variant_anchor = _require_digest(variant.get("anchorSha256"), "variant anchor SHA-256")
    if variant_anchor == facts.anchor_sha256:
        raise ControlError("variant anchor must differ from baseline anchor")
    enforce_seed_policy(
        policy=FIXED_BASELINE_SEED,
        anchor_sha256=variant_anchor,
        seed=variant.get("seed"),
        baseline_seed=baseline.get("seed"),
    )

    result = deepcopy(baseline_workflow)
    staged_image = f"k2-002-ep01-i2v-r5-anchor-only/{variant_anchor}.png"
    result["12"]["inputs"]["image"] = staged_image
    changed = validate_allowed_diff(baseline_workflow, result)
    receipt = {
        "experimentId": EXPERIMENT_ID,
        "seedPolicy": FIXED_BASELINE_SEED,
        "changedVariable": CHANGED_VARIABLE,
        "baselineSeed": baseline["seed"],
        "variantSeed": variant["seed"],
        "baselineAnchorSha256": facts.anchor_sha256,
        "variantAnchorSha256": variant_anchor,
        "baselineWorkflowCanonicalSha256": facts.workflow_canonical_sha256,
        "variantWorkflowCanonicalSha256": canonical_sha256(result),
        "workflowDiff": changed,
        "workflowDiffAllowed": True,
        "anchorOnlyControl": "PASS",
        "gpuOrProviderCalls": 0,
    }
    return result, receipt


class RunCountLock:
    """Atomic, fail-closed one-attempt lock; dry-runs never instantiate it."""

    def __init__(self, evidence_root: Path) -> None:
        self.root = Path(os.path.abspath(os.fspath(evidence_root)))
        self.lock_path = self.root / "RUN_ATTEMPT_1.json"
        self.complete_path = self.root / "COMPLETE.json"

    def _open_root(self) -> int:
        try:
            info = self.root.lstat()
        except FileNotFoundError as exc:
            raise ControlError("evidence root does not exist") from exc
        if self.root.is_symlink() or not self.root.is_dir():
            raise ControlError("evidence root must be a real directory")
        if info.st_mode & 0o022:
            raise ControlError("evidence root is group/world writable")
        descriptor = os.open(
            self.root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            os.close(descriptor)
            raise ControlError("evidence root changed while it was opened")
        return descriptor

    @staticmethod
    def _fsync_root(descriptor: int) -> None:
        os.fsync(descriptor)

    def reserve(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.path.lexists(self.complete_path):
            raise ControlError("valid COMPLETE receipt already exists")
        payload = canonical_bytes(
            {
                "experimentId": EXPERIMENT_ID,
                "runNumber": 1,
                "state": "RESERVED_BEFORE_COMFYUI_SUBMIT",
                "reservedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        ) + b"\n"
        root_descriptor = self._open_root()
        try:
            try:
                descriptor = os.open(
                    self.lock_path.name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=root_descriptor,
                )
            except FileExistsError as exc:
                raise ControlError("maxRuns=1 lock already consumed") from exc
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._fsync_root(root_descriptor)
        finally:
            os.close(root_descriptor)

    def complete(self, receipt: Mapping[str, Any]) -> None:
        if not self.lock_path.is_file():
            raise ControlError("run attempt was not reserved")
        payload = canonical_bytes(
            {
                "experimentId": EXPERIMENT_ID,
                "runNumber": 1,
                "state": "COMPLETE",
                "receipt": dict(receipt),
            }
        ) + b"\n"
        root_descriptor = self._open_root()
        try:
            try:
                descriptor = os.open(
                    self.complete_path.name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=root_descriptor,
                )
            except FileExistsError as exc:
                raise ControlError("COMPLETE receipt already exists") from exc
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._fsync_root(root_descriptor)
        finally:
            os.close(root_descriptor)
