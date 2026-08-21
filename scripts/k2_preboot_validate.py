#!/usr/bin/env python3
"""Validate the offline K2-001 pre-production candidate package.

This utility is intentionally provider-neutral and performs no network, GPU, paid,
authority, domain-admission or publication action.  It verifies that the checked-in
creative draft stays inside the current K2 target, the Project Lead's CNY 1,000 hard
ceiling and the fail-closed P0/P1 truth boundary.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence


PREBOOT_SCHEMA_VERSION = "k2.preboot-candidate.v1"
PACKAGE_ID = "k2-001-preboot-v1"
MAX_BUDGET_MINOR = 100_000
FRAME_RATE = 24
TOTAL_FRAMES = 720
SHOT_DURATIONS = (168, 168, 192, 192)
CHARACTER_KEYS = ("character-lin", "character-gu")
REQUIRED_CHARACTER_VIEWS = (
    "front-full",
    "front-close",
    "three-quarter-left",
    "profile-left",
    "profile-right",
    "rear-three-quarter",
    "rear-full",
    "expression-sheet",
)
MODEL_FILES = {
    "UNET": (
        "wan2.2_ti2v_5B_fp16.safetensors",
        "456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e",
    ),
    "TEXT_ENCODER": (
        "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68",
    ),
    "VAE": (
        "wan2.2_vae.safetensors",
        "e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156",
    ),
}
BLOCKERS = (
    "RIGHTS_AUTHORITY_BUNDLE_MISSING",
    "PROVIDER_AUTHORITY_BUNDLE_MISSING",
    "BUDGET_AUTHORITY_REF_MISSING",
    "IMAGE_CURRENT_G4_GENERATION_REQUEST_MISSING",
    "IMAGE_LIVE_ADAPTER_MISSING",
    "AUDIO_LIVE_ADAPTER_MISSING",
    "IMAGE_PROVIDER_EXPERIMENT_MISSING",
    "VIDEO_SAME_LINEAGE_PROVIDER_EXPERIMENT_MISSING",
    "AUDIO_PROVIDER_EXPERIMENT_MISSING",
    "CANDIDATE_SELECTION_MISSING",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SECRET_FIELD_PATTERN = re.compile(
    r"(?:api[_-]?key|access[_-]?key|secret|token|password|credentialvalue)",
    re.IGNORECASE,
)


class PrebootValidationError(ValueError):
    """The preboot candidate cannot be treated as a safe offline package."""


def _fields(value: Any, expected: set[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise PrebootValidationError(f"{field} fields are invalid")
    return value


def _text(value: Any, field: str, *, maximum: int = 4_000) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise PrebootValidationError(f"{field} is invalid")
    return value


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PrebootValidationError(f"{field} is invalid")
    return value


def _false(value: Any, field: str) -> None:
    if value is not False:
        raise PrebootValidationError(f"{field} must remain false")


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise PrebootValidationError(f"{field} is invalid")
    return value


def _string_list(
    value: Any,
    field: str,
    *,
    exact: Sequence[str] | None = None,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise PrebootValidationError(f"{field} is invalid")
    result = [_text(item, f"{field}[{index}]") for index, item in enumerate(value)]
    if len(result) != len(set(result)):
        raise PrebootValidationError(f"{field} contains duplicates")
    if exact is not None and tuple(result) != tuple(exact):
        raise PrebootValidationError(f"{field} does not match the frozen package")
    return result


def _reject_secrets(value: Any, field: str = "manifest") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or SECRET_FIELD_PATTERN.search(key):
                raise PrebootValidationError(f"{field} contains a secret-shaped field")
            _reject_secrets(nested, f"{field}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_secrets(nested, f"{field}[{index}]")


def _validate_truth_boundary(value: Any) -> None:
    boundary = _fields(
        value,
        {
            "classification",
            "domainFact",
            "publicationAllowed",
            "spendingAuthorized",
            "currentGate",
            "nextGateAllowed",
        },
        "truthBoundary",
    )
    if boundary["classification"] != "DRAFT_CANDIDATE_NOT_DOMAIN_FACT":
        raise PrebootValidationError("truthBoundary.classification is invalid")
    _false(boundary["domainFact"], "truthBoundary.domainFact")
    _false(boundary["publicationAllowed"], "truthBoundary.publicationAllowed")
    _false(boundary["spendingAuthorized"], "truthBoundary.spendingAuthorized")
    _false(boundary["nextGateAllowed"], "truthBoundary.nextGateAllowed")
    if boundary["currentGate"] != "P1_NOT_PASSED":
        raise PrebootValidationError("truthBoundary.currentGate is invalid")


def _validate_budget(value: Any) -> None:
    budget = _fields(
        value,
        {
            "currency",
            "hardCapMinor",
            "committedSpendMinor",
            "allocationState",
            "paidCallsAllowedNow",
        },
        "budget",
    )
    if budget["currency"] != "CNY":
        raise PrebootValidationError("budget.currency must be CNY")
    if _integer(budget["hardCapMinor"], "budget.hardCapMinor", minimum=1) != MAX_BUDGET_MINOR:
        raise PrebootValidationError("budget.hardCapMinor must equal the CNY 1,000 ceiling")
    if _integer(budget["committedSpendMinor"], "budget.committedSpendMinor") != 0:
        raise PrebootValidationError("budget.committedSpendMinor must remain zero offline")
    if budget["allocationState"] != "UNALLOCATED_PENDING_PROVIDER_QUOTES":
        raise PrebootValidationError("budget.allocationState is invalid")
    _false(budget["paidCallsAllowedNow"], "budget.paidCallsAllowedNow")


def _validate_episode(value: Any) -> None:
    episode = _fields(
        value,
        {
            "designKey",
            "title",
            "sourceClassification",
            "targetDurationSec",
            "frameRate",
            "totalFrames",
            "aspectRatio",
            "sceneCount",
            "shotCount",
        },
        "episodeDesign",
    )
    expected = {
        "designKey": "K2-001",
        "title": "记忆回声",
        "sourceClassification": "CURRENT_K2_LOCAL_EVIDENCE_BASELINE",
        "targetDurationSec": 30,
        "frameRate": FRAME_RATE,
        "totalFrames": TOTAL_FRAMES,
        "aspectRatio": "16:9",
        "sceneCount": 2,
        "shotCount": 4,
    }
    if dict(episode) != expected:
        raise PrebootValidationError("episodeDesign does not match the frozen K2 target")


def _validate_technical_evidence(value: Any) -> None:
    evidence = _fields(
        value,
        {
            "attestationRef",
            "attestationPayloadDigest",
            "authorityState",
            "providerAuthorityAccepted",
            "publicationAllowed",
        },
        "technicalEvidence",
    )
    if evidence["attestationRef"] != "technical-k2-funhpc-a100-20260820T141317Z":
        raise PrebootValidationError("technicalEvidence.attestationRef is invalid")
    if _sha256(
        evidence["attestationPayloadDigest"],
        "technicalEvidence.attestationPayloadDigest",
    ) != "3a0ad8e839545390b3baaf3de57903f57f0c40c5bcaa117cd9990cd616c1bec2":
        raise PrebootValidationError("technicalEvidence digest does not match the reviewed artifact")
    if evidence["authorityState"] != "TECHNICAL_EVIDENCE_ONLY":
        raise PrebootValidationError("technicalEvidence.authorityState is invalid")
    _false(evidence["providerAuthorityAccepted"], "technicalEvidence.providerAuthorityAccepted")
    _false(evidence["publicationAllowed"], "technicalEvidence.publicationAllowed")


def _validate_models(value: Any) -> None:
    if not isinstance(value, list) or len(value) != len(MODEL_FILES):
        raise PrebootValidationError("models are invalid")
    observed: dict[str, tuple[str, str]] = {}
    for index, raw in enumerate(value):
        model = _fields(raw, {"role", "name", "sha256"}, f"models[{index}]")
        role = _text(model["role"], f"models[{index}].role")
        if role in observed:
            raise PrebootValidationError("models contain duplicate roles")
        observed[role] = (
            _text(model["name"], f"models[{index}].name"),
            _sha256(model["sha256"], f"models[{index}].sha256"),
        )
    if observed != MODEL_FILES:
        raise PrebootValidationError("models do not match the verified runtime digests")


def _validate_characters(value: Any) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise PrebootValidationError("characters are invalid")
    keys: list[str] = []
    names: list[str] = []
    for index, raw in enumerate(value):
        character = _fields(
            raw,
            {
                "characterKey",
                "name",
                "designStatus",
                "visualAnchors",
                "forbiddenDrift",
                "requiredViews",
            },
            f"characters[{index}]",
        )
        keys.append(_text(character["characterKey"], f"characters[{index}].characterKey"))
        names.append(_text(character["name"], f"characters[{index}].name"))
        if character["designStatus"] != "DRAFT_CANDIDATE_NOT_IDENTITY_AUTHORITY":
            raise PrebootValidationError(f"characters[{index}].designStatus is invalid")
        _string_list(character["visualAnchors"], f"characters[{index}].visualAnchors")
        _string_list(character["forbiddenDrift"], f"characters[{index}].forbiddenDrift")
        _string_list(
            character["requiredViews"],
            f"characters[{index}].requiredViews",
            exact=REQUIRED_CHARACTER_VIEWS,
        )
    if tuple(keys) != CHARACTER_KEYS or tuple(names) != ("林澈", "顾言"):
        raise PrebootValidationError("characters do not match the K2 baseline order")


def _validate_camera(value: Any, field: str) -> None:
    camera = _fields(
        value,
        {"shotSize", "movement", "angle", "lensMm", "intent"},
        field,
    )
    for key in ("shotSize", "movement", "angle", "intent"):
        _text(camera[key], f"{field}.{key}")
    lens = _integer(camera["lensMm"], f"{field}.lensMm", minimum=1)
    if lens > 200:
        raise PrebootValidationError(f"{field}.lensMm is invalid")


def _validate_dialogue(value: Any, field: str) -> None:
    dialogue = _fields(
        value,
        {"speaker", "transcript", "emotion", "sourceStatus", "estimatedStartSec"},
        field,
    )
    speaker = dialogue["speaker"]
    transcript = dialogue["transcript"]
    emotion = dialogue["emotion"]
    if speaker is None:
        if transcript != "" or emotion != "NONE":
            raise PrebootValidationError(f"{field} silent dialogue is invalid")
    else:
        _text(speaker, f"{field}.speaker")
        _text(transcript, f"{field}.transcript")
        _text(emotion, f"{field}.emotion")
    if dialogue["sourceStatus"] != "CURRENT_SCRIPT_CANDIDATE":
        raise PrebootValidationError(f"{field}.sourceStatus is invalid")
    start = dialogue["estimatedStartSec"]
    if isinstance(start, bool) or not isinstance(start, (int, float)) or start < 0 or start > 30:
        raise PrebootValidationError(f"{field}.estimatedStartSec is invalid")


def _validate_image_plan(value: Any, field: str) -> None:
    image = _fields(
        value,
        {
            "purpose",
            "requiredCharacterViews",
            "targetWidth",
            "targetHeight",
            "adapterState",
            "outputAdmitted",
        },
        field,
    )
    _text(image["purpose"], f"{field}.purpose")
    views = _string_list(image["requiredCharacterViews"], f"{field}.requiredCharacterViews")
    if not set(views).issubset(REQUIRED_CHARACTER_VIEWS):
        raise PrebootValidationError(f"{field}.requiredCharacterViews is invalid")
    if _integer(image["targetWidth"], f"{field}.targetWidth", minimum=256) != 1024:
        raise PrebootValidationError(f"{field}.targetWidth is invalid")
    if _integer(image["targetHeight"], f"{field}.targetHeight", minimum=256) != 1024:
        raise PrebootValidationError(f"{field}.targetHeight is invalid")
    if image["adapterState"] != "DESIGN_ONLY_ADAPTER_NOT_SELECTED":
        raise PrebootValidationError(f"{field}.adapterState is invalid")
    _false(image["outputAdmitted"], f"{field}.outputAdmitted")


def _validate_video_plan(value: Any, field: str) -> None:
    video = _fields(
        value,
        {
            "modelId",
            "profileId",
            "smokeFrames",
            "width",
            "height",
            "frameRate",
            "promptDraft",
            "negativePromptDraft",
            "seedResolution",
            "dispatchState",
            "outputAdmitted",
        },
        field,
    )
    expected = {
        "modelId": "wan2.2-ti2v-5b-fp16",
        "profileId": "k2.wan22-ti2v.p1-smoke.v1",
        "smokeFrames": 49,
        "width": 640,
        "height": 352,
        "frameRate": FRAME_RATE,
        "seedResolution": "DERIVE_FROM_CURRENT_GENERATION_REQUEST_DIGEST_AT_RUNTIME",
        "dispatchState": "DESIGN_ONLY_NO_DISPATCH",
        "outputAdmitted": False,
    }
    for key, expected_value in expected.items():
        if video[key] != expected_value:
            raise PrebootValidationError(f"{field}.{key} is invalid")
    _text(video["promptDraft"], f"{field}.promptDraft")
    _text(video["negativePromptDraft"], f"{field}.negativePromptDraft")


def _validate_audio_plan(value: Any, field: str, transcript: str) -> None:
    audio = _fields(
        value,
        {
            "mode",
            "dialogueTranscript",
            "voiceProfile",
            "voiceCloning",
            "externalAudioRef",
            "musicMode",
            "ambienceCandidate",
            "sampleRate",
            "channels",
            "adapterState",
            "outputAdmitted",
        },
        field,
    )
    if audio["mode"] != "TEXT_ONLY_NEUTRAL_TTS_PLAN":
        raise PrebootValidationError(f"{field}.mode is invalid")
    if audio["dialogueTranscript"] != transcript:
        raise PrebootValidationError(f"{field}.dialogueTranscript must match the script candidate")
    _text(audio["voiceProfile"], f"{field}.voiceProfile")
    _false(audio["voiceCloning"], f"{field}.voiceCloning")
    if audio["externalAudioRef"] is not None:
        raise PrebootValidationError(f"{field}.externalAudioRef must remain null")
    if audio["musicMode"] != "NONE_FOR_P1":
        raise PrebootValidationError(f"{field}.musicMode is invalid")
    _text(audio["ambienceCandidate"], f"{field}.ambienceCandidate")
    if _integer(audio["sampleRate"], f"{field}.sampleRate", minimum=8_000) != 48_000:
        raise PrebootValidationError(f"{field}.sampleRate is invalid")
    if _integer(audio["channels"], f"{field}.channels", minimum=1) != 2:
        raise PrebootValidationError(f"{field}.channels is invalid")
    if audio["adapterState"] != "DESIGN_ONLY_ADAPTER_NOT_SELECTED":
        raise PrebootValidationError(f"{field}.adapterState is invalid")
    _false(audio["outputAdmitted"], f"{field}.outputAdmitted")


def _validate_shots(value: Any) -> None:
    if not isinstance(value, list) or len(value) != 4:
        raise PrebootValidationError("shots must contain exactly four entries")
    expected_start = 0
    orders: list[int] = []
    for index, raw in enumerate(value):
        field = f"shots[{index}]"
        shot = _fields(
            raw,
            {
                "shotKey",
                "sceneNumber",
                "globalOrder",
                "startFrame",
                "durationFrames",
                "frameRate",
                "cameraBaseline",
                "storyBeatCandidate",
                "dialoguePlan",
                "imagePreflight",
                "videoExperimentDraft",
                "audioExperimentDraft",
                "continuityCandidate",
                "candidateStatus",
            },
            field,
        )
        order = _integer(shot["globalOrder"], f"{field}.globalOrder", minimum=1)
        orders.append(order)
        if shot["shotKey"] != f"K2-001-SH-{order * 10:03d}":
            raise PrebootValidationError(f"{field}.shotKey is invalid")
        expected_scene = 1 if order <= 2 else 2
        if shot["sceneNumber"] != expected_scene:
            raise PrebootValidationError(f"{field}.sceneNumber is invalid")
        if shot["startFrame"] != expected_start:
            raise PrebootValidationError(f"{field}.startFrame breaks contiguous timing")
        duration = _integer(shot["durationFrames"], f"{field}.durationFrames", minimum=1)
        if duration != SHOT_DURATIONS[index]:
            raise PrebootValidationError(f"{field}.durationFrames is invalid")
        expected_start += duration
        if shot["frameRate"] != FRAME_RATE:
            raise PrebootValidationError(f"{field}.frameRate is invalid")
        _validate_camera(shot["cameraBaseline"], f"{field}.cameraBaseline")
        _text(shot["storyBeatCandidate"], f"{field}.storyBeatCandidate")
        _validate_dialogue(shot["dialoguePlan"], f"{field}.dialoguePlan")
        _validate_image_plan(shot["imagePreflight"], f"{field}.imagePreflight")
        _validate_video_plan(shot["videoExperimentDraft"], f"{field}.videoExperimentDraft")
        _validate_audio_plan(
            shot["audioExperimentDraft"],
            f"{field}.audioExperimentDraft",
            shot["dialoguePlan"]["transcript"],
        )
        _string_list(shot["continuityCandidate"], f"{field}.continuityCandidate")
        if shot["candidateStatus"] != "DRAFT_NOT_CONFIRMED":
            raise PrebootValidationError(f"{field}.candidateStatus is invalid")
    if orders != [1, 2, 3, 4] or expected_start != TOTAL_FRAMES:
        raise PrebootValidationError("shots do not form the frozen 720-frame sequence")


def _validate_experiments(value: Any) -> None:
    if not isinstance(value, list) or len(value) != 3:
        raise PrebootValidationError("experiments must cover image, video and audio")
    expected_states = {
        "image": "NOT_SELECTED",
        "video": "TECHNICAL_PREREQUISITE_ONLY",
        "audio": "NOT_SELECTED",
    }
    expected_request_resolution = {
        "image": "BLOCKED_CURRENT_G4_IMAGE_REQUEST_ABSENT",
        "video": "AT_RUNTIME_FROM_CURRENT_G4",
        "audio": "AT_RUNTIME_FROM_CURRENT_G4",
    }
    kinds: list[str] = []
    for index, raw in enumerate(value):
        field = f"experiments[{index}]"
        experiment = _fields(
            raw,
            {
                "mediaKind",
                "lineageRule",
                "generationRequestResolution",
                "adapterState",
                "authorityRequired",
                "realAttemptRecorded",
                "candidateSelected",
                "assetAdmitted",
                "publicationAllowed",
            },
            field,
        )
        kind = _text(experiment["mediaKind"], f"{field}.mediaKind")
        kinds.append(kind)
        if experiment["lineageRule"] != "SAME_CURRENT_K2_GENERATION_REQUEST_REQUIRED":
            raise PrebootValidationError(f"{field}.lineageRule is invalid")
        if experiment["generationRequestResolution"] != expected_request_resolution.get(kind):
            raise PrebootValidationError(f"{field}.generationRequestResolution is invalid")
        if experiment["adapterState"] != expected_states.get(kind):
            raise PrebootValidationError(f"{field}.adapterState is invalid")
        if experiment["authorityRequired"] is not True:
            raise PrebootValidationError(f"{field}.authorityRequired must remain true")
        for key in (
            "realAttemptRecorded",
            "candidateSelected",
            "assetAdmitted",
            "publicationAllowed",
        ):
            _false(experiment[key], f"{field}.{key}")
    if kinds != ["image", "video", "audio"]:
        raise PrebootValidationError("experiments must remain ordered image/video/audio")


def _validate_authority_inputs(value: Any) -> None:
    authority = _fields(
        value,
        {"rightsBundle", "providerBundle", "budgetAuthorityRef", "runtimeCredential"},
        "authorityInputs",
    )
    if authority["rightsBundle"] != "MISSING_EXTERNAL_FACT":
        raise PrebootValidationError("authorityInputs.rightsBundle is invalid")
    if authority["providerBundle"] != "MISSING_EXTERNAL_FACT":
        raise PrebootValidationError("authorityInputs.providerBundle is invalid")
    if authority["budgetAuthorityRef"] != "MISSING_EXTERNAL_FACT":
        raise PrebootValidationError("authorityInputs.budgetAuthorityRef is invalid")
    if authority["runtimeCredential"] != "NOT_STORED_IN_PACKAGE":
        raise PrebootValidationError("authorityInputs.runtimeCredential is invalid")


def validate_preboot_manifest(manifest: Any) -> dict[str, Any]:
    """Validate and return a shallow result summary for an offline manifest."""

    root = _fields(
        manifest,
        {
            "schemaVersion",
            "packageId",
            "truthBoundary",
            "budget",
            "episodeDesign",
            "technicalEvidence",
            "models",
            "authorityInputs",
            "characters",
            "shots",
            "experiments",
            "runtimeChecklist",
            "blockers",
        },
        "manifest",
    )
    _reject_secrets(root)
    if root["schemaVersion"] != PREBOOT_SCHEMA_VERSION:
        raise PrebootValidationError("schemaVersion is invalid")
    if root["packageId"] != PACKAGE_ID:
        raise PrebootValidationError("packageId is invalid")
    _validate_truth_boundary(root["truthBoundary"])
    _validate_budget(root["budget"])
    _validate_episode(root["episodeDesign"])
    _validate_technical_evidence(root["technicalEvidence"])
    _validate_models(root["models"])
    _validate_authority_inputs(root["authorityInputs"])
    _validate_characters(root["characters"])
    _validate_shots(root["shots"])
    _validate_experiments(root["experiments"])
    _string_list(root["runtimeChecklist"], "runtimeChecklist")
    _string_list(root["blockers"], "blockers", exact=BLOCKERS)
    canonical = json.dumps(
        root, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schemaVersion": PREBOOT_SCHEMA_VERSION,
        "packageId": PACKAGE_ID,
        "manifestSha256": sha256(canonical).hexdigest(),
        "shotCount": 4,
        "totalFrames": TOTAL_FRAMES,
        "budgetHardCapMinor": MAX_BUDGET_MINOR,
        "gate": "P1_NOT_PASSED",
        "publicationAllowed": False,
    }


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PrebootValidationError("manifest JSON contains duplicate keys")
        result[key] = value
    return result


def load_manifest(path: Path) -> Any:
    if not path.is_absolute():
        raise PrebootValidationError("manifest path must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PrebootValidationError("manifest path is unavailable") from exc
    if not resolved.is_file() or resolved.stat().st_size > 2_000_000:
        raise PrebootValidationError("manifest file is invalid")
    try:
        return json.loads(
            resolved.read_text(encoding="utf-8"),
            object_pairs_hook=_no_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PrebootValidationError("manifest JSON is invalid") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the offline K2-001 script/storyboard/Wan2.2/audio candidate "
            "without calling a provider or granting production authority."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    args = parser.parse_args(argv)
    try:
        result = validate_preboot_manifest(load_manifest(args.manifest))
    except PrebootValidationError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print("K2_PREBOOT_PACKAGE=PASS")
        print(f"MANIFEST_SHA256={result['manifestSha256']}")
        print("BUDGET_HARD_CAP=CNY_1000")
        print("PAID_CALLS_EXECUTED=0")
        print("P1_GATE=NOT_PASSED")
        print("PUBLICATION_ALLOWED=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
