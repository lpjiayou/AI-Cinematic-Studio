from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
from types import SimpleNamespace
import struct
import tempfile
from typing import Any
import unittest
from unittest.mock import patch
import wave

from services.v3_render_core import DigestError
from services.v3_render_core import digests as render_digests
from services.v3_render_core.composition import (
    _PinnedRegularFile,
    _PinnedRuntimeBinary,
    RenderArtifactError,
    _publish_timeline_output_v1,
    _require_stable_runtime_binary,
    _runtime_binary_identity,
)
from services.v4_platform import V4CompositionExecutor, probe_media
from services.v4_platform.audio_validation import analyze_audio_artifact
from services.v5_core_os.episode_production.audio_authority import (
    validate_ambience_asset_version,
    validate_dialogue_asset_version,
    validate_music_asset_version,
    validate_sfx_asset_version,
)
from services.v5_core_os.episode_production.audio_timing import (
    build_source_audio_timing_evidence,
    validate_audio_cue,
)
from services.v5_core_os.episode_production.audio_validation import (
    build_audio_technical_validation,
    validate_audio_technical_validation,
)
from services.v5_core_os.episode_production.delivery import (
    K2DeliveryService,
    RejectingApprovalAuthority,
)
from services.v5_core_os.episode_production.evidence import (
    EvidenceFact,
    EvidenceRecord,
    GateAppend,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
)
from services.v5_core_os.episode_production.glyph_reveal_v2 import (
    DigestPinnedBasePlateGlyphInspectionAdapter,
    GlyphRevealRequirementV2,
    build_glyph_reveal_requirement_v2,
)
from services.v5_core_os.episode_production.media import (
    ArtifactRejectedError,
    WorkerUnavailableError,
)
from services.v5_core_os.episode_production.timeline_preview import (
    TECHNICAL_FIXTURE_LABELS,
    build_audio_input_binding,
    validate_audio_input_binding,
)
from tests.contract.test_m12_audio_technical_validation_contract import (
    validation_command,
)
from tests.contract.test_m12_audio_timing_contract import (
    SCRIPT_VERSION_DIGEST,
    SCRIPT_VERSION_REF,
    build_cue,
    build_stem_member_fixture,
    build_stem_set_fixture,
    explicit_source_assets,
    validate_stem_set_fixture,
)
from tests.contract.test_m13_glyph_reveal_v2_contract import (
    InMemoryInspectionEvidenceStore,
    inspection_evidence_v2,
    requirement_command_v2,
)
from tests.integration.test_m13_glyph_reveal_composition import (
    FRAME_COUNT,
    FRAME_RATE,
)
from tests.integration.test_m13_glyph_reveal_v2_composition import (
    _stage_small_v2_inputs,
)


SAMPLE_RATE = 48_000
SOURCE_SAMPLE_COUNT = 48_000
OUTPUT_SAMPLE_COUNT = 98_000
CREATED_AT = "2026-08-30T05:12:00Z"
OPERATION_REF = "m12-m13-minimal-preview-v1"
REGISTER_KEY = "m12-m13-minimal-preview-inputs-v1"
PREVIEW_KEY = "m12-m13-minimal-preview-compose-v1"


def _resealed(value: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def _write_deterministic_dialogue_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = [
        4_000 if index % 48 < 24 else -4_000
        for index in range(SOURCE_SAMPLE_COUNT)
    ]
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def _real_dialogue_inputs(root: Path) -> dict[str, Any]:
    bundle = explicit_source_assets()
    original = bundle["sources"]["dialogue"]
    original_asset = original["asset"]
    storage_key = original_asset["artifact"]["storageKey"]
    audio_path = root / storage_key
    _write_deterministic_dialogue_wav(audio_path)
    content = audio_path.read_bytes()
    file_digest = sha256(content).hexdigest()

    evidence = deepcopy(original["v4Evidence"])
    evidence.pop("payloadDigest", None)
    evidence.update(
        {
            "artifactRef": "audio-artifact-" + file_digest[:32],
            "storageKey": storage_key,
            "byteSize": len(content),
            "sha256": file_digest,
            "sampleRate": SAMPLE_RATE,
            "channels": 1,
            "probe": {
                "sampleRate": SAMPLE_RATE,
                "channels": 1,
                "durationSeconds": 1.0,
                "durationSamples": SOURCE_SAMPLE_COUNT,
                "codec": "pcm_s16le",
                "container": "wav",
            },
        }
    )
    evidence["artifactEvidenceRef"] = (
        "audio-artifact-evidence-"
        + _digest(
            {
                "generationRequestDigest": evidence[
                    "generationRequestDigest"
                ],
                "executionRequestDigest": evidence[
                    "executionRequestDigest"
                ],
                "storageKey": storage_key,
                "sha256": file_digest,
            }
        )[:32]
    )
    evidence = _resealed(evidence)

    asset = deepcopy(original_asset)
    asset.pop("payloadDigest", None)
    asset["artifact"].update(
        {
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "artifactRef": evidence["artifactRef"],
            "storageKey": storage_key,
            "byteSize": len(content),
            "fileDigest": file_digest,
        }
    )
    provenance = deepcopy(asset["provenance"])
    provenance.pop("payloadDigest", None)
    provenance.update(
        {
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
        }
    )
    asset["provenance"] = _resealed(provenance)
    asset = _resealed(asset)
    asset_contract = validate_dialogue_asset_version(
        asset,
        confirmed_voice_lock=bundle["confirmedVoiceLock"],
        voice_asset_version=bundle["voiceAsset"],
    )
    timing = build_source_audio_timing_evidence(
        evidence,
        source_asset_version=asset_contract,
    )
    source = {
        "asset": asset,
        "assetContract": asset_contract,
        "v4Evidence": evidence,
        "timingEvidence": timing,
    }
    bundle["sources"]["dialogue"] = source

    cue_mapping = build_cue(
        source,
        "dialogue",
        sourceEndSample=SOURCE_SAMPLE_COUNT,
    )
    cue = validate_audio_cue(
        cue_mapping,
        source_asset_version=asset_contract,
        source_artifact_evidence=evidence,
        source_timing_evidence=timing,
        expected_script_version_ref=SCRIPT_VERSION_REF,
        expected_script_version_digest=SCRIPT_VERSION_DIGEST,
    )
    analysis = analyze_audio_artifact(evidence, artifact_root=root)
    technical_command = validation_command("minimal-preview-dialogue")
    technical_command.update(
        {
            "validationRef": "audio-technical-validation-minimal-preview",
            "validationVersionRef": (
                "audio-technical-validation-minimal-preview-v1"
            ),
            "createdAt": CREATED_AT,
        }
    )
    validation_mapping = build_audio_technical_validation(
        technical_command,
        source_asset_version=asset_contract,
        source_artifact_evidence=evidence,
        v4_analysis_evidence=analysis,
        audio_cues=[cue],
    )
    validation = validate_audio_technical_validation(
        validation_mapping,
        source_asset_version=asset_contract,
        source_artifact_evidence=evidence,
        v4_analysis_evidence=analysis,
        audio_cues=[cue],
    )
    binding = validate_audio_input_binding(
        build_audio_input_binding(
            {
                "workspaceRef": asset["workspaceRef"],
                "productionRunRef": asset["productionRunRef"],
                "audioInputBindingRef": (
                    "audio-input-binding-minimal-preview-dialogue"
                ),
                "sourceLabels": sorted(TECHNICAL_FIXTURE_LABELS),
            },
            asset_version=asset_contract,
            technical_validation=validation,
        )
    )
    member = build_stem_member_fixture(
        source,
        "dialogue",
        suffix="minimal-preview",
        cue=cue_mapping,
        source_end=SOURCE_SAMPLE_COUNT,
    )
    stem_mapping = build_stem_set_fixture(
        bundle,
        [member],
        suffix="minimal-preview",
        cues=[cue_mapping],
        duration=SOURCE_SAMPLE_COUNT,
    )
    stem_set = validate_stem_set_fixture(
        bundle,
        stem_mapping,
        cues=[cue_mapping],
    )
    return {
        "source": source,
        "cue": cue,
        "member": member,
        "stemSet": stem_set,
        "binding": binding,
        "analysis": analysis,
        "audioPath": audio_path,
    }


def _real_non_speech_audio_input(
    root: Path,
    bundle: dict[str, Any],
    role: str,
) -> dict[str, Any]:
    if role not in {"narration", "sfx", "ambience", "music"}:
        raise AssertionError("unsupported deterministic technical audio role")
    original = bundle["sources"][role]
    original_asset = original["asset"]
    storage_key = original_asset["artifact"]["storageKey"]
    audio_path = root / storage_key
    _write_deterministic_dialogue_wav(audio_path)
    content = audio_path.read_bytes()
    file_digest = sha256(content).hexdigest()

    evidence = deepcopy(original["v4Evidence"])
    evidence.pop("payloadDigest", None)
    evidence.update(
        {
            "artifactRef": "audio-artifact-" + file_digest[:32],
            "storageKey": storage_key,
            "byteSize": len(content),
            "sha256": file_digest,
            "sampleRate": SAMPLE_RATE,
            "channels": 1,
            "probe": {
                "sampleRate": SAMPLE_RATE,
                "channels": 1,
                "durationSeconds": 1.0,
                "durationSamples": SOURCE_SAMPLE_COUNT,
                "codec": "pcm_s16le",
                "container": "wav",
            },
        }
    )
    evidence["artifactEvidenceRef"] = (
        "audio-artifact-evidence-"
        + _digest(
            {
                "generationRequestDigest": evidence[
                    "generationRequestDigest"
                ],
                "executionRequestDigest": evidence[
                    "executionRequestDigest"
                ],
                "storageKey": storage_key,
                "sha256": file_digest,
            }
        )[:32]
    )
    evidence = _resealed(evidence)

    asset = deepcopy(original_asset)
    asset.pop("payloadDigest", None)
    asset["artifact"].update(
        {
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "artifactRef": evidence["artifactRef"],
            "storageKey": storage_key,
            "byteSize": len(content),
            "fileDigest": file_digest,
        }
    )
    provenance = deepcopy(asset["provenance"])
    provenance.pop("payloadDigest", None)
    provenance.update(
        {
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
        }
    )
    asset["provenance"] = _resealed(provenance)
    asset = _resealed(asset)
    if role == "narration":
        asset_contract = validate_dialogue_asset_version(
            asset,
            confirmed_voice_lock=bundle["confirmedVoiceLock"],
            voice_asset_version=bundle["voiceAsset"],
        )
    elif role == "sfx":
        asset_contract = validate_sfx_asset_version(asset)
    elif role == "ambience":
        asset_contract = validate_ambience_asset_version(asset)
    else:
        asset_contract = validate_music_asset_version(asset)
    timing = build_source_audio_timing_evidence(
        evidence,
        source_asset_version=asset_contract,
    )
    source = {
        "asset": asset,
        "assetContract": asset_contract,
        "v4Evidence": evidence,
        "timingEvidence": timing,
    }
    bundle["sources"][role] = source

    cue_mapping = build_cue(
        source,
        role,
        sourceEndSample=SOURCE_SAMPLE_COUNT,
    )
    cue = validate_audio_cue(
        cue_mapping,
        source_asset_version=asset_contract,
        source_artifact_evidence=evidence,
        source_timing_evidence=timing,
        expected_script_version_ref=SCRIPT_VERSION_REF,
        expected_script_version_digest=SCRIPT_VERSION_DIGEST,
    )
    analysis = analyze_audio_artifact(evidence, artifact_root=root)
    technical_command = validation_command(f"minimal-preview-{role}")
    technical_command.update(
        {
            "validationRef": f"audio-technical-validation-{role}-minimal-preview",
            "validationVersionRef": (
                f"audio-technical-validation-{role}-minimal-preview-v1"
            ),
            "createdAt": CREATED_AT,
        }
    )
    validation_mapping = build_audio_technical_validation(
        technical_command,
        source_asset_version=asset_contract,
        source_artifact_evidence=evidence,
        v4_analysis_evidence=analysis,
        audio_cues=[cue],
    )
    validation = validate_audio_technical_validation(
        validation_mapping,
        source_asset_version=asset_contract,
        source_artifact_evidence=evidence,
        v4_analysis_evidence=analysis,
        audio_cues=[cue],
    )
    binding = validate_audio_input_binding(
        build_audio_input_binding(
            {
                "workspaceRef": asset["workspaceRef"],
                "productionRunRef": asset["productionRunRef"],
                "audioInputBindingRef": (
                    f"audio-input-binding-minimal-preview-{role}"
                ),
                "sourceLabels": sorted(TECHNICAL_FIXTURE_LABELS),
            },
            asset_version=asset_contract,
            technical_validation=validation,
        )
    )
    member = build_stem_member_fixture(
        source,
        role,
        suffix="minimal-preview",
        cue=cue_mapping,
        source_end=SOURCE_SAMPLE_COUNT,
    )
    return {
        "source": source,
        "cue": cue,
        "cueMapping": cue_mapping,
        "member": member,
        "binding": binding,
        "analysis": analysis,
        "audioPath": audio_path,
    }


def _real_glyph_inputs(
    root: Path,
    *,
    workspace_ref: str,
    production_run_ref: str,
) -> dict[str, Any]:
    staged = _stage_small_v2_inputs(root)
    base_path = root / staged.base["storageKey"]
    base = _resealed(
        {
            **staged.base,
            "workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            "probe": probe_media(base_path),
        }
    )
    masks = [
        _resealed(
            {
                **mask,
                "workspaceRef": workspace_ref,
                "productionRunRef": production_run_ref,
            }
        )
        for mask in staged.masks
    ]
    inspection = inspection_evidence_v2(
        base,
        media_probe={
            "width": 64,
            "height": 64,
            "frameCount": FRAME_COUNT,
            "frameRate": FRAME_RATE,
        },
    )
    inspection = _resealed(
        {
            **inspection,
            "workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
        }
    )
    adapter = DigestPinnedBasePlateGlyphInspectionAdapter(
        InMemoryInspectionEvidenceStore(inspection)
    )
    requirement = build_glyph_reveal_requirement_v2(
        requirement_command_v2(
            workspaceRef=workspace_ref,
            productionRunRef=production_run_ref,
        ),
        base_plate_asset=base,
        mask_assets=masks,
        inspection_adapter=adapter,
    )
    return {
        "base": base,
        "masks": masks,
        "inspection": inspection,
        "requirement": requirement,
    }


@dataclass(frozen=True)
class _TypedInputs:
    audio: dict[str, Any]
    base: dict[str, Any]
    masks: tuple[dict[str, Any], ...]
    inspection: dict[str, Any]
    requirement: GlyphRevealRequirementV2
    run: dict[str, Any]


def _source_template(root: Path) -> _TypedInputs:
    audio = _real_dialogue_inputs(root)
    asset = audio["source"]["asset"]
    glyph = _real_glyph_inputs(
        root,
        workspace_ref=asset["workspaceRef"],
        production_run_ref=asset["productionRunRef"],
    )
    run = _resealed(
        {
            "schemaVersion": "test.m12-m13-minimal-preview-run.v1",
            "workspaceRef": asset["workspaceRef"],
            "projectRef": asset["projectRef"],
            "seriesRef": asset["seriesRef"],
            "episodeRef": asset["episodeRef"],
            "productionRunRef": asset["productionRunRef"],
            "version": 1,
            "state": "MEDIA_READY",
        }
    )
    return _TypedInputs(
        audio=audio,
        base=glyph["base"],
        masks=tuple(glyph["masks"]),
        inspection=glyph["inspection"],
        requirement=glyph["requirement"],
        run=run,
    )


def _multi_role_source_template(root: Path) -> _TypedInputs:
    template = _source_template(root)
    dialogue = template.audio
    bundle = explicit_source_assets()
    bundle["sources"]["dialogue"] = dialogue["source"]
    sfx = _real_non_speech_audio_input(root, bundle, "sfx")
    ambience = _real_non_speech_audio_input(root, bundle, "ambience")
    cue_mappings = [
        dialogue["cue"].as_dict(),
        sfx["cueMapping"],
        ambience["cueMapping"],
    ]
    members = [
        dialogue["member"],
        sfx["member"],
        ambience["member"],
    ]
    stem_mapping = build_stem_set_fixture(
        bundle,
        members,
        suffix="minimal-preview-multi-role",
        cues=cue_mappings,
        duration=SOURCE_SAMPLE_COUNT,
    )
    stem_set = validate_stem_set_fixture(
        bundle,
        stem_mapping,
        cues=cue_mappings,
    )
    audio = {
        **dialogue,
        "sourceBundle": bundle,
        "sources": (dialogue, sfx, ambience),
        "bindings": (
            dialogue["binding"],
            sfx["binding"],
            ambience["binding"],
        ),
        "cues": (dialogue["cue"], sfx["cue"], ambience["cue"]),
        "members": tuple(members),
        "stemSet": stem_set,
    }
    return _TypedInputs(
        audio=audio,
        base=template.base,
        masks=template.masks,
        inspection=template.inspection,
        requirement=template.requirement,
        run=template.run,
    )


class _CurrentMedia:
    def __init__(self, inputs: _TypedInputs) -> None:
        self._inputs = inputs
        self.assets = SimpleNamespace(
            shot_graph=SimpleNamespace(root_service=self)
        )

    def _check_scope(self, workspace_ref: str, run_ref: str) -> None:
        if (
            workspace_ref != self._inputs.run["workspaceRef"]
            or run_ref != self._inputs.run["productionRunRef"]
        ):
            raise StaleInputError("minimal preview media scope is stale")

    def get_run(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        self._check_scope(workspace_ref, run_ref)
        return deepcopy(self._inputs.run)

    def verify_media_current(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        self._check_scope(workspace_ref, run_ref)
        return {
            "root": deepcopy(self._inputs.run),
            "executableShotGraph": _resealed(
                {
                    "schemaVersion": "test.minimal-shot-graph.v1",
                    "output": {
                        "width": 64,
                        "height": 64,
                        "frameRate": FRAME_RATE,
                        "totalFrames": FRAME_COUNT,
                    },
                }
            ),
            "mediaManifest": _resealed(
                {
                    "schemaVersion": "test.minimal-media-manifest.v1",
                    "mediaManifestRef": "minimal-media-manifest-v1",
                }
            ),
            "creativeShotVersions": [],
            "assetVersions": [deepcopy(self._inputs.base)],
        }


class _CountingComposition:
    def __init__(self, root: Path) -> None:
        self._delegate = V4CompositionExecutor.from_artifact_root(root)
        self.artifact_root = self._delegate.artifact_root
        self.glyph_calls = 0
        self.preview_calls = 0

    def compose_glyph_reveal_v2(
        self, command: dict[str, Any]
    ) -> dict[str, Any]:
        self.glyph_calls += 1
        return self._delegate.compose_glyph_reveal_v2(command)

    def compose_timeline_preview_v1(
        self, command: dict[str, Any]
    ) -> dict[str, Any]:
        self.preview_calls += 1
        return self._delegate.compose_timeline_preview_v1(command)


class _FailBeforeCompositionCommit:
    def __init__(self, delegate: SqliteEpisodeProductionEvidenceAdapter) -> None:
        self._delegate = delegate
        self.failed = False

    def append_records_and_gate(self, *args: Any, **kwargs: Any):
        if not self.failed:
            self.failed = True
            raise RepositoryUnavailableError(
                "simulated failure after deterministic artifact publication"
            )
        return self._delegate.append_records_and_gate(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


def _seed_media_ready(
    repository: SqliteEpisodeProductionEvidenceAdapter,
    inputs: _TypedInputs,
) -> None:
    states = (
        "ROOTS_READY",
        "AUTHORITY_READY",
        "SCRIPT_VALIDATED",
        "SHOTS_COMPILED",
        "ASSETS_READY",
        "MEDIA_READY",
    )
    for ordinal, (from_state, to_state) in enumerate(
        zip(states, states[1:]), start=1
    ):
        payload = {
            "schemaVersion": "test.m12-m13-minimal-gate-fact.v1",
            "ordinal": ordinal,
            "fromState": from_state,
            "toState": to_state,
            "publicationAllowed": False,
        }
        repository.append_gate(
            GateAppend(
                workspaceRef=inputs.run["workspaceRef"],
                productionRunRef=inputs.run["productionRunRef"],
                gateName=f"MINIMAL_PREVIEW_GATE_{ordinal}",
                idempotencyKey=f"minimal-preview-gate-{ordinal}",
                rootPayloadDigest=inputs.run["payloadDigest"],
                requestDigest=_digest(
                    {
                        "ordinal": ordinal,
                        "fromState": from_state,
                        "toState": to_state,
                    }
                ),
                fromState=from_state,
                toState=to_state,
                createdAt=f"2026-08-30T05:00:{ordinal:02d}Z",
                facts=(
                    EvidenceFact(
                        factKind=f"MinimalPreviewGateFact{ordinal}",
                        factRef=f"minimal-preview-gate-fact-{ordinal}",
                        factVersion=1,
                        payload=payload,
                        payloadDigest=_digest(payload),
                    ),
                ),
            )
        )


def _service_with_repository(
    root: Path,
    repository: Any,
    inputs: _TypedInputs,
) -> tuple[K2DeliveryService, _CountingComposition]:
    composition = _CountingComposition(root)
    inspection_adapter = DigestPinnedBasePlateGlyphInspectionAdapter(
        InMemoryInspectionEvidenceStore(inputs.inspection)
    )
    service = K2DeliveryService(
        _CurrentMedia(inputs),
        repository,
        composition,
        RejectingApprovalAuthority(),
        ref_factory=lambda prefix: f"{prefix}-minimal-preview-v1",
        clock=lambda: CREATED_AT,
        glyph_inspection_adapter=inspection_adapter,
    )
    return service, composition


def _service(
    root: Path,
    database_path: Path,
    inputs: _TypedInputs,
    *,
    initialize: bool,
) -> tuple[
    K2DeliveryService,
    SqliteEpisodeProductionEvidenceAdapter,
    _CountingComposition,
]:
    repository = SqliteEpisodeProductionEvidenceAdapter(
        database_path,
        initialize_if_missing=initialize,
    )
    service, composition = _service_with_repository(
        root,
        repository,
        inputs,
    )
    return service, repository, composition


def _register_inputs(
    service: K2DeliveryService,
    inputs: _TypedInputs,
) -> dict[str, Any]:
    bindings = inputs.audio.get("bindings")
    if bindings is None:
        bindings = (inputs.audio["binding"],)
    cues = inputs.audio.get("cues")
    if cues is None:
        cues = (inputs.audio["cue"],)
    return service.record_m12_m13_inputs(
        workspace_ref=inputs.run["workspaceRef"],
        production_run_ref=inputs.run["productionRunRef"],
        idempotency_key=REGISTER_KEY,
        audio_input_bindings=bindings,
        audio_cues=cues,
        audio_stem_set=inputs.audio["stemSet"],
        glyph_reveal_requirement=inputs.requirement,
        mask_assets=inputs.masks,
    )


def _preview_command(
    inputs: _TypedInputs,
    registration: dict[str, Any],
) -> dict[str, Any]:
    bindings = inputs.audio.get("bindings")
    if bindings is None:
        bindings = (inputs.audio["binding"],)
    cues = inputs.audio.get("cues")
    if cues is None:
        cues = (inputs.audio["cue"],)
    stems = inputs.audio["stemSet"].as_dict()
    requirement = inputs.requirement.as_dict()
    return {
        "workspaceRef": inputs.run["workspaceRef"],
        "productionRunRef": inputs.run["productionRunRef"],
        "operationRef": OPERATION_REF,
        "idempotencyKey": PREVIEW_KEY,
        "expectedRunVersion": inputs.run["version"],
        "expectedEvidenceRevision": registration["evidenceRevision"],
        "timelineInputRefs": {
            "videoAssetVersionRef": inputs.base["assetVersionRef"],
            "audioInputBindingRefs": sorted(
                item.as_dict()["audioInputBindingRef"] for item in bindings
            ),
            "audioCueVersionRefs": sorted(
                item.as_dict()["cueVersionRef"] for item in cues
            ),
            "audioStemSetVersionRef": stems["stemSetVersionRef"],
            "glyphRevealRequirementRef": requirement["requirementRef"],
        },
    }


def _semantic_digests(result: dict[str, Any]) -> dict[str, str]:
    return {
        "timeline": result["timelineVersion"]["payloadDigest"],
        "pixel": result["previewCandidate"][
            "decodedFramePixelDigest"
        ],
        "pcm": result["previewCandidate"]["pcmContentDigest"],
        "subtitle": result["subtitleManifest"]["payloadDigest"],
    }


def _stored_fact_payload(database_path: Path, fact_kind: str) -> dict[str, Any]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM v5_episode_production_facts "
            "WHERE fact_kind=?",
            (fact_kind,),
        ).fetchall()
    if len(rows) != 1:
        raise AssertionError(f"expected exactly one {fact_kind} fact")
    value = json.loads(rows[0][0])
    if not isinstance(value, dict):
        raise AssertionError(f"{fact_kind} fact is not an object")
    return value


def _replace_fact_payload(
    database_path: Path,
    fact_kind: str,
    payload: dict[str, Any],
) -> None:
    sealed = _resealed(payload)
    encoded = json.dumps(
        sealed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            "UPDATE v5_episode_production_facts "
            "SET payload_json=?, payload_digest=? WHERE fact_kind=?",
            (encoded, sealed["payloadDigest"], fact_kind),
        )
        if cursor.rowcount != 1:
            raise AssertionError(f"expected exactly one {fact_kind} fact")


def _stored_record_payload(
    database_path: Path,
    record_kind: str,
) -> dict[str, Any]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM v5_episode_production_records "
            "WHERE record_kind=?",
            (record_kind,),
        ).fetchall()
    if len(rows) != 1:
        raise AssertionError(f"expected exactly one {record_kind} record")
    value = json.loads(rows[0][0])
    if not isinstance(value, dict):
        raise AssertionError(f"{record_kind} record is not an object")
    return value


def _replace_record_payload(
    database_path: Path,
    record_kind: str,
    payload: dict[str, Any],
) -> None:
    sealed = _resealed(payload)
    encoded = json.dumps(
        sealed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            "UPDATE v5_episode_production_records "
            "SET payload_json=?, payload_digest=? WHERE record_kind=?",
            (encoded, sealed["payloadDigest"], record_kind),
        )
        if cursor.rowcount != 1:
            raise AssertionError(f"expected exactly one {record_kind} record")


def _append_alternate_stem_set_version(
    repository: SqliteEpisodeProductionEvidenceAdapter,
    inputs: _TypedInputs,
) -> dict[str, Any]:
    original = inputs.audio["stemSet"].as_dict()
    alternate = deepcopy(original)
    alternate.update(
        {
            "stemSetVersionRef": original["stemSetRef"] + "-v2",
            "version": 2,
            "supersedesStemSetVersionRef": original["stemSetVersionRef"],
            "supersedesStemSetVersionDigest": original["payloadDigest"],
        }
    )
    alternate = _resealed(alternate)
    cues = [item.as_dict() for item in inputs.audio["cues"]]
    validated = validate_stem_set_fixture(
        inputs.audio["sourceBundle"],
        alternate,
        cues=cues,
    ).as_dict()
    request_digest = _digest(
        {
            "schemaVersion": "test.alternate-stem-set-record.v1",
            "stemSetVersionRef": validated["stemSetVersionRef"],
            "stemSetDigest": validated["payloadDigest"],
        }
    )
    repository.append_record(
        EvidenceRecord(
            workspaceRef=inputs.run["workspaceRef"],
            productionRunRef=inputs.run["productionRunRef"],
            recordKind="AudioStemSet",
            recordRef=validated["stemSetVersionRef"],
            recordVersion=validated["version"],
            idempotencyKey="minimal-preview-alternate-stem-set-v2",
            requestDigest=request_digest,
            createdAt=CREATED_AT,
            payload=validated,
            payloadDigest=validated["payloadDigest"],
        )
    )
    return validated


class M12M13MinimalPreviewIntegrationTests(unittest.TestCase):
    def test_real_ffmpeg_vertical_slice_is_deterministic_and_restart_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template_root = root / "source-template"
            inputs = _source_template(template_root)
            run_a_root = root / "independent-run-a"
            run_b_root = root / "independent-run-b"
            shutil.copytree(template_root, run_a_root)
            shutil.copytree(template_root, run_b_root)

            completed: list[
                tuple[
                    Path,
                    Path,
                    K2DeliveryService,
                    SqliteEpisodeProductionEvidenceAdapter,
                    _CountingComposition,
                    dict[str, Any],
                    dict[str, Any],
                ]
            ] = []
            recovered_artifacts: dict[Path, tuple[str, int]] = {}
            for run_root in (run_a_root, run_b_root):
                database_path = run_root / "minimal-preview-evidence.sqlite3"
                service, repository, composition = _service(
                    run_root,
                    database_path,
                    inputs,
                    initialize=True,
                )
                _seed_media_ready(repository, inputs)
                registration = _register_inputs(service, inputs)
                command = _preview_command(inputs, registration)
                if run_root == run_a_root:
                    failing_repository = _FailBeforeCompositionCommit(
                        repository
                    )
                    failing_service, failing_composition = (
                        _service_with_repository(
                            run_root,
                            failing_repository,
                            inputs,
                        )
                    )
                    with self.assertRaises(RepositoryUnavailableError):
                        failing_service.compose_timeline_preview(command)
                    self.assertTrue(failing_repository.failed)
                    self.assertEqual(failing_composition.glyph_calls, 1)
                    self.assertEqual(failing_composition.preview_calls, 1)
                    self.assertEqual(
                        repository.current_state(
                            inputs.run["workspaceRef"],
                            inputs.run["productionRunRef"],
                        ),
                        "MEDIA_READY",
                    )
                    published = sorted(
                        path
                        for path in run_root.rglob("*.mp4")
                        if {"glyph-reveal", "composition"}
                        & set(path.relative_to(run_root).parts)
                    )
                    self.assertEqual(len(published), 2)
                    recovered_artifacts = {
                        path: (
                            sha256(path.read_bytes()).hexdigest(),
                            path.stat().st_mtime_ns,
                        )
                        for path in published
                    }
                result = service.compose_timeline_preview(command)
                if run_root == run_a_root:
                    self.assertEqual(
                        {
                            path: (
                                sha256(path.read_bytes()).hexdigest(),
                                path.stat().st_mtime_ns,
                            )
                            for path in recovered_artifacts
                        },
                        recovered_artifacts,
                    )
                completed.append(
                    (
                        run_root,
                        database_path,
                        service,
                        repository,
                        composition,
                        command,
                        result,
                    )
                )

            first = completed[0][-1]
            second = completed[1][-1]
            self.assertEqual(_semantic_digests(first), _semantic_digests(second))
            self.assertFalse(first["idempotentReplay"])
            self.assertFalse(second["idempotentReplay"])
            self.assertEqual(first["state"], "QC_READY")
            self.assertEqual(first["qcReport"]["result"], "PASS")
            self.assertFalse(first["qcReport"]["publicationAllowed"])

            timeline = first["timelineVersion"]
            tracks = timeline["tracks"]
            self.assertEqual(
                [track["trackKind"] for track in tracks],
                ["VIDEO", "AUDIO", "SUBTITLE", "EFFECT"],
            )
            self.assertEqual([len(track["clips"]) for track in tracks], [1, 1, 1, 1])
            self.assertEqual(timeline["durationFrames"], FRAME_COUNT)
            self.assertEqual(timeline["output"]["totalFrames"], FRAME_COUNT)
            self.assertEqual(timeline["output"]["sampleRate"], SAMPLE_RATE)
            self.assertEqual(
                timeline["output"]["durationSamples"], OUTPUT_SAMPLE_COUNT
            )
            self.assertEqual(
                tracks[1]["clips"][0]["sourceBinding"]["stemMemberRef"],
                inputs.audio["member"]["stemMemberRef"],
            )
            self.assertEqual(
                tracks[3]["clips"][0]["sourceBinding"][
                    "glyphRevealRequirementRef"
                ],
                inputs.requirement.requirement_ref,
            )

            subtitle = first["subtitleManifest"]
            self.assertEqual(len(subtitle["entries"]), 1)
            self.assertEqual(subtitle["entries"][0]["text"], "不要动。")
            self.assertEqual(
                subtitle["entries"][0]["audioCueVersionRef"],
                inputs.audio["cue"].as_dict()["cueVersionRef"],
            )
            composition_result = first["compositionResult"]
            probe = composition_result["outputMediaProbe"]
            digest = composition_result["outputDigest"]
            self.assertEqual(probe["frameCount"], FRAME_COUNT)
            self.assertEqual(probe["frameRate"], {"numerator": 24, "denominator": 1})
            self.assertEqual(probe["sampleRate"], SAMPLE_RATE)
            self.assertEqual(probe["sampleCount"], OUTPUT_SAMPLE_COUNT)
            self.assertEqual(probe["channelCount"], 2)
            self.assertEqual(digest["frameCount"], FRAME_COUNT)
            self.assertEqual(digest["sampleRate"], SAMPLE_RATE)
            self.assertEqual(digest["sampleCount"], OUTPUT_SAMPLE_COUNT)
            self.assertFalse(composition_result["providerUsed"])
            self.assertFalse(composition_result["gpuUsed"])
            self.assertFalse(first["previewCandidate"]["publicationAllowed"])
            self.assertEqual(
                first["previewCandidate"]["mixRequestRef"],
                composition_result["mixRequestRef"],
            )

            (
                run_root,
                database_path,
                _,
                repository,
                composition,
                command,
                _,
            ) = completed[0]
            self.assertEqual(composition.glyph_calls, 1)
            self.assertEqual(composition.preview_calls, 1)
            preview_path = run_root / composition_result["outputStorageKey"]
            self.assertTrue(preview_path.is_file())
            original_bytes = preview_path.read_bytes()
            original_mtime = preview_path.stat().st_mtime_ns
            records_before = repository.list_records(
                inputs.run["workspaceRef"], inputs.run["productionRunRef"]
            )
            stem_records = [
                record
                for record in records_before
                if record["recordKind"] == "AudioStemSet"
            ]
            self.assertEqual(len(stem_records), 1)
            self.assertEqual(
                stem_records[0]["payload"]["stemSetVersionRef"],
                inputs.audio["stemSet"].as_dict()["stemSetVersionRef"],
            )
            self.assertEqual(
                [
                    member["stemMemberRef"]
                    for member in stem_records[0]["payload"]["members"]
                ],
                [inputs.audio["member"]["stemMemberRef"]],
            )
            gates_before = repository.list_gates(
                inputs.run["workspaceRef"], inputs.run["productionRunRef"]
            )

            restarted, restarted_repository, restarted_composition = _service(
                run_root,
                database_path,
                inputs,
                initialize=False,
            )
            registration_replay = _register_inputs(restarted, inputs)
            self.assertTrue(registration_replay["idempotentReplay"])
            replay = restarted.compose_timeline_preview(command)
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(_semantic_digests(replay), _semantic_digests(first))
            self.assertEqual(restarted_composition.glyph_calls, 0)
            self.assertEqual(restarted_composition.preview_calls, 0)
            self.assertEqual(preview_path.read_bytes(), original_bytes)
            self.assertEqual(preview_path.stat().st_mtime_ns, original_mtime)
            self.assertEqual(
                restarted_repository.list_records(
                    inputs.run["workspaceRef"],
                    inputs.run["productionRunRef"],
                ),
                records_before,
            )
            self.assertEqual(
                restarted_repository.list_gates(
                    inputs.run["workspaceRef"],
                    inputs.run["productionRunRef"],
                ),
                gates_before,
            )

            changed = deepcopy(command)
            changed["operationRef"] = "m12-m13-minimal-preview-changed"
            with self.assertRaises(IdempotencyConflictError):
                restarted.compose_timeline_preview(changed)
            self.assertEqual(restarted_composition.glyph_calls, 0)
            self.assertEqual(restarted_composition.preview_calls, 0)

            foreign = deepcopy(command)
            foreign["workspaceRef"] = "workspace-foreign-minimal-preview"
            with self.assertRaises(StaleInputError):
                restarted.compose_timeline_preview(foreign)

            preview_path.write_bytes(original_bytes + b"tamper")
            with self.assertRaises(ArtifactRejectedError):
                restarted.compose_timeline_preview(command)
            self.assertEqual(restarted_composition.glyph_calls, 0)
            self.assertEqual(restarted_composition.preview_calls, 0)

    def test_uncommitted_conflicting_timeline_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template_root = root / "source-template"
            inputs = _source_template(template_root)
            run_root = root / "conflict-run"
            shutil.copytree(template_root, run_root)
            database_path = run_root / "minimal-preview-evidence.sqlite3"
            service, repository, composition = _service(
                run_root,
                database_path,
                inputs,
                initialize=True,
            )
            _seed_media_ready(repository, inputs)
            registration = _register_inputs(service, inputs)
            command = _preview_command(inputs, registration)
            records_before = repository.list_records(
                inputs.run["workspaceRef"],
                inputs.run["productionRunRef"],
            )

            failing_repository = _FailBeforeCompositionCommit(repository)
            failing_service, failing_composition = _service_with_repository(
                run_root,
                failing_repository,
                inputs,
            )
            with self.assertRaises(RepositoryUnavailableError):
                failing_service.compose_timeline_preview(command)
            self.assertEqual(failing_composition.glyph_calls, 1)
            self.assertEqual(failing_composition.preview_calls, 1)

            composition_outputs = [
                path
                for path in run_root.rglob("*.mp4")
                if "composition" in path.relative_to(run_root).parts
            ]
            self.assertEqual(len(composition_outputs), 1)
            conflicting_path = composition_outputs[0]
            conflicting_bytes = conflicting_path.read_bytes() + b"conflict"
            conflicting_path.write_bytes(conflicting_bytes)

            with self.assertRaises(WorkerUnavailableError):
                service.compose_timeline_preview(command)
            self.assertEqual(composition.glyph_calls, 1)
            self.assertEqual(composition.preview_calls, 1)
            self.assertEqual(conflicting_path.read_bytes(), conflicting_bytes)
            self.assertEqual(
                repository.current_state(
                    inputs.run["workspaceRef"],
                    inputs.run["productionRunRef"],
                ),
                "MEDIA_READY",
            )
            self.assertEqual(
                repository.list_records(
                    inputs.run["workspaceRef"],
                    inputs.run["productionRunRef"],
                ),
                records_before,
            )

    def test_restart_get_preserves_non_subtitle_cues_and_exact_stem_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _multi_role_source_template(root)
            database_path = root / "minimal-preview-evidence.sqlite3"
            service, repository, composition = _service(
                root,
                database_path,
                inputs,
                initialize=True,
            )
            _seed_media_ready(repository, inputs)
            registration = _register_inputs(service, inputs)
            result = service.compose_timeline_preview(
                _preview_command(inputs, registration)
            )
            self.assertEqual(result["state"], "QC_READY")
            self.assertEqual(composition.glyph_calls, 1)
            self.assertEqual(composition.preview_calls, 1)

            alternate = _append_alternate_stem_set_version(
                repository,
                inputs,
            )
            mix_records = repository.list_records(
                inputs.run["workspaceRef"],
                inputs.run["productionRunRef"],
                record_kind="TimelineMixRequest",
            )
            self.assertEqual(len(mix_records), 1)
            persisted_mix = mix_records[0]["payload"]
            original_stems = inputs.audio["stemSet"].as_dict()
            self.assertEqual(
                persisted_mix["stemSetVersionRef"],
                original_stems["stemSetVersionRef"],
            )
            self.assertNotEqual(
                persisted_mix["stemSetVersionRef"],
                alternate["stemSetVersionRef"],
            )
            self.assertEqual(
                [item["stemMemberRef"] for item in alternate["members"]],
                [item["stemMemberRef"] for item in original_stems["members"]],
            )

            restarted, _, restarted_composition = _service(
                root,
                database_path,
                inputs,
                initialize=False,
            )
            bundle = restarted.get_preview_bundle(
                inputs.run["workspaceRef"],
                inputs.run["productionRunRef"],
            )
            cue_by_role = {item["cueRole"]: item for item in bundle["cues"]}
            self.assertEqual(
                set(cue_by_role),
                {"dialogue", "sfx", "ambience"},
            )
            self.assertIsNotNone(
                cue_by_role["dialogue"]["subtitleTimingReference"]
            )
            self.assertIsNone(
                cue_by_role["sfx"]["subtitleTimingReference"]
            )
            self.assertIsNone(
                cue_by_role["ambience"]["subtitleTimingReference"]
            )
            self.assertEqual(
                {item["audioRole"] for item in bundle["audio"]["bindings"]},
                {"dialogue", "sfx", "ambience"},
            )
            self.assertEqual(
                bundle["audio"]["stemSetVersionRef"],
                persisted_mix["stemSetVersionRef"],
            )
            preview_file = restarted.get_preview_file(
                inputs.run["workspaceRef"],
                inputs.run["productionRunRef"],
            )
            self.assertTrue(Path(preview_file["path"]).is_file())
            self.assertEqual(restarted_composition.glyph_calls, 0)
            self.assertEqual(restarted_composition.preview_calls, 0)

    def test_getters_reject_qc_and_persisted_wrapper_closure_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _source_template(root)
            database_path = root / "minimal-preview-evidence.sqlite3"
            service, repository, composition = _service(
                root,
                database_path,
                inputs,
                initialize=True,
            )
            _seed_media_ready(repository, inputs)
            registration = _register_inputs(service, inputs)
            service.compose_timeline_preview(
                _preview_command(inputs, registration)
            )
            workspace = inputs.run["workspaceRef"]
            run_ref = inputs.run["productionRunRef"]

            original_qc = _stored_fact_payload(database_path, "QCReport")
            qc_mutations = {
                "schemaVersion": lambda value: value.__setitem__(
                    "schemaVersion", "tampered.qc-schema.v1"
                ),
                "machineVerified": lambda value: value.__setitem__(
                    "machineVerified", False
                ),
                "approvalStatus": lambda value: value.__setitem__(
                    "approvalStatus", "APPROVED"
                ),
                "checks": lambda value: value.__setitem__(
                    "checks", value["checks"][:-1]
                ),
            }
            for field, mutate in qc_mutations.items():
                with self.subTest(qc_field=field):
                    tampered = deepcopy(original_qc)
                    mutate(tampered)
                    _replace_fact_payload(database_path, "QCReport", tampered)
                    try:
                        with self.assertRaises(EpisodeProductionError):
                            service.get_preview_bundle(workspace, run_ref)
                        with self.assertRaises(EpisodeProductionError):
                            service.get_preview_file(workspace, run_ref)
                    finally:
                        _replace_fact_payload(
                            database_path,
                            "QCReport",
                            original_qc,
                        )

            wrapper_mutations = {
                "PreviewCandidate": lambda value: value.__setitem__(
                    "approvalStatus", "APPROVED"
                ),
                "CompositionResult": lambda value: value.__setitem__(
                    "providerUsed", True
                ),
                "TimelineVersion": lambda value: value.__setitem__(
                    "authorityState", "TAMPERED"
                ),
            }
            for record_kind, mutate in wrapper_mutations.items():
                with self.subTest(record_kind=record_kind):
                    original = _stored_record_payload(
                        database_path,
                        record_kind,
                    )
                    tampered = deepcopy(original)
                    mutate(tampered)
                    _replace_record_payload(
                        database_path,
                        record_kind,
                        tampered,
                    )
                    try:
                        with self.assertRaises(EpisodeProductionError):
                            service.get_preview_file(workspace, run_ref)
                    finally:
                        _replace_record_payload(
                            database_path,
                            record_kind,
                            original,
                        )

            preview_file = service.get_preview_file(workspace, run_ref)
            self.assertTrue(Path(preview_file["path"]).is_file())
            self.assertEqual(composition.glyph_calls, 1)
            self.assertEqual(composition.preview_calls, 1)

    def test_pcm_and_runtime_identity_reject_path_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_path = root / "dialogue.wav"
            _write_deterministic_dialogue_wav(audio_path)
            original_probe = render_digests._probe_audio_stream

            def replacing_probe(*args: Any, **kwargs: Any) -> dict[str, Any]:
                result = original_probe(*args, **kwargs)
                moved_path = root / "dialogue-original.wav"
                audio_path.replace(moved_path)
                shutil.copyfile(moved_path, audio_path)
                return result

            with patch.object(
                render_digests,
                "_probe_audio_stream",
                side_effect=replacing_probe,
            ):
                with self.assertRaisesRegex(
                    DigestError,
                    "input changed while measuring",
                ):
                    render_digests.canonical_pcm_digest_metadata(
                        audio_path,
                        expected_sample_count=SOURCE_SAMPLE_COUNT,
                    )

            runtime_path = root / "runtime-tool"
            runtime_bytes = b"#!/bin/sh\nexit 0\n"
            runtime_path.write_bytes(runtime_bytes)
            runtime_path.chmod(0o700)
            runtime_identity = _runtime_binary_identity(
                runtime_path,
                label="test runtime",
            )
            runtime_path.replace(root / "runtime-tool-original")
            runtime_path.write_bytes(runtime_bytes)
            runtime_path.chmod(0o700)
            with self.assertRaisesRegex(
                RenderArtifactError,
                "changed during composition",
            ):
                _require_stable_runtime_binary(
                    runtime_path,
                    runtime_identity,
                    label="test runtime",
                )

    def test_pinned_runtime_and_candidate_publication_resist_path_swaps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_parent = root / "runtime-bin"
            runtime_parent.mkdir()
            runtime_path = runtime_parent / "ffmpeg"
            runtime_bytes = (
                b"#!/bin/sh\n"
                b"printf 'ffmpeg version pinned-original\\n'\n"
            )
            runtime_path.write_bytes(runtime_bytes)
            runtime_path.chmod(0o700)
            expected_runtime_digest = sha256(runtime_bytes).hexdigest()

            with _PinnedRuntimeBinary(
                runtime_path,
                label="test FFmpeg",
            ) as pinned_runtime:
                original_parent = root / "runtime-bin-original"
                runtime_parent.replace(original_parent)
                runtime_parent.mkdir()
                replacement_path = runtime_parent / "ffmpeg"
                replacement_path.write_bytes(
                    b"#!/bin/sh\nprintf 'replacement-runtime\\n'\n"
                )
                replacement_path.chmod(0o700)
                observed_identity = pinned_runtime.version_identity()
                self.assertIn("pinned-original", observed_identity)
                self.assertNotIn("replacement-runtime", observed_identity)
                self.assertIn(
                    f"sha256:{expected_runtime_digest}",
                    observed_identity,
                )
                shutil.rmtree(runtime_parent)
                original_parent.replace(runtime_parent)
                pinned_runtime.require_stable()

            artifact_root = root / "artifacts"
            artifact_root.mkdir()
            candidate_root = root / "candidate-work"
            candidate_root.mkdir()
            candidate = candidate_root / "candidate.mp4"
            candidate_bytes = b"deterministic-candidate-bytes"
            candidate.write_bytes(candidate_bytes)
            expected_file_digest = (
                "sha256:" + sha256(candidate_bytes).hexdigest()
            )
            output_directory = artifact_root / "scope" / "composition"
            output_name = "preview-test.mp4"
            output_path = output_directory / output_name

            with _PinnedRegularFile(
                candidate,
                label="test timeline candidate",
            ) as pinned_candidate:
                original_candidate = candidate_root / "candidate-original.mp4"
                candidate.replace(original_candidate)
                candidate.write_bytes(b"poisoned-candidate-bytes")
                with self.assertRaisesRegex(
                    RenderArtifactError,
                    "changed while pinned",
                ):
                    _publish_timeline_output_v1(
                        root=artifact_root,
                        directory=output_directory,
                        source=pinned_candidate,
                        expected_file_digest=expected_file_digest,
                        output_name=output_name,
                    )
                self.assertFalse(output_path.exists())

            candidate.replace(candidate_root / "candidate-poison.mp4")
            original_candidate.replace(candidate)
            with _PinnedRegularFile(
                candidate,
                label="test restored timeline candidate",
            ) as pinned_candidate:
                destination = _publish_timeline_output_v1(
                    root=artifact_root,
                    directory=output_directory,
                    source=pinned_candidate,
                    expected_file_digest=expected_file_digest,
                    output_name=output_name,
                )
                self.assertEqual(destination.read_bytes(), candidate_bytes)
                first_mtime = destination.stat().st_mtime_ns
                replay = _publish_timeline_output_v1(
                    root=artifact_root,
                    directory=output_directory,
                    source=pinned_candidate,
                    expected_file_digest=expected_file_digest,
                    output_name=output_name,
                )
                self.assertEqual(replay.read_bytes(), candidate_bytes)
                self.assertEqual(replay.stat().st_mtime_ns, first_mtime)

                symlink_name = "preview-symlink.mp4"
                (output_directory / symlink_name).symlink_to(output_path)
                with self.assertRaises(RenderArtifactError):
                    _publish_timeline_output_v1(
                        root=artifact_root,
                        directory=output_directory,
                        source=pinned_candidate,
                        expected_file_digest=expected_file_digest,
                        output_name=symlink_name,
                    )
                self.assertTrue(
                    (output_directory / symlink_name).is_symlink()
                )


if __name__ == "__main__":
    unittest.main()
