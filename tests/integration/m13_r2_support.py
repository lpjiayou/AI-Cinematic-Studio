"""Test-only builders for the M13-R2 complete CPU backend acceptance.

The fixture is deliberately project-neutral and uses only local deterministic
media.  It calls the real V5/V4/V3 boundaries; none of the helpers below
replace production validation, rendering, persistence, or restoration logic.
"""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import subprocess
from typing import Any, Mapping
from unittest.mock import patch

from services.v3_render_core.digests import file_sha256, image_digest_metadata
from services.v4_platform import probe_media
from services.v4_platform.render_candidate import V4RenderCandidateExecutor
from services.v5_core_os.episode_production.evidence import EvidenceRecord
from services.v5_core_os.episode_production.foundation import (
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
)
from services.v5_core_os.episode_production.glyph_reveal_v2 import (
    DigestPinnedBasePlateGlyphInspectionAdapter,
    build_glyph_reveal_requirement_v2,
)
from services.v5_core_os.episode_production.timeline_editing import (
    build_mask_binding,
    build_speed_spec,
    build_transform_spec,
    build_transition_spec,
)
from tests.contract.test_m13_glyph_reveal_contract import (
    base_plate_asset,
    composite_params,
    mask_assets,
)
from tests.contract.test_m13_glyph_reveal_v2_contract import (
    InMemoryInspectionEvidenceStore,
    inspection_evidence_v2,
)
from tests.contract.test_m13_timeline_editing_contract import clip_command
import tests.contract.test_m12_audio_authority_contract as audio_authority_fixture
import tests.contract.test_m12_audio_contract as audio_contract_fixture
import tests.contract.test_m12_audio_timing_contract as audio_timing_fixture
import tests.integration.test_m12_m13_minimal_preview as minimal_preview_fixture
import tests.integration.test_m13_e3_timeline_v3_preview as e3_fixture
from tests.integration.m13_e3_support import (
    CREATED_AT,
    CurrentRealMediaAuthority,
    admit_canonical_font,
    canonical_mark_asset,
)
from tests.integration.test_m12_m13_minimal_preview import _TypedInputs
from tests.integration.test_m13_e1_timeline_v3_preview import (
    _sealed,
    _seed_real_video_ready,
)
from tests.integration.test_m13_glyph_reveal_composition import (
    _write_small_gray_png,
)
from tests.integration.test_m13_e2_timeline_v3_preview import _append_e2_profile
from tests.integration.test_m13_e3_timeline_v3_preview import (
    _face_command,
    _nameplate_command,
    _service,
)
from tests.integration.test_m13_e4_timeline_v3_preview import (
    E4_EFFECT_ORDER,
    _distance_state_command,
)
from tests.integration.test_m13_r1a_composition_render_manifest import _toolchain


WORKSPACE = "workspace-generic-r2"
PROJECT = "project-generic-r2"
SERIES = "series-generic-r2"
EPISODE = "episode-generic-r2"
RUN = "run-generic-r2"
SHOT = "shot-generic-r2"
CHARACTER = "character-generic-r2"
SCRIPT = "script-generic-r2"
SCRIPT_VERSION = "script-version-generic-r2"
SCRIPT_TEXT = "R2"
SCRIPT_VERSION_DIGEST = _digest(
    {"scriptVersionRef": SCRIPT_VERSION, "title": SCRIPT_TEXT}
)
FRAME_RATE = 24
SAMPLE_RATE = 48_000
FIXTURE_LABELS = (
    "TECHNICAL_FIXTURE_ONLY",
    "NOT_LIVE_K2",
    "NOT_ADMITTED",
    "NOT_SELECTED",
    "NOT_MASTER",
    "NOT_EXPORT",
)


def resealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def _audio_patch_stack() -> ExitStack:
    stack = ExitStack()
    replacements = (
        (audio_contract_fixture, "WORKSPACE", WORKSPACE),
        (audio_contract_fixture, "PROJECT", PROJECT),
        (audio_contract_fixture, "SERIES", SERIES),
        (audio_contract_fixture, "RUN", RUN),
        (audio_authority_fixture, "WORKSPACE", WORKSPACE),
        (audio_authority_fixture, "PROJECT", PROJECT),
        (audio_authority_fixture, "SERIES", SERIES),
        (audio_authority_fixture, "RUN", RUN),
        (audio_authority_fixture, "EPISODE", EPISODE),
        (audio_timing_fixture, "WORKSPACE", WORKSPACE),
        (audio_timing_fixture, "PROJECT", PROJECT),
        (audio_timing_fixture, "SERIES", SERIES),
        (audio_timing_fixture, "RUN", RUN),
        (audio_timing_fixture, "EPISODE", EPISODE),
        (audio_timing_fixture, "SCRIPT_VERSION_REF", SCRIPT_VERSION),
        (
            audio_timing_fixture,
            "SCRIPT_VERSION_DIGEST",
            SCRIPT_VERSION_DIGEST,
        ),
        (minimal_preview_fixture, "SCRIPT_VERSION_REF", SCRIPT_VERSION),
        (
            minimal_preview_fixture,
            "SCRIPT_VERSION_DIGEST",
            SCRIPT_VERSION_DIGEST,
        ),
    )
    for module, name, value in replacements:
        stack.enter_context(patch.object(module, name, value))
    return stack


def _write_base_video(
    path: Path, frame_count: int, width: int, height: int
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            (
                f"testsrc2=size={width}x{height}:rate={FRAME_RATE}"
                if (width, height) == (64, 64)
                else f"color=c=0x485868:size={width}x{height}:rate={FRAME_RATE}"
            ),
            "-frames:v",
            str(frame_count),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "0",
            "-pix_fmt",
            "yuv420p",
            "-threads:v",
            "1",
            "-x264-params",
            (
                "threads=1:lookahead_threads=1:sliced_threads=0:"
                "sync-lookahead=0:rc-lookahead=0:scenecut=0"
            ),
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-metadata",
            "creation_time=1970-01-01T00:00:00Z",
            "-y",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )


def _generic_glyph_inputs(
    root: Path, frame_count: int, width: int, height: int
) -> dict[str, Any]:
    storage_key = "technical-fixtures/generic-r2/base.mp4"
    base_path = root / storage_key
    _write_base_video(base_path, frame_count, width, height)
    base = base_plate_asset(
        sha256=file_sha256(base_path),
        byte_size=base_path.stat().st_size,
        storage_key=storage_key,
    )
    base.update(
        {
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "assetRef": "video-asset-generic-r2",
            "assetVersionRef": "video-asset-version-generic-r2-v1",
            "ordinal": 1,
            "creativeShotRef": SHOT,
            "creativeShotVersionRef": "creative-shot-version-generic-r2-v1",
            "generationRequestRef": "video-request-generic-r2",
            "generationRequestVersionRef": "video-request-version-generic-r2-v1",
            "sourceImageAssetVersionRef": "image-asset-version-generic-r2-v1",
            "sourceCandidateRef": "video-candidate-generic-r2-v1",
            "revisionRef": "video-revision-generic-r2-v1",
            "sourceRuntimeCandidateRef": "runtime-candidate-generic-r2-v1",
            "semanticVisualQcRef": "visual-qc-generic-r2-v1",
            "humanSelectionRef": "technical-selection-generic-r2-v1",
            "supersedesAssetVersionRef": "video-asset-version-generic-r2-v0",
            "artifactRef": "video-artifact-generic-r2-v1",
            "probe": probe_media(base_path),
        }
    )
    base = resealed(base)

    templates = mask_assets(storage_prefix="technical-fixtures/generic-r2/masks")
    masks: list[dict[str, Any]] = []
    for ordinal, template in enumerate(templates, start=1):
        mask_path = root / f"technical-fixtures/generic-r2/masks/mask-{ordinal:02d}.png"
        _write_small_gray_png(mask_path, set(range(ordinal)))
        measured = image_digest_metadata(mask_path)
        template.update(
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": RUN,
                "assetVersionRef": f"mask-asset-version-generic-r2-{ordinal:02d}",
                "storageKey": str(mask_path.relative_to(root)),
                "byteSize": mask_path.stat().st_size,
                "sha256": file_sha256(mask_path),
                "pixelDigest": measured["pixel_digest"],
                "pixelDigestSpec": measured["pixel_digest_spec"],
                "pixelMode": measured["pixel_mode"],
                "width": measured["width"],
                "height": measured["height"],
                "glyphSlug": "generic-mark",
            }
        )
        masks.append(resealed(template))

    inspection = inspection_evidence_v2(
        base,
        target_shot_ref=SHOT,
        media_probe={
            "width": width,
            "height": height,
            "frameCount": frame_count,
            "frameRate": FRAME_RATE,
        },
    )
    inspection.update(
        {
            "inspectionRef": "inspection-generic-r2-v1",
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "targetShotRef": SHOT,
            "evidenceRef": "inspection-evidence-generic-r2-v1",
            "evidenceDigest": "sha256:"
            + sha256(
                b"generic R2 full-frame no-readable-glyph evidence\n"
            ).hexdigest(),
        }
    )
    inspection = resealed(inspection)
    adapter = DigestPinnedBasePlateGlyphInspectionAdapter(
        GenericInspectionStore(inspection)
    )
    schedule_bounds = ((12, 13), (13, 15), (15, 18), (18, 22), (22, 26), (26, 30))
    requirement = build_glyph_reveal_requirement_v2(
        {
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "requirementRef": "glyph-requirement-generic-r2-v1",
            "glyphSlug": "generic-mark",
            "targetShotRef": SHOT,
            "frameRangeStartInclusive": 12,
            "frameRangeEndExclusive": 30,
            "revealSchedule": [
                {
                    "revealOrdinal": ordinal,
                    "maskAssetVersionRef": masks[ordinal - 1]["assetVersionRef"],
                    "startFrameInclusive": start,
                    "endFrameExclusive": end,
                }
                for ordinal, (start, end) in enumerate(schedule_bounds, start=1)
            ],
            "basePlateAssetVersionRef": base["assetVersionRef"],
            "basePlateInspectionRef": inspection["inspectionRef"],
            "compositeParams": composite_params(),
        },
        base_plate_asset=base,
        mask_assets=masks,
        inspection_adapter=adapter,
    )
    return {
        "base": base,
        "masks": tuple(masks),
        "inspection": inspection,
        "requirement": requirement,
    }


def _generic_audio_inputs(root: Path) -> dict[str, Any]:
    with _audio_patch_stack():
        dialogue = minimal_preview_fixture._real_dialogue_inputs(root)
        bundle = audio_timing_fixture.explicit_source_assets()
        bundle["sources"]["dialogue"] = dialogue["source"]
        remaining = [
            minimal_preview_fixture._real_non_speech_audio_input(
                root, bundle, role
            )
            for role in ("narration", "sfx", "ambience", "music")
        ]
        sources = [dialogue, *remaining]
        cue_mappings = [
            item["cue"].as_dict()
            if hasattr(item["cue"], "as_dict")
            else item["cueMapping"]
            for item in sources
        ]
        members = [
            audio_timing_fixture.build_stem_member_fixture(
                item["source"],
                role,
                suffix="generic-r2",
                cue=cue_mapping,
                source_end=minimal_preview_fixture.SOURCE_SAMPLE_COUNT,
                stem_start=index * minimal_preview_fixture.SOURCE_SAMPLE_COUNT,
            )
            for index, (role, item, cue_mapping) in enumerate(
                zip(
                    ("dialogue", "narration", "sfx", "ambience", "music"),
                    sources,
                    cue_mappings,
                    strict=True,
                )
            )
        ]
        stem_mapping = audio_timing_fixture.build_stem_set_fixture(
            bundle,
            members,
            suffix="generic-r2",
            cues=cue_mappings,
            duration=5 * minimal_preview_fixture.SOURCE_SAMPLE_COUNT,
        )
        stem_set = audio_timing_fixture.validate_stem_set_fixture(
            bundle,
            stem_mapping,
            cues=cue_mappings,
        )
    return {
        **dialogue,
        "sourceBundle": bundle,
        "sources": tuple(sources),
        "bindings": tuple(item["binding"] for item in sources),
        "cues": tuple(item["cue"] for item in sources),
        "members": tuple(members),
        "stemSet": stem_set,
    }


def generic_inputs(
    root: Path, frame_count: int, width: int, height: int
) -> _TypedInputs:
    glyph = _generic_glyph_inputs(root, frame_count, width, height)
    audio = _generic_audio_inputs(root)
    run = resealed(
        {
            "schemaVersion": "test.m13-r2-generic-run.v1",
            "workspaceRef": WORKSPACE,
            "projectRef": PROJECT,
            "seriesRef": SERIES,
            "episodeRef": EPISODE,
            "productionRunRef": RUN,
            "version": 1,
            "state": "MEDIA_READY",
            "scriptVersionRef": SCRIPT_VERSION,
            "upstreamSnapshot": {
                "script": {
                    "scriptRef": SCRIPT,
                    "scriptVersionRef": SCRIPT_VERSION,
                    "versionDigest": SCRIPT_VERSION_DIGEST,
                }
            },
        }
    )
    return _TypedInputs(
        audio=audio,
        base=glyph["base"],
        masks=glyph["masks"],
        inspection=glyph["inspection"],
        requirement=glyph["requirement"],
        run=run,
    )


def generic_authority(
    inputs: _TypedInputs, frame_count: int, width: int, height: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run = deepcopy(inputs.run)
    storyboard = resealed(
        {
            "schemaVersion": "test.m13-r2-generic-storyboard.v1",
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "rootPayloadDigest": run["payloadDigest"],
            "storyboardVersionRef": "storyboard-version-generic-r2-v1",
            "scriptVersionRef": SCRIPT_VERSION,
            "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
        }
    )
    graph = resealed(
        {
            "schemaVersion": "test.m13-r2-generic-shot-graph.v1",
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "rootPayloadDigest": run["payloadDigest"],
            "executableShotGraphVersionRef": "shot-graph-version-generic-r2-v1",
            "scriptVersionRef": SCRIPT_VERSION,
            "scriptVersionDigest": SCRIPT_VERSION_DIGEST,
            "storyboardDigest": storyboard["payloadDigest"],
            "shots": [
                {
                    "schemaVersion": "test.m13-r2-generic-creative-shot.v1",
                    "creativeShotRef": SHOT,
                    "creativeShotVersionRef": inputs.base["creativeShotVersionRef"],
                    "payloadDigest": inputs.base["creativeShotDigest"],
                    "requiredCharacterIdentityLocks": [
                        {
                            "characterRef": CHARACTER,
                            "identityLockRef": "identity-lock-generic-r2",
                            "identityLockVersionRef": "identity-lock-version-generic-r2-v1",
                            "identityLockDigest": "1" * 64,
                        }
                    ],
                }
            ],
            "output": {
                "width": width,
                "height": height,
                "frameRate": FRAME_RATE,
                "totalFrames": frame_count,
            },
        }
    )
    return run, storyboard, graph


class GenericScriptTextReader:
    def __init__(self, run: Mapping[str, Any]) -> None:
        self.run = deepcopy(dict(run))

    def get_workspace(self, workspace_ref: str, series_ref: str, episode_ref: str):
        if (workspace_ref, series_ref, episode_ref) != (
            WORKSPACE,
            SERIES,
            EPISODE,
        ):
            raise StaleInputError("generic script authority scope drifted")
        return {
            "script": {
                "scriptRef": SCRIPT,
                "confirmedScriptVersionRef": SCRIPT_VERSION,
            },
            "versions": [
                {"scriptVersionRef": SCRIPT_VERSION, "title": SCRIPT_TEXT}
            ],
        }


class GenericIdentityProjectionReader:
    def require_current_identity_reference_projection(
        self, workspace_ref: str, production_run_ref: str, character_ref: str
    ) -> dict[str, Any]:
        if (workspace_ref, production_run_ref, character_ref) != (
            WORKSPACE,
            RUN,
            CHARACTER,
        ):
            raise StaleInputError("generic identity authority scope drifted")
        decision = {
            "referenceRef": "identity-reference-generic-r2",
            "referenceVersionRef": "identity-reference-version-generic-r2-v1",
            "contentDigest": sha256(b"generic-r2-local-reference").hexdigest(),
            "mediaType": "image",
            "rightsState": "LOCAL_EVIDENCE_ONLY",
            "provenance": "LOCAL_EVIDENCE",
            "approvalRef": "local-evidence-approval-generic-r2",
        }
        base = {
            "schemaVersion": "v5.identity-reference-version-projection.v1",
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "characterRef": CHARACTER,
            "scriptCharacterName": "Generic R2",
            "identityLockRef": "identity-lock-generic-r2",
            "identityLockVersionRef": "identity-lock-version-generic-r2-v1",
            "identityLockDigest": "1" * 64,
            **decision,
            "externalDecisionDigest": _digest(decision),
        }
        return {
            **base,
            "projectionCheckedAt": CREATED_AT,
            "projectionDigest": _digest(base),
        }


class GenericInspectionStore:
    def __init__(self, inspection: Mapping[str, Any]) -> None:
        self.inspection = deepcopy(dict(inspection))
        self.support = b"generic R2 full-frame no-readable-glyph evidence\n"

    def read_inspection(self, **_kwargs):
        return deepcopy(self.inspection)

    def read_evidence_bytes(self, *, evidence_ref: str):
        if evidence_ref != self.inspection["evidenceRef"]:
            return None
        return self.support


def register_inputs(service, inputs: _TypedInputs) -> dict[str, Any]:
    return service.record_m12_m13_inputs(
        workspace_ref=WORKSPACE,
        production_run_ref=RUN,
        idempotency_key="m13-r2-generic-inputs",
        audio_input_bindings=inputs.audio["bindings"],
        audio_cues=inputs.audio["cues"],
        audio_stem_set=inputs.audio["stemSet"],
        glyph_reveal_requirement=inputs.requirement,
        mask_assets=inputs.masks,
    )


def _edit(service, parent: dict[str, Any], slug: str, operation: str, arguments: dict):
    timeline = parent["timelineVersion"] if "timelineVersion" in parent else parent
    return service.edit_timeline(
        {
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "operationRef": f"m13-r2-{slug}",
            "idempotencyKey": f"m13-r2-{slug}-key",
            "expectedRunVersion": 1,
            "parentTimelineVersionRef": timeline["timelineVersionRef"],
            "parentTimelineVersionDigest": timeline["payloadDigest"],
            "editCommand": {"operation": operation, "arguments": deepcopy(arguments)},
        }
    )


def build_complete_timeline(
    service,
    inputs: _TypedInputs,
    chains: list[Any],
    frame_count: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    created = service.create_timeline(
        {
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "operationRef": "m13-r2-create-timeline",
            "idempotencyKey": "m13-r2-create-timeline-key",
            "expectedRunVersion": 1,
        }
    )
    tracks = {item["trackKind"]: item["trackRef"] for item in created["tracks"]}
    video_ref = "clip-generic-r2-01-video"
    video = clip_command("VIDEO", clip_ref=video_ref)
    video.pop("timelineVersionRef")
    video.update(
        {
            "trackRef": tracks["VIDEO"],
            "timelineStartFrameInclusive": 0,
            "timelineEndFrameExclusive": frame_count,
            "sourceBinding": {
                "assetVersionRef": inputs.base["assetVersionRef"],
                "assetVersionDigest": inputs.base["payloadDigest"],
                "sourceInFrameInclusive": 0,
                "sourceOutFrameExclusive": frame_count,
            },
        }
    )
    current = _edit(service, created["timelineVersion"], "insert-video", "INSERT_CLIP", {"clip": video})

    role_order = ("dialogue", "narration", "sfx", "ambience", "music")
    bindings = {
        role: item.as_dict()
        for role, item in zip(role_order, inputs.audio["bindings"], strict=True)
    }
    members = {item["stemRole"]: item for item in inputs.audio["members"]}
    for ordinal, role in enumerate(role_order, start=1):
        binding = bindings[role]
        audio = clip_command(
            "AUDIO", clip_ref=f"clip-generic-r2-{ordinal + 1:02d}-audio-{role}"
        )
        audio.pop("timelineVersionRef")
        audio["trackRef"] = tracks["AUDIO"]
        audio["timelineStartFrameInclusive"] = (ordinal - 1) * FRAME_RATE
        audio["timelineEndFrameExclusive"] = ordinal * FRAME_RATE
        audio["sourceBinding"].update(
            {
                "audioAssetVersionRef": binding["assetVersionRef"],
                "audioAssetVersionDigest": binding["assetVersionDigest"],
                "stemMemberRef": members[role]["stemMemberRef"],
            }
        )
        current = _edit(service, current, f"insert-audio-{ordinal}", "INSERT_CLIP", {"clip": audio})

    cue = inputs.audio["cues"][0].as_dict()
    subtitle = clip_command("SUBTITLE", clip_ref="clip-generic-r2-07-subtitle")
    subtitle.pop("timelineVersionRef")
    subtitle["trackRef"] = tracks["SUBTITLE"]
    subtitle["sourceBinding"] = {
        "audioCueRef": cue["cueVersionRef"],
        "audioCueDigest": cue["payloadDigest"],
        "scriptVersionRef": cue["scriptVersionRef"],
        "scriptVersionDigest": cue["scriptVersionDigest"],
        "textStart": cue["subtitleTimingReference"]["textRangeStart"],
        "textEndExclusive": cue["subtitleTimingReference"]["textRangeEndExclusive"],
        "textDigest": cue["subtitleTimingReference"]["textDigest"],
        "language": cue["subtitleTimingReference"]["language"],
        "wordTiming": [
            {
                "wordRef": word["wordRef"],
                "textStart": word["textRangeStart"],
                "textEndExclusive": word["textRangeEndExclusive"],
                "timelineStartFrameInclusive": word["sourceStartSample"] * FRAME_RATE // SAMPLE_RATE,
                "timelineEndFrameExclusive": word["sourceEndSample"] * FRAME_RATE // SAMPLE_RATE,
                "textDigest": word["textDigest"],
            }
            for word in cue["wordTimings"]
        ],
    }
    current = _edit(service, current, "insert-subtitle", "INSERT_CLIP", {"clip": subtitle})

    glyph = clip_command("EFFECT", clip_ref="clip-generic-r2-08-effect-glyph")
    glyph.pop("timelineVersionRef")
    glyph.update(
        {
            "trackRef": tracks["EFFECT"],
            "timelineStartFrameInclusive": 12,
            "timelineEndFrameExclusive": 30,
            "sourceBinding": {
                "effectRequirementRef": inputs.requirement.requirement_ref,
                "effectRequirementDigest": inputs.requirement.payload_digest,
                "effectKind": "GLYPH_REVEAL",
                "effectResultRef": None,
                "layer": 1,
                "blendMode": "GRAZING_LIGHT_RELIEF",
            },
        }
    )
    current = _edit(service, current, "insert-effect-glyph", "INSERT_CLIP", {"clip": glyph})

    for ordinal, chain in enumerate(chains, start=2):
        if hasattr(chain, "requirement"):
            requirement = chain.requirement.as_dict()
            result = chain.result.as_dict()
        else:
            requirement = chain["requirement"]
            result = chain["result"]
        effect = clip_command(
            "EFFECT", clip_ref=f"clip-generic-r2-{ordinal + 7:02d}-effect"
        )
        effect.pop("timelineVersionRef")
        effect.update(
            {
                "trackRef": tracks["EFFECT"],
                "timelineStartFrameInclusive": requirement["frameRangeStartInclusive"],
                "timelineEndFrameExclusive": requirement["frameRangeEndExclusive"],
                "layer": requirement["layer"],
                "zOrder": requirement["layer"],
                "blendMode": requirement["blendMode"],
                "sourceBinding": {
                    "effectRequirementRef": requirement["requirementRef"],
                    "effectRequirementDigest": requirement["payloadDigest"],
                    "effectKind": requirement["effectMode"],
                    "effectResultRef": None,
                    "effectResultDigest": None,
                    "layer": requirement["layer"],
                    "blendMode": requirement["blendMode"],
                },
            }
        )
        current = _edit(service, current, f"insert-effect-{ordinal}", "INSERT_CLIP", {"clip": effect})
        current = _edit(
            service,
            current,
            f"bind-effect-{ordinal}",
            "BIND_EFFECT_RESULT",
            {
                "clipRef": effect["clipRef"],
                "effectResultRef": result["resultRef"],
                "effectResultDigest": result["payloadDigest"],
            },
        )

    # Preview authority deliberately seals the complete four-track/eight-effect
    # layout before video modifiers are applied.  The editing Preview contract
    # rejects modifiers that it cannot project losslessly; RenderCandidate is
    # the production path that accepts and executes those closed modifiers.
    preview_timeline = current["timelineVersion"]
    preview = service.compose_and_qc(
        {
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "operationRef": "m13-r2-preview-baseline",
            "idempotencyKey": "m13-r2-preview-baseline-key",
            "expectedRunVersion": 1,
            "expectedEvidenceRevision": current["evidenceRevision"],
            "timelineVersionRef": preview_timeline["timelineVersionRef"],
            "timelineVersionDigest": preview_timeline["payloadDigest"],
        }
    )

    split = frame_count // 2
    # SPLIT_CLIP appends the right successor.  Keep its ref after every
    # existing clip so append order and journal restore order are identical.
    right_ref = "zz-clip-generic-r2-video-right"
    current = _edit(service, current, "split-video", "SPLIT_CLIP", {"clipRef": video_ref, "splitTimelineFrame": split, "rightClipRef": right_ref})
    right = next(item for item in current["clips"] if item["clipRef"] == right_ref)
    trimmed_source = deepcopy(right["sourceBinding"])
    trimmed_source["sourceOutFrameExclusive"] = frame_count - 8
    moved_start = split + 4
    moved_end = frame_count - 4
    sped_end = moved_start + (frame_count - 8 - split) // 2
    current = _edit(
        service,
        current,
        "trim-video",
        "TRIM_CLIP",
        {
            "clipRef": right_ref,
            "timelineStartFrameInclusive": split,
            "timelineEndFrameExclusive": frame_count - 8,
            "sourceBinding": trimmed_source,
        },
    )
    current = _edit(
        service,
        current,
        "move-video",
        "MOVE_CLIP",
        {
            "clipRef": right_ref,
            "trackRef": tracks["VIDEO"],
            "timelineStartFrameInclusive": moved_start,
            "timelineEndFrameExclusive": moved_end,
        },
    )
    current = _edit(service, current, "speed-video", "SET_SPEED", {"clipRef": right_ref, "speed": build_speed_spec({"numerator": 2, "denominator": 1})})
    transition = build_transition_spec(
        {
            "transitionKind": "CROSSFADE",
            "durationFrames": 4,
            "curve": "LINEAR",
            "alignment": "CENTER",
        }
    )
    current = _edit(service, current, "transition-out", "SET_TRANSITION", {"clipRef": video_ref, "edge": "OUT", "transition": transition})
    current = _edit(service, current, "transition-in", "SET_TRANSITION", {"clipRef": right_ref, "edge": "IN", "transition": transition})
    current = _edit(
        service,
        current,
        "transform-video",
        "SET_TRANSFORM",
        {
            "clipRef": right_ref,
            "transform": build_transform_spec(
                {
                    "positionXPixels": 2,
                    "positionYPixels": -2,
                    "scaleX": {"numerator": 3, "denominator": 4},
                    "scaleY": {"numerator": 3, "denominator": 4},
                    "rotationMilliDegrees": 0,
                    "anchorXPixels": 0,
                    "anchorYPixels": 0,
                    "opacity": 875,
                    "perspectiveMode": "NONE",
                    "perspectiveMatrix": None,
                    "perspectiveCorners": None,
                }
            ),
        },
    )
    current = _edit(
        service,
        current,
        "mask-video",
        "SET_MASKS",
        {
            "clipRef": right_ref,
            "maskBindings": [
                build_mask_binding(
                    {
                        "maskAssetVersionRef": inputs.masks[0]["assetVersionRef"],
                        "maskAssetVersionDigest": inputs.masks[0]["payloadDigest"],
                        "mode": "ALPHA",
                        "frameRangeStartInclusive": moved_start,
                        "frameRangeEndExclusive": sped_end,
                        "transform": build_transform_spec(
                            {
                                "positionXPixels": 0,
                                "positionYPixels": 0,
                                "scaleX": {"numerator": 1, "denominator": 1},
                                "scaleY": {"numerator": 1, "denominator": 1},
                                "rotationMilliDegrees": 0,
                                "anchorXPixels": 0,
                                "anchorYPixels": 0,
                                "opacity": 1000,
                                "perspectiveMode": "NONE",
                                "perspectiveMatrix": None,
                                "perspectiveCorners": None,
                            }
                        ),
                    }
                )
            ],
        },
    )
    # R1 RenderManifest accepts the seven effect-mask authorities but does not
    # accept a residual VIDEO mask binding.  Preserve the SET_MASKS successor
    # in immutable history, then close the final renderable successor by
    # explicitly clearing only that clip-level modifier.
    current = _edit(
        service,
        current,
        "clear-video-mask",
        "SET_MASKS",
        {"clipRef": right_ref, "maskBindings": []},
    )
    return current, preview


@dataclass
class R2Stack:
    artifact_root: Path
    evidence_path: Path
    repository: Any
    service: Any
    composition: Any
    inputs: _TypedInputs
    run: dict[str, Any]
    graph: dict[str, Any]
    mark: dict[str, Any]
    font_fixture: Any
    toolchain: dict[str, str]
    timeline: dict[str, Any]
    preview: dict[str, Any]


def build_stack(
    root: Path,
    frame_count: int,
    *,
    width: int = 64,
    height: int = 64,
) -> R2Stack:
    artifact_root = root / "artifacts"
    evidence_path = root / "evidence.sqlite3"
    inputs = generic_inputs(artifact_root, frame_count, width, height)
    run, storyboard, graph = generic_authority(
        inputs, frame_count, width, height
    )
    inputs = _TypedInputs(
        audio=inputs.audio,
        base=inputs.base,
        masks=inputs.masks,
        inspection=inputs.inspection,
        requirement=inputs.requirement,
        run=run,
    )
    repository = minimal_preview_fixture.SqliteEpisodeProductionEvidenceAdapter(
        evidence_path, initialize_if_missing=True
    )
    _seed_real_video_ready(repository, run, storyboard, graph)
    font_fixture = admit_canonical_font(run=run, evidence=repository)
    mark = canonical_mark_asset(run=run, base=inputs.base, source=inputs.masks[4])
    mark = resealed({**mark, "assetVersionRef": "image-mark-version-generic-r2-v1"})
    toolchain = _toolchain()
    service, composition = _service(
        artifact_root=artifact_root,
        repository=repository,
        inputs=inputs,
        run=run,
        graph=graph,
        mark=mark,
        identity_reader=GenericIdentityProjectionReader(),
        script_reader=GenericScriptTextReader(run),
        font_authority=font_fixture.service,
        render_toolchain_identity=toolchain,
    )
    service.glyph_inspection_adapter = (
        DigestPinnedBasePlateGlyphInspectionAdapter(
            GenericInspectionStore(inputs.inspection)
        )
    )
    composition.render_candidate = V4RenderCandidateExecutor(
        artifact_root,
        composition,
        font_asset_authority=font_fixture.service,
    ).execute
    register_inputs(service, inputs)

    smoke_layer = resealed(
        {**inputs.masks[3], "assetVersionRef": "mask-smoke-layer-generic-r2-v1"}
    )
    repository.append_record(
        EvidenceRecord(
            workspaceRef=WORKSPACE,
            productionRunRef=RUN,
            recordKind="MaskAssetVersion",
            recordRef=smoke_layer["assetVersionRef"],
            recordVersion=1,
            idempotencyKey="m13-r2-smoke-layer",
            requestDigest=_digest({"smokeLayer": smoke_layer["payloadDigest"]}),
            createdAt=CREATED_AT,
            payload=smoke_layer,
            payloadDigest=smoke_layer["payloadDigest"],
        )
    )
    e2_chains, _ = _append_e2_profile(
        artifact_root, repository, service, inputs, smoke_layer
    )
    with (
        patch.object(e3_fixture, "SCRIPT_REF", SCRIPT),
        patch.object(e3_fixture, "SCRIPT_VERSION_REF", SCRIPT_VERSION),
        patch.object(e3_fixture, "SCRIPT_VERSION_DIGEST", SCRIPT_VERSION_DIGEST),
        patch.object(e3_fixture, "CHARACTER_REF", CHARACTER),
    ):
        nameplate = service.execute_deterministic_effect(
            _nameplate_command(run, inputs.base, font_fixture.asset)
        )["deterministicEffect"]
        face = service.execute_deterministic_effect(
            _face_command(run, inputs.base, mark)
        )["deterministicEffect"]
    distance = service.execute_deterministic_effect(
        _distance_state_command(run, inputs.base, mark, inputs.masks[4])
    )["deterministicEffect"]
    timeline, preview = build_complete_timeline(
        service,
        inputs,
        [*e2_chains, nameplate, face, distance],
        frame_count,
    )
    return R2Stack(
        artifact_root=artifact_root,
        evidence_path=evidence_path,
        repository=repository,
        service=service,
        composition=composition,
        inputs=inputs,
        run=run,
        graph=graph,
        mark=mark,
        font_fixture=font_fixture,
        toolchain=toolchain,
        timeline=timeline,
        preview=preview,
    )


class FailOneRenderAppend:
    """Fail exactly once at the five-record RenderCandidate journal CAS."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.failed = False

    def append_records(self, records, **kwargs):
        kinds = {item.recordKind for item in records}
        if not self.failed and "RenderCandidate" in kinds:
            self.failed = True
            raise RepositoryUnavailableError(
                "simulated interruption before RenderCandidate journal commit"
            )
        return self.delegate.append_records(records, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


def candidate_command(manifest_result: dict[str, Any], slug: str) -> dict[str, Any]:
    timeline = manifest_result["timelineVersion"]
    composition = manifest_result["compositionVersion"]
    manifest = manifest_result["renderManifest"]
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
        "operationRef": f"m13-r2-{slug}",
        "idempotencyKey": f"m13-r2-{slug}-key",
        "expectedRunVersion": 1,
        "timelineVersionRef": timeline["timelineVersionRef"],
        "timelineVersionDigest": timeline["payloadDigest"],
        "compositionVersionRef": composition["compositionVersionRef"],
        "compositionVersionDigest": composition["payloadDigest"],
        "renderManifestRef": manifest["renderManifestRef"],
        "renderManifestDigest": manifest["payloadDigest"],
    }


def preview_command(stack: R2Stack, slug: str) -> dict[str, Any]:
    timeline = stack.timeline["timelineVersion"]
    return {
        "workspaceRef": WORKSPACE,
        "productionRunRef": RUN,
        "operationRef": f"m13-r2-preview-{slug}",
        "idempotencyKey": f"m13-r2-preview-{slug}-key",
        "expectedRunVersion": 1,
        "expectedEvidenceRevision": stack.timeline["evidenceRevision"],
        "timelineVersionRef": timeline["timelineVersionRef"],
        "timelineVersionDigest": timeline["payloadDigest"],
    }


def restart_stack(stack: R2Stack):
    from services.v5_core_os.episode_production.evidence import (
        SqliteEpisodeProductionEvidenceAdapter,
    )
    from tests.integration.m13_e3_support import restart_font_authority

    repository = SqliteEpisodeProductionEvidenceAdapter(
        stack.evidence_path, initialize_if_missing=False
    )
    font = restart_font_authority(
        run=stack.run, evidence=repository, fixture=stack.font_fixture
    )
    service, composition = _service(
        artifact_root=stack.artifact_root,
        repository=repository,
        inputs=stack.inputs,
        run=stack.run,
        graph=stack.graph,
        mark=stack.mark,
        identity_reader=GenericIdentityProjectionReader(),
        script_reader=GenericScriptTextReader(stack.run),
        font_authority=font,
        render_toolchain_identity=stack.toolchain,
    )
    service.glyph_inspection_adapter = (
        DigestPinnedBasePlateGlyphInspectionAdapter(
            GenericInspectionStore(stack.inputs.inspection)
        )
    )
    composition.render_candidate = V4RenderCandidateExecutor(
        stack.artifact_root,
        composition,
        font_asset_authority=font,
    ).execute
    return service, composition, repository


__all__ = [
    "E4_EFFECT_ORDER",
    "FIXTURE_LABELS",
    "FailOneRenderAppend",
    "RUN",
    "WORKSPACE",
    "build_stack",
    "candidate_command",
    "preview_command",
    "restart_stack",
]
