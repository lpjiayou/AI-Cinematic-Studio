from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from services.v4_platform import MediaJobCoordinator, SqliteMediaJobAdapter
from services.v5_core_os.episode_production import (
    AUDIO_REQUIREMENT_ROUTE_RECORD_KIND,
    DEFAULT_VALIDATION_PROFILE_REF,
    EXECUTION_CLASSES,
    EpisodeProductionPublicError,
    build_voice_asset_version,
    create_local_development_boundary,
)
from services.v5_core_os.episode_production.evidence import EvidenceRecord
from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.media_candidate_review import (
    ASSET_ADMISSION,
    ASSET_VERSION,
    CANDIDATE,
    HUMAN_SELECTION,
    SEMANTIC_VISUAL_QC,
    TECHNICAL_VALIDATION,
    VISUAL_QC_PROFILE,
    VISUAL_QC_PROFILE_DIGEST,
)
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.series_intelligence import M6Scope, VerifiedApproval
from services.v5_core_os.series_intelligence.errors import AuthorityUnavailableError
from tests.contract.test_m12_audio_authority_contract import (
    rights_binding,
    voice_asset_command,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_series_planning_m5 import valid_candidate


FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "generic_upstream_method_closure.json"
)


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class GenericRefs:
    def __init__(self, fixture: dict):
        self.counts: dict[str, int] = {}
        self.fixed = {
            "project": fixture["projectRef"],
            "series": fixture["seriesRef"],
            "episode": fixture["episodeRef"],
        }

    def __call__(self, prefix: str) -> str:
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        if prefix in self.fixed and self.counts[prefix] == 1:
            return self.fixed[prefix]
        return f"{prefix}-generic-upstream-{self.counts[prefix]}"


class GenericScopeAuthority:
    def resolve_scope(
        self, workspace_ref: str, project_ref: str, series_ref: str
    ) -> M6Scope:
        return M6Scope(
            "series-production",
            f"tenant-{workspace_ref}",
            workspace_ref,
            project_ref,
            series_ref,
        )


class GenericApprovalAuthority:
    def verify_approval(self, *, scope, approval_ref, action) -> VerifiedApproval:
        del scope, action
        if approval_ref != "approval-generic-human":
            raise AuthorityUnavailableError()
        return VerifiedApproval(
            approval_ref, "actor-generic-owner", "human"
        )


class NoCallVideoAdapter:
    adapter_identity = "v4.comfyui-wan22-image-to-video.v1"
    provenance = "SELF_HOSTED_AI_GENERATED"

    def __init__(self) -> None:
        self.generate_calls = 0

    def generate(self, request, candidate_path):
        del request, candidate_path
        self.generate_calls += 1
        raise AssertionError("the generic acceptance fixture must not execute video")


def sqlite_tables(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        connection.close()


def operation_context(fixture: dict, operation: str) -> dict:
    return {
        "workspaceRef": fixture["workspaceRef"],
        "projectRef": fixture["projectRef"],
        "seriesRef": fixture["seriesRef"],
        "operationRef": operation,
        "idempotencyKey": operation,
    }


def activate_generic_baseline(assembly: LifecycleAssembly, fixture: dict) -> dict:
    context = operation_context(fixture, "generic-baseline")
    bible = assembly.series_intelligence.create_bible_version(
        {
            **context,
            "operationRef": "generic-bible-create",
            "idempotencyKey": "generic-bible-create",
            "candidate": True,
            "content": deepcopy(fixture["seriesBibleContent"]),
        }
    )
    bible = assembly.series_intelligence.confirm_bible_version(
        {
            **context,
            "operationRef": "generic-bible-confirm",
            "idempotencyKey": "generic-bible-confirm",
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "expectedRevision": bible["root"]["revision"],
            "approvalRef": "approval-generic-human",
        }
    )
    source = assembly.series_planning.get_confirmed_m6_source_snapshot(
        fixture["workspaceRef"], fixture["projectRef"], fixture["seriesRef"]
    )
    episode_item_ref = source["episodePlanItems"][0]["episodePlanItemRef"]
    character_refs = [item["characterRef"] for item in fixture["characters"]]
    character_content = {
        "characters": deepcopy(fixture["characters"]),
        "stateIntervals": [
            {
                "intervalRef": f"interval-{character_ref}-location",
                "characterRef": character_ref,
                "category": "Location",
                "startEpisodePlanItemRef": episode_item_ref,
                "endEpisodePlanItemRef": None,
                "valueRef": "location-relay-garden",
            }
            for character_ref in character_refs
        ],
        "relationships": [
            {
                "relationshipRef": "relationship-ari-mina",
                "fromCharacterRef": "character-ari",
                "toCharacterRef": "character-mina",
                "relationshipType": "field-partners",
                "startEpisodePlanItemRef": episode_item_ref,
                "endEpisodePlanItemRef": None,
            }
        ],
        "identityBindings": [],
    }
    characters = assembly.series_intelligence.create_character_version(
        {
            **context,
            "operationRef": "generic-character-create",
            "idempotencyKey": "generic-character-create",
            "candidate": True,
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "content": character_content,
        }
    )
    characters = assembly.series_intelligence.confirm_character_version(
        {
            **context,
            "operationRef": "generic-character-confirm",
            "idempotencyKey": "generic-character-confirm",
            "characterContinuityRef": characters["root"][
                "characterContinuityRef"
            ],
            "characterContinuityVersionRef": characters["version"][
                "characterContinuityVersionRef"
            ],
            "expectedRevision": characters["root"]["revision"],
            "approvalRef": "approval-generic-human",
        }
    )
    return assembly.series_intelligence.activate_baseline(
        {
            **context,
            "operationRef": "generic-baseline-activate",
            "idempotencyKey": "generic-baseline-activate",
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": characters["root"][
                "characterContinuityRef"
            ],
            "characterContinuityVersionRef": characters["version"][
                "characterContinuityVersionRef"
            ],
            "expectedActivationRevision": 0,
            "approvalRef": "approval-generic-human",
        }
    )


SCRIPT_CONTENT_FIELDS = (
    "title",
    "logline",
    "synopsis",
    "targetDurationSec",
    "scenes",
)


def seed_generic_roots(assembly: LifecycleAssembly, fixture: dict) -> dict:
    workspace = fixture["workspaceRef"]
    profile = fixture["contentProfileRef"]
    series = assembly.series_episode.create_series(
        {
            "workspaceRef": workspace,
            "contentProfileRef": profile,
            "title": fixture["series"]["title"],
            "description": fixture["series"]["description"],
            "plannedEpisodeCount": 1,
        }
    )
    project = assembly.project_context.create_project(
        {
            "workspaceRef": workspace,
            "contentProfileRef": profile,
            "projectType": "series",
            "seriesRef": series["seriesRef"],
            "title": fixture["project"]["title"],
            "description": fixture["project"]["description"],
            "targetPlatform": "technical-evidence",
            "aspectRatio": "16:9",
            "plannedEpisodeCount": 1,
        }
    )
    director_plan = valid_plan()
    director_plan["storyDirection"]["title"] = fixture["episode"]["title"]
    director_plan["productionPlan"]["characters"] = [
        item["name"] for item in fixture["characters"]
    ]
    brief = valid_brief()
    brief["character"] = "Ari Vale and Mina Sol"
    creative = assembly.series_episode.confirm_creative_plan(
        {
            "workspaceRef": workspace,
            "humanConfirmed": True,
            "sourcePlanRef": "director-plan-generic-upstream",
            "sourcePlanSchemaVersion": director_plan["schemaVersion"],
            "sourcePlanVersion": 1,
            "brief": brief,
            "sourcePlan": director_plan,
        }
    )
    episode = assembly.series_episode.create_episode(
        {
            "workspaceRef": workspace,
            "seriesRef": series["seriesRef"],
            "creativePlanRef": creative["creativePlanRef"],
            "episodeNumber": 1,
            "seasonNumber": 1,
            "volumeNumber": 1,
            "title": fixture["episode"]["title"],
        }
    )
    candidate = valid_candidate(1)
    candidate["seriesConcept"] = "A generic technical relay-recovery series."
    candidate["episodePlanItems"][0]["title"] = fixture["episode"]["title"]
    initial_plan = assembly.series_planning.confirm_candidate(
        {
            "workspaceRef": workspace,
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "humanConfirmed": True,
            "candidate": candidate,
        }
    )
    bound_plan = assembly.series_planning.create_episode_plan_item_binding_version(
        {
            "workspaceRef": workspace,
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "seriesPlanRef": initial_plan["plan"]["seriesPlanRef"],
            "expectedPlanVersion": initial_plan["plan"]["version"],
            "episodePlanItemBindings": [
                {
                    "episodeRef": episode["episodeRef"],
                    "episodePlanItemRef": initial_plan["version"][
                        "episodePlanItems"
                    ][0]["episodePlanItemRef"],
                }
            ],
        }
    )
    assembly.series_planning.confirm_version(
        {
            "workspaceRef": workspace,
            "seriesPlanRef": bound_plan["plan"]["seriesPlanRef"],
            "seriesPlanVersionRef": bound_plan["version"]["seriesPlanVersionRef"],
            "expectedPlanVersion": bound_plan["plan"]["version"],
            "humanConfirmed": True,
        }
    )
    historical = assembly.script_studio.create_version(
        {
            "workspaceRef": workspace,
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "changeKind": "ai-generation",
            "content": deepcopy(fixture["scriptContent"]),
        }
    )
    baseline = activate_generic_baseline(assembly, fixture)
    successor_content = deepcopy(
        {
            field: historical["scriptVersion"][field]
            for field in SCRIPT_CONTENT_FIELDS
        }
    )
    successor_content["scenes"][1]["productionNotes"].append(
        "Bind this version to the active episode baseline."
    )
    bound_script = assembly.script_studio.create_version(
        {
            "workspaceRef": workspace,
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "scriptRef": historical["script"]["scriptRef"],
            "baseScriptVersionRef": historical["scriptVersion"][
                "scriptVersionRef"
            ],
            "changeKind": "manual-edit",
            "content": successor_content,
        }
    )
    assembly.script_studio.confirm_version(
        {
            "workspaceRef": workspace,
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "scriptRef": bound_script["script"]["scriptRef"],
            "scriptVersionRef": bound_script["scriptVersion"][
                "scriptVersionRef"
            ],
            "humanConfirmed": True,
        }
    )
    return {
        "project": project,
        "series": series,
        "episode": episode,
        "historical": historical,
        "boundScript": bound_script,
        "baseline": baseline,
    }


def run_command(fixture: dict) -> dict:
    return {
        "workspaceRef": fixture["workspaceRef"],
        "projectRef": fixture["projectRef"],
        "seriesRef": fixture["seriesRef"],
        "episodeRef": fixture["episodeRef"],
        "idempotencyKey": "generic-upstream-run",
        "shotsPerScene": [1, 1],
    }


def validation_command(fixture: dict, run: dict, *, key: str) -> dict:
    return {
        "workspaceRef": fixture["workspaceRef"],
        "projectRef": fixture["projectRef"],
        "seriesRef": fixture["seriesRef"],
        "episodeRef": fixture["episodeRef"],
        "productionRunRef": run["productionRunRef"],
        "validationProfileRef": DEFAULT_VALIDATION_PROFILE_REF,
        "validationProfileVersion": 1,
        "idempotencyKey": key,
    }


def source_span(scene: dict, source_field: str, source_index: int = 0) -> dict:
    if source_field == "ACTION":
        text = scene["action"]
    elif source_field == "DIALOGUE":
        text = scene["dialogue"][source_index]["text"]
    elif source_field == "NARRATION":
        text = scene["narration"][source_index]
    else:
        text = scene["subtitleText"][source_index]
    return {
        "scriptSceneRef": scene["scriptSceneRef"],
        "sourceField": source_field,
        "sourceIndex": source_index,
        "startOffsetInclusive": 0,
        "endOffsetExclusive": len(text),
    }


def action_beat(
    scene: dict,
    beat_ref: str,
    order: int,
    start: int,
    end: int,
    execution_class: str,
    *,
    targets: list[str] | None = None,
) -> dict:
    result = {
        "beatRef": beat_ref,
        "beatOrder": order,
        "sourceSpan": source_span(scene, "ACTION"),
        "subjectRefs": ["character-ari"],
        "targetRefs": list(targets or []),
        "frameRangeStartInclusive": start,
        "frameRangeEndExclusive": end,
        "executionClass": execution_class,
    }
    if execution_class == "DETERMINISTIC_EVENT":
        result["postprocessRequirementKey"] = "relay-status-glyph"
    return result


def execution_plan_command(
    fixture: dict, run: dict, bound_script: dict, validation: dict
) -> dict:
    first, second = bound_script["scriptVersion"]["scenes"]
    return {
        "workspaceRef": fixture["workspaceRef"],
        "projectRef": fixture["projectRef"],
        "seriesRef": fixture["seriesRef"],
        "episodeRef": fixture["episodeRef"],
        "productionRunRef": run["productionRunRef"],
        "consistencyValidationVersionRef": validation[
            "consistencyValidationVersionRef"
        ],
        "shots": [
            {
                "shotOrder": 1,
                "shotFrameCount": 50,
                "cameraInstruction": {
                    "framing": "MEDIUM",
                    "movement": "DOLLY_IN",
                },
                "actionExecutionBeats": [
                    action_beat(first, "beat-static", 1, 0, 10, "STATIC_HOLD"),
                    action_beat(first, "beat-micro", 2, 10, 20, "MICRO_MOTION"),
                    action_beat(
                        first,
                        "beat-contact",
                        3,
                        20,
                        30,
                        "CONTACT_ACTION",
                        targets=["character-mina"],
                    ),
                    action_beat(first, "beat-gait", 4, 30, 40, "GAIT_LOCOMOTION"),
                    action_beat(
                        first,
                        "beat-event",
                        5,
                        40,
                        50,
                        "DETERMINISTIC_EVENT",
                    ),
                ],
                "audioIntents": [
                    {
                        "audioType": "DIALOGUE",
                        "beatRef": "beat-static",
                        "sourceSpan": source_span(first, "DIALOGUE"),
                        "timingReference": {
                            "startFrameInclusive": 0,
                            "endFrameExclusive": 10,
                        },
                    },
                    {
                        "audioType": "AMBIENCE",
                        "beatRef": "beat-static",
                        "timingReference": {
                            "startFrameInclusive": 0,
                            "endFrameExclusive": 50,
                        },
                    },
                    {
                        "audioType": "SFX",
                        "beatRef": "beat-contact",
                        "timingReference": {
                            "startFrameInclusive": 20,
                            "endFrameExclusive": 30,
                        },
                    },
                ],
            },
            {
                "shotOrder": 2,
                "shotFrameCount": 20,
                "cameraInstruction": {
                    "framing": "WIDE",
                    "movement": "LOCKED",
                },
                "actionExecutionBeats": [
                    action_beat(second, "beat-second-static", 1, 0, 20, "STATIC_HOLD")
                ],
                "audioIntents": [
                    {
                        "audioType": "SILENCE",
                        "beatRef": "beat-second-static",
                        "timingReference": {
                            "startFrameInclusive": 0,
                            "endFrameExclusive": 20,
                        },
                    }
                ],
            },
        ],
        "idempotencyKey": "generic-upstream-execution-plan",
    }


def sealed(value: dict) -> dict:
    result = deepcopy(value)
    result["payloadDigest"] = _digest(result)
    return result


def evidence_record(
    workspace: str,
    run_ref: str,
    kind: str,
    ref: str,
    payload: dict,
    ordinal: int,
) -> EvidenceRecord:
    value = sealed(payload)
    return EvidenceRecord(
        workspaceRef=workspace,
        productionRunRef=run_ref,
        recordKind=kind,
        recordRef=ref,
        recordVersion=1,
        idempotencyKey=f"generic-admission-{ordinal}-{ref}",
        requestDigest=_digest({"kind": kind, "ref": ref, "ordinal": ordinal}),
        createdAt="2026-09-02T12:00:00Z",
        payload=value,
        payloadDigest=value["payloadDigest"],
    )


def method_service(boundary):
    return boundary._EpisodeProductionPublicBoundary__method_aware_media


def append_generic_anchor(
    boundary, fixture: dict, run: dict, execution_plan: dict
) -> dict:
    evidence = method_service(boundary).evidence_repository
    micro = next(
        item
        for item in execution_plan["visualExecutionRequirements"]
        if item["executionClass"] == "MICRO_MOTION"
    )
    candidate_ref = "generic-anchor-candidate"
    candidate = sealed(
        {
            "candidateRef": candidate_ref,
            "candidateVersion": 1,
            "mediaKind": "IMAGE",
            "revisionRef": "generic-anchor-revision",
            "slotRef": micro["creativeShotVersionRef"],
            "sourceAssetVersions": [],
            "publicationAllowed": False,
        }
    )
    asset_ref = "generic-action-anchor"
    asset_version_ref = "generic-action-anchor-version-1"
    records = (
        EvidenceRecord(
            workspaceRef=fixture["workspaceRef"],
            productionRunRef=run["productionRunRef"],
            recordKind=CANDIDATE,
            recordRef=candidate_ref,
            recordVersion=1,
            idempotencyKey="generic-anchor-candidate",
            requestDigest=_digest({"candidate": candidate_ref}),
            createdAt="2026-09-02T12:00:00Z",
            payload=candidate,
            payloadDigest=candidate["payloadDigest"],
        ),
        evidence_record(
            fixture["workspaceRef"],
            run["productionRunRef"],
            TECHNICAL_VALIDATION,
            "generic-anchor-technical-validation",
            {
                "candidateRef": candidate_ref,
                "candidateVersion": 1,
                "candidateDigest": candidate["payloadDigest"],
                "lifecycleState": "TECHNICALLY_VERIFIED",
                "publicationAllowed": False,
            },
            2,
        ),
        evidence_record(
            fixture["workspaceRef"],
            run["productionRunRef"],
            SEMANTIC_VISUAL_QC,
            "generic-anchor-visual-qc",
            {
                "candidateRef": candidate_ref,
                "candidateVersion": 1,
                "candidateDigest": candidate["payloadDigest"],
                "assessmentProfile": deepcopy(VISUAL_QC_PROFILE),
                "assessmentProfileDigest": VISUAL_QC_PROFILE_DIGEST,
                "supersedesVisualQc": None,
                "lifecycleState": "SEMANTIC_QC_PASSED",
                "publicationAllowed": False,
            },
            3,
        ),
        evidence_record(
            fixture["workspaceRef"],
            run["productionRunRef"],
            HUMAN_SELECTION,
            "generic-anchor-selection",
            {
                "candidateRef": candidate_ref,
                "lifecycleState": "SELECTED_BY_HUMAN",
                "publicationAllowed": False,
            },
            4,
        ),
        evidence_record(
            fixture["workspaceRef"],
            run["productionRunRef"],
            ASSET_ADMISSION,
            "generic-anchor-admission",
            {
                "candidateRef": candidate_ref,
                "assetVersionRef": asset_version_ref,
                "admissionState": "ADMITTED",
                "publicationAllowed": False,
            },
            5,
        ),
        evidence_record(
            fixture["workspaceRef"],
            run["productionRunRef"],
            ASSET_VERSION,
            asset_version_ref,
            {
                "schemaVersion": "v5.generic-admitted-image-asset-version.v1",
                "workspaceRef": fixture["workspaceRef"],
                "productionRunRef": run["productionRunRef"],
                "assetRef": asset_ref,
                "assetVersionRef": asset_version_ref,
                "version": 1,
                "creativeShotVersionRef": micro["creativeShotVersionRef"],
                "sourceCandidateRef": candidate_ref,
                "mediaKind": "image",
                "mediaType": "image/png",
                "sha256": _digest({"generic-anchor": "version-1"}),
                "state": "REGISTERED",
                "immutable": True,
                "publicationAllowed": False,
            },
            6,
        ),
    )
    evidence.append_records(records)
    asset = records[-1].payload
    return {
        "visualExecutionRequirementRef": micro[
            "visualExecutionRequirementRef"
        ],
        "inputRequirementKey": (
            "action-ready-anchor:" + micro["visualExecutionRequirementRef"]
        ),
        "inputRole": "ACTION_READY_ANCHOR",
        "assetVersionRef": asset["assetVersionRef"],
        "assetVersionDigest": asset["payloadDigest"],
    }


def input_plan_command(
    fixture: dict,
    run: dict,
    execution_plan: dict,
    anchor_binding: dict,
) -> dict:
    return {
        "workspaceRef": fixture["workspaceRef"],
        "projectRef": fixture["projectRef"],
        "seriesRef": fixture["seriesRef"],
        "episodeRef": fixture["episodeRef"],
        "productionRunRef": run["productionRunRef"],
        "executionMethodPlanVersionRef": execution_plan[
            "executionMethodPlanVersionRef"
        ],
        "assetBindings": [deepcopy(anchor_binding)],
        "idempotencyKey": "generic-upstream-input-plan",
    }


def video_route_command(fixture: dict, run: dict, input_plan: dict) -> dict:
    return {
        "workspaceRef": fixture["workspaceRef"],
        "projectRef": fixture["projectRef"],
        "seriesRef": fixture["seriesRef"],
        "episodeRef": fixture["episodeRef"],
        "productionRunRef": run["productionRunRef"],
        "methodAwareInputPlanVersionRef": input_plan[
            "methodAwareInputPlanVersionRef"
        ],
        "idempotencyKey": "generic-upstream-video-route",
    }


def confirm_fixed_voice(boundary, fixture: dict) -> dict:
    created = boundary.create_voice_lock(
        {
            "workspaceRef": fixture["workspaceRef"],
            "projectRef": fixture["projectRef"],
            "seriesRef": fixture["seriesRef"],
            "characterRef": "character-mina",
            "engineFamily": "local-neural-tts-v1",
            "voiceId": "generic-fixed-voice-mina",
            "gender": "female",
            "apparentAge": 35,
            "pitchSemitones": 0.0,
            "rateScale": 1.0,
            "timbreDescriptor": "clear-neutral-register",
            "languageCode": "en-US",
            "idempotencyKey": "generic-fixed-voice-create",
        }
    )
    return boundary.confirm_voice_lock(
        {
            "workspaceRef": fixture["workspaceRef"],
            "projectRef": fixture["projectRef"],
            "seriesRef": fixture["seriesRef"],
            "voiceRef": created["voiceLock"]["voiceRef"],
            "voiceLockVersionRef": created["voiceLockVersion"][
                "voiceLockVersionRef"
            ],
            "voiceLockDigest": created["voiceLockVersion"]["payloadDigest"],
            "expectedRevision": created["voiceLock"]["revision"],
            "idempotencyKey": "generic-fixed-voice-confirm",
        }
    )


def fixed_voice_asset(
    fixture: dict, run: dict, confirmed_voice_lock: dict
) -> dict:
    command = voice_asset_command(
        confirmed_voice_lock, subject_ref="character-mina"
    )
    command.update(
        {
            "workspaceRef": fixture["workspaceRef"],
            "projectRef": fixture["projectRef"],
            "seriesRef": fixture["seriesRef"],
            "episodeRef": fixture["episodeRef"],
            "productionRunRef": run["productionRunRef"],
            "assetRef": "generic-fixed-voice-asset",
            "assetVersionRef": "generic-fixed-voice-asset-version-1",
            "createdBy": "v5.generic-upstream.acceptance",
        }
    )
    return build_voice_asset_version(
        command, confirmed_voice_lock=confirmed_voice_lock
    )


def audio_route_command(
    fixture: dict,
    run: dict,
    execution_plan: dict,
    requirement: dict,
    *,
    voice_asset: dict,
    key_suffix: str | None = None,
) -> dict:
    audio_type = requirement["audioType"]
    command = {
        "workspaceRef": fixture["workspaceRef"],
        "projectRef": fixture["projectRef"],
        "seriesRef": fixture["seriesRef"],
        "episodeRef": fixture["episodeRef"],
        "productionRunRef": run["productionRunRef"],
        "executionMethodPlanVersionRef": execution_plan[
            "executionMethodPlanVersionRef"
        ],
        "audioRequirementRef": requirement["audioRequirementRef"],
        "idempotencyKey": (
            key_suffix or f"generic-audio-route-{audio_type.lower()}"
        ),
    }
    if audio_type != "SILENCE":
        command["rightsBinding"] = rights_binding(
            asset_requirement_ref=requirement["audioRequirementRef"],
            asset_requirement_digest=requirement["payloadDigest"],
        )
    if audio_type == "DIALOGUE":
        command["voiceAssetVersion"] = deepcopy(voice_asset)
    return command


class GenericUpstreamMethodClosureAcceptanceTests(unittest.TestCase):
    def test_generic_sqlite_vertical_slice_closes_without_runtime_fallbacks(self):
        fixture = load_fixture()
        refs = GenericRefs(fixture)
        scope_authority = GenericScopeAuthority()
        approval_authority = GenericApprovalAuthority()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            creator_database = root / "creator.sqlite3"
            production_database = root / "episode-production.sqlite3"
            evidence_database = root / "episode-production.evidence.sqlite3"
            media_jobs_database = root / "media-jobs.sqlite3"
            artifacts = root / "artifacts"

            lifecycle = LifecycleAssembly.sqlite(
                creator_database,
                initialize_or_upgrade=True,
                ref_factory=refs,
                clock=lambda: "2026-09-02T12:00:00Z",
                m6_scope_authority=scope_authority,
                m6_approval_authority=approval_authority,
            )
            roots = seed_generic_roots(lifecycle, fixture)
            self.assertEqual(roots["project"]["projectRef"], fixture["projectRef"])
            self.assertEqual(roots["series"]["seriesRef"], fixture["seriesRef"])
            self.assertEqual(roots["episode"]["episodeRef"], fixture["episodeRef"])
            self.assertNotIn(
                "m6ConsumerBinding", roots["historical"]["scriptVersion"]
            )
            binding = roots["boundScript"]["scriptVersion"]["m6ConsumerBinding"]
            self.assertEqual(binding["projectRef"], fixture["projectRef"])
            self.assertEqual(
                binding["m6BaselineSnapshotRef"],
                roots["baseline"]["m6BaselineSnapshotRef"],
            )

            video_adapter = NoCallVideoAdapter()
            coordinator = MediaJobCoordinator(
                SqliteMediaJobAdapter(media_jobs_database),
                video_adapter,
                artifacts,
                ref_factory=refs,
                clock=lambda: "2026-09-02T12:00:00Z",
            )
            boundary_kwargs = {
                "project_boundary": lifecycle.project_context,
                "series_episode_boundary": lifecycle.series_episode,
                "series_planning_boundary": lifecycle.series_planning,
                "script_studio_boundary": lifecycle.script_studio,
                "evidence_database_path": evidence_database,
                "media_execution": coordinator,
            }
            boundary = create_local_development_boundary(
                production_database,
                **boundary_kwargs,
                ref_factory=refs,
                clock=lambda: "2026-09-02T12:00:00Z",
            )
            creator_tables = sqlite_tables(creator_database)
            evidence_tables = sqlite_tables(evidence_database)
            media_job_tables = sqlite_tables(media_jobs_database)
            files_before = {path.name for path in root.iterdir()}

            run_input = run_command(fixture)
            run = boundary.create_run(run_input)
            validation_input = validation_command(
                fixture, run, key="generic-upstream-validation"
            )
            validation = boundary.create_narrative_validation(validation_input)
            self.assertEqual(
                (validation["result"], validation["m8Readiness"]),
                ("PASS", "READY_FOR_M8"),
            )

            execution_input = execution_plan_command(
                fixture, run, roots["boundScript"], validation
            )
            execution_plan = boundary.create_execution_method_plan(execution_input)
            self.assertEqual(
                {
                    item["executionClass"]
                    for item in execution_plan["visualExecutionRequirements"]
                },
                EXECUTION_CLASSES,
            )
            self.assertTrue(execution_plan["visualExecutionRequirements"])
            self.assertTrue(execution_plan["audioRequirements"])
            self.assertEqual(len(execution_plan["postprocessRequirements"]), 1)

            anchor = append_generic_anchor(
                boundary, fixture, run, execution_plan
            )
            input_command = input_plan_command(
                fixture, run, execution_plan, anchor
            )
            input_plan = boundary.create_method_aware_input_plan(input_command)
            self.assertEqual(len(input_plan["methodInputPlans"]), 6)
            self.assertNotEqual(len(input_plan["methodInputPlans"]), 4)
            micro_input = next(
                item
                for item in input_plan["methodInputPlans"]
                if item["executionClass"] == "MICRO_MOTION"
            )
            self.assertEqual(micro_input["inputPlanningState"], "READY")

            video_command = video_route_command(fixture, run, input_plan)
            video_route = boundary.route_method_aware_videos(video_command)
            states: dict[str, set[str]] = {}
            methods: dict[str, set[str]] = {}
            for route in video_route["routes"]:
                states.setdefault(route["executionClass"], set()).add(
                    route["routingState"]
                )
                methods.setdefault(route["executionClass"], set()).add(
                    route["executionMethod"]
                )
                self.assertFalse(route["fallbackUsed"])
            self.assertEqual(states["STATIC_HOLD"], {"BYPASSED_STATIC_PLATE"})
            self.assertEqual(
                states["MICRO_MOTION"], {"QUEUED_EXISTING_MEDIA_JOB"}
            )
            self.assertEqual(
                states["CONTACT_ACTION"], {"CAPABILITY_UNAVAILABLE"}
            )
            self.assertEqual(
                states["GAIT_LOCOMOTION"], {"CAPABILITY_UNAVAILABLE"}
            )
            self.assertEqual(
                states["DETERMINISTIC_EVENT"],
                {"REJECTED_DETERMINISTIC_POSTPROCESS"},
            )
            self.assertEqual(
                methods,
                {
                    "STATIC_HOLD": {"STATIC_PLATE_OR_REUSE"},
                    "MICRO_MOTION": {"SINGLE_ANCHOR_I2V"},
                    "CONTACT_ACTION": {"CONTACT_CONDITIONED_VIDEO"},
                    "GAIT_LOCOMOTION": {
                        "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO"
                    },
                    "DETERMINISTIC_EVENT": {
                        "V3_DETERMINISTIC_COMPOSITION"
                    },
                },
            )
            for execution_class in (
                "CONTACT_ACTION",
                "GAIT_LOCOMOTION",
                "DETERMINISTIC_EVENT",
            ):
                closed_route = next(
                    item
                    for item in video_route["routes"]
                    if item["executionClass"] == execution_class
                )
                self.assertIsNone(closed_route["videoGenerationRequestRef"])
                self.assertFalse(closed_route["fallbackUsed"])
            event_route = next(
                item
                for item in video_route["routes"]
                if item["executionClass"] == "DETERMINISTIC_EVENT"
            )
            self.assertEqual(
                event_route["targetBoundary"], "M13_DETERMINISTIC_POSTPROCESS"
            )
            self.assertIsNone(event_route["videoGenerationRequestRef"])
            self.assertEqual(video_route["videoGenerationRequestCount"], 1)
            self.assertEqual(video_route["queuedJobCount"], 1)
            self.assertFalse(video_route["wanFallbackUsed"])
            self.assertEqual(video_adapter.generate_calls, 0)
            self.assertEqual(
                len(
                    [
                        request
                        for request in video_route["videoGenerationRequests"]
                        if not request.get("visualExecutionRequirementRef")
                        or not request.get("visualExecutionRequirementDigest")
                    ]
                ),
                0,
            )

            confirmed_voice = confirm_fixed_voice(boundary, fixture)
            voice_asset = fixed_voice_asset(fixture, run, confirmed_voice)
            audio_commands = [
                audio_route_command(
                    fixture,
                    run,
                    execution_plan,
                    requirement,
                    voice_asset=voice_asset,
                )
                for requirement in execution_plan["audioRequirements"]
            ]
            audio_routes = [
                boundary.create_explicit_audio_generation_request(command)
                for command in audio_commands
            ]
            audio_requests = [
                route["audioGenerationRequest"]
                for route in audio_routes
                if route["audioGenerationRequest"] is not None
            ]
            explicit_non_silence = [
                item
                for item in execution_plan["audioRequirements"]
                if item["audioType"] != "SILENCE"
            ]
            self.assertEqual(len(audio_requests), len(explicit_non_silence))
            self.assertEqual(
                {
                    request["audioRequirementRef"]
                    for request in audio_requests
                },
                {
                    requirement["audioRequirementRef"]
                    for requirement in explicit_non_silence
                },
            )
            self.assertEqual(
                len(
                    [
                        request
                        for request in audio_requests
                        if not request.get("audioRequirementRef")
                        or not request.get("audioRequirementDigest")
                    ]
                ),
                0,
            )
            silence = next(
                route
                for route in audio_routes
                if route["audioType"] == "SILENCE"
            )
            self.assertEqual(silence["routeDisposition"], "NO_REQUEST_SILENCE")
            self.assertIsNone(silence["audioGenerationRequest"])
            self.assertTrue(
                all(not route["m12RuntimeInstalled"] for route in audio_routes)
            )
            self.assertTrue(
                all(not route["publicationAllowed"] for route in audio_routes)
            )

            restarted_lifecycle = LifecycleAssembly.sqlite(
                creator_database,
                ref_factory=refs,
                clock=lambda: "2026-09-02T12:00:01Z",
                m6_scope_authority=scope_authority,
                m6_approval_authority=approval_authority,
            )
            restarted_script = restarted_lifecycle.script_studio.get_workspace(
                fixture["workspaceRef"],
                fixture["seriesRef"],
                fixture["episodeRef"],
            )
            restored_bound_script = next(
                item
                for item in restarted_script["versions"]
                if item["scriptVersionRef"]
                == roots["boundScript"]["scriptVersion"]["scriptVersionRef"]
            )
            self.assertEqual(restored_bound_script["m6ConsumerBinding"], binding)

            restarted_adapter = NoCallVideoAdapter()
            restarted_coordinator = MediaJobCoordinator(
                SqliteMediaJobAdapter(
                    media_jobs_database, initialize_if_missing=False
                ),
                restarted_adapter,
                artifacts,
                ref_factory=refs,
                clock=lambda: "2026-09-02T12:00:01Z",
            )
            restarted_kwargs = {
                "project_boundary": restarted_lifecycle.project_context,
                "series_episode_boundary": restarted_lifecycle.series_episode,
                "series_planning_boundary": restarted_lifecycle.series_planning,
                "script_studio_boundary": restarted_lifecycle.script_studio,
                "evidence_database_path": evidence_database,
                "media_execution": restarted_coordinator,
            }
            restarted = create_local_development_boundary(
                production_database,
                **restarted_kwargs,
                ref_factory=refs,
                clock=lambda: "2026-09-02T12:00:01Z",
                initialize_if_missing=False,
            )

            self.assertTrue(restarted.create_run(run_input)["idempotentReplay"])
            self.assertTrue(
                restarted.create_narrative_validation(validation_input)[
                    "idempotentReplay"
                ]
            )
            self.assertTrue(
                restarted.create_execution_method_plan(execution_input)[
                    "idempotentReplay"
                ]
            )
            self.assertTrue(
                restarted.create_method_aware_input_plan(input_command)[
                    "idempotentReplay"
                ]
            )
            self.assertTrue(
                restarted.route_method_aware_videos(video_command)[
                    "idempotentReplay"
                ]
            )
            replayed_audio = [
                restarted.create_explicit_audio_generation_request(command)
                for command in audio_commands
            ]
            self.assertTrue(
                all(route["idempotentReplay"] for route in replayed_audio)
            )
            self.assertEqual(
                len(
                    restarted_coordinator.list_jobs(
                        fixture["workspaceRef"], run["productionRunRef"]
                    )
                ),
                1,
            )
            self.assertEqual(restarted_adapter.generate_calls, 0)

            changed_execution_input = deepcopy(execution_input)
            changed_execution_input["shots"][0]["cameraInstruction"][
                "movement"
            ] = "LOCKED"
            with self.assertRaises(EpisodeProductionPublicError) as changed_replay:
                restarted.create_execution_method_plan(changed_execution_input)
            self.assertEqual(
                changed_replay.exception.code, "idempotency_conflict"
            )

            with self.assertRaises(EpisodeProductionPublicError) as foreign:
                restarted.get_method_aware_video_route(
                    "workspace-generic-foreign",
                    fixture["projectRef"],
                    fixture["seriesRef"],
                    fixture["episodeRef"],
                    run["productionRunRef"],
                    video_route["videoMethodRouteVersionRef"],
                )
            self.assertEqual(
                (foreign.exception.status, foreign.exception.code),
                (404, "not_found"),
            )

            newer_validation = restarted.create_narrative_validation(
                validation_command(
                    fixture, run, key="generic-upstream-validation-successor"
                )
            )
            self.assertEqual(newer_validation["currentness"], "CURRENT")
            stale_plan = restarted.get_execution_method_plan(
                fixture["workspaceRef"],
                fixture["projectRef"],
                fixture["seriesRef"],
                fixture["episodeRef"],
                run["productionRunRef"],
                execution_plan["executionMethodPlanVersionRef"],
            )
            self.assertEqual(stale_plan["currentness"], "STALE")
            stale_video = restarted.get_method_aware_video_route(
                fixture["workspaceRef"],
                fixture["projectRef"],
                fixture["seriesRef"],
                fixture["episodeRef"],
                run["productionRunRef"],
                video_route["videoMethodRouteVersionRef"],
            )
            self.assertEqual(stale_video["currentness"], "STALE")
            first_audio = next(
                route
                for route in audio_routes
                if route["audioGenerationRequest"] is not None
            )
            stale_audio = restarted.get_explicit_audio_requirement_route(
                fixture["workspaceRef"],
                fixture["projectRef"],
                fixture["seriesRef"],
                fixture["episodeRef"],
                run["productionRunRef"],
                first_audio["audioRequirementRouteVersionRef"],
            )
            self.assertEqual(stale_audio["currentness"], "STALE")
            first_requirement = next(
                item
                for item in execution_plan["audioRequirements"]
                if item["audioType"] == first_audio["audioType"]
            )
            with self.assertRaises(EpisodeProductionPublicError) as stale:
                restarted.create_explicit_audio_generation_request(
                    audio_route_command(
                        fixture,
                        run,
                        execution_plan,
                        first_requirement,
                        voice_asset=voice_asset,
                        key_suffix="generic-audio-route-against-stale-plan",
                    )
                )
            self.assertEqual(stale.exception.code, "execution_not_authorized")

            audio_records = method_service(
                restarted
            ).evidence_repository.list_records(
                fixture["workspaceRef"],
                run["productionRunRef"],
                record_kind=AUDIO_REQUIREMENT_ROUTE_RECORD_KIND,
            )
            self.assertEqual(len(audio_records), len(audio_routes))
            self.assertEqual(sqlite_tables(creator_database), creator_tables)
            self.assertEqual(sqlite_tables(evidence_database), evidence_tables)
            self.assertEqual(sqlite_tables(media_jobs_database), media_job_tables)
            self.assertEqual({path.name for path in root.iterdir()}, files_before)


if __name__ == "__main__":
    unittest.main()
