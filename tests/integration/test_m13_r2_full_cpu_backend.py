from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import secrets
import shutil
import tempfile
import threading
import time
import unittest
from urllib import parse, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import (
    PUBLIC_AUTH_SCHEMA_VERSION,
    PublicApiAuthenticator,
    token_sha256,
)
from apps.creator_workspace_mvp.public_contract import (
    PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT,
)
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    RepositoryUnavailableError,
)
from services.v5_core_os.episode_production.media import ArtifactRejectedError
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicBoundary,
)
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.integration.m13_r2_support import (
    E4_EFFECT_ORDER,
    FIXTURE_LABELS,
    RUN,
    WORKSPACE,
    FailOneRenderAppend,
    build_stack,
    candidate_command,
    preview_command,
    restart_stack,
)
from tests.integration.test_m13_r1a_composition_render_manifest import (
    _command as manifest_command,
    _profile,
)
from tests.unit.test_episode_production_k2 import seed_k2_roots


FORBIDDEN_GENERIC_VALUES = (
    "K2-002",
    "EP01",
    "SH02",
    "SH15",
    "SH18",
    "裴昀",
    "沈知微",
    "贞",
    "k2-technical-evidence",
)


def _track_counts(stack) -> dict[str, int]:
    return {
        track["trackKind"]: sum(
            clip["trackRef"] == track["trackRef"]
            for clip in stack.timeline["clips"]
        )
        for track in stack.timeline["tracks"]
    }


def _manifest(stack, slug: str, profile: dict) -> dict:
    return stack.service.create_composition_render_manifest(
        manifest_command(
            stack.run,
            stack.timeline["timelineVersion"],
            slug=slug,
            profile=profile,
        )
    )


def _public_boundary(service) -> EpisodeProductionPublicBoundary:
    boundary = object.__new__(EpisodeProductionPublicBoundary)
    setattr(boundary, "_EpisodeProductionPublicBoundary__delivery", service)
    return boundary


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13R2FullCpuBackendIntegrationTests(unittest.TestCase):
    def test_ci_micro_complete_chain_restart_interruption_and_tamper(self):
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as directory:
            stack = build_stack(Path(directory), 120)
            self.assertEqual(
                _track_counts(stack),
                {"VIDEO": 2, "AUDIO": 5, "SUBTITLE": 1, "EFFECT": 8},
            )
            self.assertEqual(
                {item["stemRole"] for item in stack.inputs.audio["members"]},
                {"dialogue", "narration", "sfx", "ambience", "music"},
            )
            edit_operations = {
                item["payload"]["operation"]
                for item in stack.repository.list_records(
                    WORKSPACE, RUN, record_kind="TimelineEditOperation"
                )
            }
            self.assertTrue(
                {
                    "SPLIT_CLIP",
                    "TRIM_CLIP",
                    "MOVE_CLIP",
                    "SET_TRANSITION",
                    "SET_SPEED",
                    "SET_TRANSFORM",
                    "SET_MASKS",
                }.issubset(edit_operations)
            )

            preview = stack.preview
            self.assertEqual(preview["state"], "REAL_PREVIEW_READY")
            self.assertFalse(preview["previewCandidate"]["publicationAllowed"])
            self.assertEqual(
                [
                    item["effectMode"]
                    for item in preview["previewCandidate"]["effectResultBindings"]
                ],
                E4_EFFECT_ORDER,
            )
            self.assertEqual(
                preview["compositionResult"]["outputMediaProbe"]["frameCount"],
                120,
            )

            sidecar_manifest = _manifest(
                stack,
                "r2-micro-sidecar",
                _profile(160, 120, subtitle_mode="SIDECAR"),
            )
            first_command = candidate_command(
                sidecar_manifest, "micro-sidecar-first"
            )
            first = stack.service.create_render_candidate(first_command)
            candidate = first["renderCandidate"]
            self.assertEqual(candidate["technicalValidationState"], "PASS")
            self.assertEqual(candidate["assetAdmissionState"], "NOT_ADMITTED")
            self.assertEqual(candidate["masterState"], "NOT_CREATED")
            self.assertEqual(candidate["exportState"], "NOT_CREATED")
            self.assertFalse(candidate["publicationAllowed"])
            self.assertIsNotNone(first["artifactEvidence"]["subtitleSidecar"])
            self.assertFalse(first["runtimeEvidence"]["gpuUsed"])
            self.assertFalse(first["runtimeEvidence"]["providerUsed"])
            self.assertEqual(
                (
                    candidate["mediaProbe"]["width"],
                    candidate["mediaProbe"]["height"],
                ),
                (160, 120),
            )

            burn_manifest = _manifest(
                stack,
                "r2-micro-burn",
                _profile(
                    160,
                    120,
                    subtitle_mode="BURN_IN",
                    font=stack.font_fixture.asset,
                ),
            )
            burn = stack.service.create_render_candidate(
                candidate_command(burn_manifest, "micro-burn")
            )
            self.assertIsNone(burn["artifactEvidence"]["subtitleSidecar"])
            self.assertEqual(
                burn["renderCandidate"]["subtitleTimingDigest"],
                candidate["subtitleTimingDigest"],
            )
            self.assertNotEqual(
                burn["renderCandidate"]["decodedFramePixelDigest"],
                candidate["decodedFramePixelDigest"],
            )

            interrupted_manifest = _manifest(
                stack,
                "r2-micro-interruption",
                _profile(176, 128, subtitle_mode="SIDECAR"),
            )
            interrupted_command = candidate_command(
                interrupted_manifest, "micro-interruption"
            )
            failing = FailOneRenderAppend(stack.repository)
            stack.service.evidence = failing
            with self.assertRaises(RepositoryUnavailableError):
                stack.service.create_render_candidate(interrupted_command)
            self.assertTrue(failing.failed)
            stack.service.evidence = stack.repository
            recovered = False
            try:
                stack.service.create_render_candidate(interrupted_command)
                recovered = True
            except EpisodeProductionError:
                pass
            candidates = stack.service.list_render_candidates(WORKSPACE, RUN)[
                "renderCandidates"
            ]
            self.assertEqual(len(candidates), 3 if recovered else 2)
            self.assertEqual(
                len({item["renderCandidateRef"] for item in candidates}),
                len(candidates),
            )

            restarted, restarted_composition, _ = restart_stack(stack)
            replay = restarted.create_render_candidate(first_command)
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(replay["renderCandidate"], candidate)
            self.assertEqual(restarted_composition.preview_v3_requests, [])
            content = restarted.get_render_candidate_content(
                WORKSPACE, RUN, candidate["renderCandidateRef"]
            )
            with content["path"].open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaises(ArtifactRejectedError):
                restarted.get_render_candidate(
                    WORKSPACE, RUN, candidate["renderCandidateRef"]
                )

            elapsed = time.monotonic() - started
            print(
                "M13_R2_MICRO_PERFORMANCE="
                + json.dumps(
                    {
                        "wallSeconds": round(elapsed, 3),
                        "peakRssKiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        "renderBytes": candidate["byteSize"],
                        "previewBytes": preview["compositionResult"]["outputByteSize"],
                    },
                    sort_keys=True,
                )
            )

    @unittest.skipUnless(
        os.environ.get("M13_R2_FULL_CPU_ACCEPTANCE") == "1",
        "set M13_R2_FULL_CPU_ACCEPTANCE=1 for the 30-second CPU acceptance",
    )
    def test_generic_30_second_authenticated_full_render_is_bit_exact(self):
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as directory:
            stack = build_stack(
                Path(directory), 720, width=704, height=1280
            )
            generic_material = {
                "run": stack.run,
                "base": stack.inputs.base,
                "masks": list(stack.inputs.masks),
                "audioBindings": [
                    item.as_dict() for item in stack.inputs.audio["bindings"]
                ],
                "audioCues": [
                    item.as_dict() for item in stack.inputs.audio["cues"]
                ],
                "stemSet": stack.inputs.audio["stemSet"].as_dict(),
                "timeline": stack.timeline,
            }
            encoded_generic = json.dumps(
                generic_material, ensure_ascii=False, sort_keys=True
            )
            for forbidden in FORBIDDEN_GENERIC_VALUES:
                self.assertNotIn(forbidden, encoded_generic)
            self.assertEqual(
                _track_counts(stack),
                {"VIDEO": 2, "AUDIO": 5, "SUBTITLE": 1, "EFFECT": 8},
            )

            preview = stack.preview
            self.assertEqual(preview["state"], "REAL_PREVIEW_READY")
            self.assertEqual(
                preview["compositionResult"]["outputMediaProbe"]["frameCount"],
                720,
            )
            self.assertEqual(
                [
                    item["effectMode"]
                    for item in preview["previewCandidate"]["effectResultBindings"]
                ],
                E4_EFFECT_ORDER,
            )

            burn_manifest = _manifest(
                stack,
                "r2-full-burn",
                _profile(
                    704,
                    1280,
                    subtitle_mode="BURN_IN",
                    font=stack.font_fixture.asset,
                ),
            )
            declared_720 = _manifest(
                stack,
                "r2-full-declared-720",
                _profile(
                    720,
                    1280,
                    subtitle_mode="BURN_IN",
                    font=stack.font_fixture.asset,
                ),
            )
            declared_1080 = _manifest(
                stack,
                "r2-full-declared-1080",
                _profile(
                    1080,
                    1920,
                    subtitle_mode="BURN_IN",
                    font=stack.font_fixture.asset,
                ),
            )
            self.assertEqual(
                (
                    declared_720["renderManifest"]["outputProfile"]["width"],
                    declared_720["renderManifest"]["outputProfile"]["height"],
                ),
                (720, 1280),
            )
            self.assertEqual(
                (
                    declared_1080["renderManifest"]["outputProfile"]["width"],
                    declared_1080["renderManifest"]["outputProfile"]["height"],
                ),
                (1080, 1920),
            )

            first_command = candidate_command(burn_manifest, "full-api-first")
            token = secrets.token_urlsafe(48)
            authenticator = PublicApiAuthenticator.from_mapping(
                {
                    "schemaVersion": PUBLIC_AUTH_SCHEMA_VERSION,
                    "credentials": [
                        {
                            "credentialRef": "creator-m13-r2-full",
                            "workspaceRef": WORKSPACE,
                            "tokenSha256": token_sha256(token),
                            "enabled": True,
                        }
                    ],
                }
            )
            assembly, _, _, _, _, _ = seed_k2_roots()
            server = create_server(
                ("127.0.0.1", 0),
                AiDirectorService(FakeTextGenerationCapability([])),
                series_episode_boundary=assembly.series_episode,
                project_boundary=assembly.project_context,
                series_planning_boundary=assembly.series_planning,
                series_intelligence_boundary=assembly.series_intelligence,
                script_studio_boundary=assembly.script_studio,
                episode_production_boundary=_public_boundary(stack.service),
                public_authenticator=authenticator,
                allow_internal_routes=False,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            collection = (
                f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
                f"{parse.quote(RUN, safe='')}/render-candidates"
            )
            try:
                public_payload = {
                    key: value
                    for key, value in first_command.items()
                    if key not in {"workspaceRef", "productionRunRef"}
                }
                post = request.Request(
                    base_url + collection,
                    data=json.dumps(public_payload).encode(),
                    method="POST",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                with request.urlopen(post, timeout=1800) as response:
                    self.assertEqual(response.status, 201)
                    created = json.loads(response.read().decode())
                redacted = json.dumps(created).lower()
                for private in (
                    "storagebindingref",
                    "storagekey",
                    "internalpath",
                    "outputstoragekey",
                ):
                    self.assertNotIn(private, redacted)
                candidate_ref = created["renderCandidate"]["renderCandidateRef"]
                content_url = (
                    base_url
                    + collection
                    + "/"
                    + parse.quote(candidate_ref, safe="")
                    + "/content"
                )
                content_request = request.Request(
                    content_url,
                    headers={"Authorization": f"Bearer {token}"},
                )
                with request.urlopen(content_request, timeout=1800) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertTrue(
                        response.headers["Content-Disposition"].startswith("inline;")
                    )
                    inline_bytes = response.read()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

            first = stack.service.get_render_candidate(
                WORKSPACE, RUN, candidate_ref
            )
            first_candidate = first["renderCandidate"]
            self.assertEqual(
                sha256(inline_bytes).hexdigest(),
                first_candidate["fileDigest"].removeprefix("sha256:"),
            )
            self.assertEqual(
                (
                    first_candidate["mediaProbe"]["width"],
                    first_candidate["mediaProbe"]["height"],
                    first_candidate["mediaProbe"]["frameCount"],
                    first_candidate["mediaProbe"]["videoCodec"],
                    first_candidate["mediaProbe"]["audioCodec"],
                    first_candidate["mediaProbe"]["audioSampleRate"],
                    first_candidate["mediaProbe"]["audioChannels"],
                ),
                (704, 1280, 720, "h264", "aac", 48_000, 2),
            )
            self.assertIsNone(first["artifactEvidence"]["subtitleSidecar"])
            self.assertFalse(first["runtimeEvidence"]["gpuUsed"])
            self.assertFalse(first["runtimeEvidence"]["providerUsed"])
            self.assertFalse(first_candidate["publicationAllowed"])

            second = stack.service.create_render_candidate(
                candidate_command(burn_manifest, "full-second")
            )
            second_candidate = second["renderCandidate"]
            for field in (
                "fileDigest",
                "decodedFramePixelDigest",
                "pcmContentDigest",
                "subtitleTimingDigest",
                "timelineVersionDigest",
                "compositionVersionDigest",
                "renderManifestDigest",
            ):
                self.assertEqual(first_candidate[field], second_candidate[field])

            restarted, restarted_composition, _ = restart_stack(stack)
            replay = restarted.create_render_candidate(first_command)
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(replay["renderCandidate"], first_candidate)
            self.assertEqual(restarted_composition.preview_v3_requests, [])
            content = restarted.get_render_candidate_content(
                WORKSPACE, RUN, first_candidate["renderCandidateRef"]
            )
            with content["path"].open("ab") as stream:
                stream.write(b"tamper")
            with self.assertRaises(ArtifactRejectedError):
                restarted.get_render_candidate(
                    WORKSPACE, RUN, first_candidate["renderCandidateRef"]
                )

            elapsed = time.monotonic() - started
            print(
                "M13_R2_FULL_PERFORMANCE="
                + json.dumps(
                    {
                        "wallSeconds": round(elapsed, 3),
                        "peakRssKiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        "previewBytes": preview["compositionResult"]["outputByteSize"],
                        "renderBytes": first_candidate["byteSize"],
                    },
                    sort_keys=True,
                )
            )


if __name__ == "__main__":
    unittest.main()
