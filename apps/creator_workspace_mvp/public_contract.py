"""Versioned Creator Public HTTP/API route and capability contract."""

from __future__ import annotations

from typing import Final


PUBLIC_API_PREFIX: Final = "/creator/api/v1"

CAPABILITIES_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/capabilities"
PUBLIC_AI_DIRECTOR_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/ai-director/candidates"
PUBLIC_CONFIRM_PLAN_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/creative-plans/confirm"
PUBLIC_SERIES_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series"
PUBLIC_PROJECTS_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/projects"
PUBLIC_PROJECT_CONTEXT_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/project-contexts"
PUBLIC_EPISODES_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/episodes"
PUBLIC_SCRIPT_WORKSPACE_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/script-workspaces"
PUBLIC_SCRIPT_GENERATE_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/script-versions/generate"
PUBLIC_SCRIPT_MANUAL_VERSION_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/script-versions/manual"
PUBLIC_SCRIPT_REWRITE_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/script-versions/rewrite-scene"
PUBLIC_SCRIPT_CONFIRM_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/script-versions/confirm"
PUBLIC_STORYBOARD_BOOTSTRAP_ENDPOINT: Final = (
    f"{PUBLIC_API_PREFIX}/script-workspaces/storyboard-bootstrap"
)
PUBLIC_SERIES_PLANNING_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-planning-workspaces"
PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-plan-candidates"
PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-plans/confirm-candidate"
PUBLIC_SERIES_PLANNING_MANUAL_VERSION_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-plan-versions/manual"
PUBLIC_SERIES_PLANNING_CONFIRM_VERSION_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-plan-versions/confirm"
PUBLIC_SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT: Final = (
    f"{PUBLIC_API_PREFIX}/series-planning-workspaces/m6-bootstrap"
)
PUBLIC_SERIES_INTELLIGENCE_WORKSPACE_ENDPOINT: Final = (
    f"{PUBLIC_API_PREFIX}/series-intelligence-workspaces"
)
PUBLIC_M6_BIBLE_VERSION_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-intelligence/bible-versions"
PUBLIC_M6_BIBLE_CANDIDATE_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-intelligence/bible-candidates"
PUBLIC_M6_BIBLE_CONFIRM_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-intelligence/bible-confirmations"
PUBLIC_M6_CHARACTER_VERSION_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-intelligence/character-versions"
PUBLIC_M6_CHARACTER_CANDIDATE_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-intelligence/character-candidates"
PUBLIC_M6_CHARACTER_CONFIRM_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-intelligence/character-confirmations"
PUBLIC_M6_BASELINE_ACTIVATE_ENDPOINT: Final = f"{PUBLIC_API_PREFIX}/series-intelligence/baseline-activations"
PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT: Final = (
    f"{PUBLIC_API_PREFIX}/episode-production-runs"
)


CAPABILITY_PROJECTION: Final = (
    {
        "id": "M1",
        "name": "AI Director",
        "state": "available",
        "publicResources": ["ai-director/candidates", "creative-plans/confirm"],
        "requirements": ["text_generation_for_candidate_generation"],
    },
    {
        "id": "M2",
        "name": "Series + Episode Foundation",
        "state": "available",
        "publicResources": ["series", "episodes"],
        "requirements": [],
    },
    {
        "id": "M3",
        "name": "Script Studio",
        "state": "available",
        "publicResources": ["script-workspaces", "script-versions"],
        "requirements": ["confirmed_creative_plan", "text_generation_for_ai_generation"],
    },
    {
        "id": "M4",
        "name": "Project Context",
        "state": "available",
        "publicResources": ["projects", "project-contexts"],
        "requirements": ["series_for_series_project"],
    },
    {
        "id": "M5",
        "name": "Series Planning + Series Director",
        "state": "available",
        "publicResources": ["series-planning-workspaces", "series-plan-candidates", "series-plan-versions"],
        "requirements": ["project_series_binding", "text_generation_for_candidate_generation"],
    },
    {
        "id": "M6",
        "name": "Series Intelligence",
        "state": "authority_required",
        "publicResources": ["series-intelligence-workspaces", "series-intelligence"],
        "requirements": ["confirmed_m5_source", "external_scope_approval_and_identity_authorities"],
    },
    {
        "id": "M7", "name": "Narrative Closed Loop", "state": "local_evidence_only",
        "publicResources": ["episode-production-runs/shot-graph"],
        "requirements": ["M6", "confirmed_script"],
    },
    {
        "id": "M8", "name": "Storyboard + Creative Shot Domain", "state": "local_evidence_only",
        "publicResources": ["episode-production-runs/shot-graph"], "requirements": ["M7"],
    },
    {
        "id": "M9", "name": "Asset Requirement + Asset Intelligence", "state": "local_evidence_only",
        "publicResources": ["episode-production-runs/assets"], "requirements": ["M8"],
    },
    {
        "id": "M10", "name": "Image Generation", "state": "local_evidence_only",
        "publicResources": [
            "episode-production-runs/production-readiness",
            "episode-production-runs/real-media-revision",
            "episode-production-runs/real-image-selection",
        ],
        "requirements": [
            "M9",
            "G6_local_qc_parent_for_same_run_revision",
            "live_multi_reference_image_capability_before_execution",
        ],
    },
    {
        "id": "M11", "name": "Video Production", "state": "production_policy_required",
        "publicResources": [
            "episode-production-runs/production-readiness",
            "episode-production-runs/provider-experiments",
            "episode-production-runs/media",
            "episode-production-runs/real-video-revision",
        ],
        "requirements": ["M10", "rights_manifest", "live_video_provider"],
    },
    {
        "id": "M12", "name": "Audio Production", "state": "production_policy_required",
        "publicResources": ["episode-production-runs/production-readiness", "episode-production-runs/media"],
        "requirements": ["M11", "rights_manifest", "live_audio_provider"],
    },
    {
        "id": "M13", "name": "Timeline + Composition + Render", "state": "local_evidence_only",
        "publicResources": ["episode-production-runs/preview"], "requirements": ["M11", "M12"],
    },
    {
        "id": "M14", "name": "Preview + QC + Approval + Local Regeneration", "state": "local_evidence_only",
        "publicResources": ["episode-production-runs/preview", "episode-production-runs/finalize"],
        "requirements": ["M13", "external_human_approvals"],
    },
    {
        "id": "M15", "name": "Episode Master + Works", "state": "local_evidence_only",
        "publicResources": ["episode-production-runs/delivery"],
        "requirements": ["M14", "publication_eligibility"],
    },
    {"id": "M16", "name": "Batch Production Orchestration", "state": "not_open", "publicResources": [], "requirements": ["M15"]},
    {"id": "M17", "name": "Series Release & Management", "state": "not_open", "publicResources": [], "requirements": ["M16"]},
    {"id": "M18", "name": "Performance Feedback", "state": "not_open", "publicResources": [], "requirements": ["M17"]},
    {"id": "M19", "name": "Commercial SaaS + Enterprise Hardening", "state": "not_open", "publicResources": [], "requirements": ["M18"]},
)


def capability_payload() -> dict:
    """Return a detached projection so request handlers cannot mutate the contract."""
    return {
        "ok": True,
        "schemaVersion": "creator.public.capabilities.v1",
        "apiVersion": "v1",
        "capabilities": [
            {
                **item,
                "publicResources": list(item["publicResources"]),
                "requirements": list(item["requirements"]),
            }
            for item in CAPABILITY_PROJECTION
        ],
    }
