from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from services.v5_core_os.episode_production.evidence import (
    EvidenceRecord,
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
)
from tests.integration.m13_e3_support import (
    CREATED_AT,
    CurrentIdentityProjectionReader,
    CurrentScriptTextReader,
    admit_canonical_font,
    canonical_mark_asset,
    restart_font_authority,
)
from tests.integration.test_m13_e1_timeline_v3_preview import (
    _register_inputs,
    _seed_real_video_ready,
    _insert_and_bind_timeline,
)
from tests.integration.test_m13_e2_timeline_v3_preview import (
    _append_e2_profile,
)
from tests.integration.test_m13_e3_timeline_v3_preview import (
    _authority,
    _face_command,
    _insert_and_bind_e3,
    _nameplate_command,
    _service,
    _source,
)


class _IdentityDecisionDriftReader(CurrentIdentityProjectionReader):
    """Change one of the exact seven decision fields on the second read."""

    def __init__(self, run, field: str, value: str) -> None:
        super().__init__(run)
        self.field = field
        self.value = value

    def require_current_identity_reference_projection(
        self,
        workspace_ref: str,
        production_run_ref: str,
        character_ref: str,
    ):
        if len(self.calls) == 1:
            self.decision[self.field] = self.value
        return super().require_current_identity_reference_projection(
            workspace_ref, production_run_ref, character_ref
        )


class _SecondReadScriptDrift(CurrentScriptTextReader):
    def get_workspace(
        self, workspace_ref: str, series_ref: str, episode_ref: str
    ):
        if len(self.calls) == 1:
            self.version = {
                **self.version,
                "title": "洛阳",
            }
        return super().get_workspace(workspace_ref, series_ref, episode_ref)


class _FontProjectionDriftAuthority:
    """Return a closed current projection, then alter one current fact."""

    def __init__(self, delegate, drift: str, *, start_at_call: int) -> None:
        self.delegate = delegate
        self.drift = drift
        self.start_at_call = start_at_call
        self.calls = 0

    def require_current_font_asset_projection(self, *args, **kwargs):
        self.calls += 1
        projection = self.delegate.require_current_font_asset_projection(
            *args, **kwargs
        )
        if self.calls < self.start_at_call:
            return projection
        value = deepcopy(projection)
        if self.drift == "file":
            value["fontAssetVersion"]["fileDigest"] = "f" * 64
        elif self.drift == "validation":
            value["fontTechnicalValidation"]["payloadDigest"] = "e" * 64
        elif self.drift == "license":
            value["fontLicenseBindingVersion"]["payloadDigest"] = "d" * 64
        else:  # pragma: no cover - test construction is closed above.
            raise AssertionError(f"unsupported FONT drift {self.drift}")
        return value

    def __getattr__(self, name):
        return getattr(self.delegate, name)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13E3CurrentnessIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="m13-e3-current-")
        cls.root = Path(cls.temporary.name)
        cls.artifact_root = cls.root / "artifacts"
        raw_inputs = _source(cls.artifact_root)
        run, storyboard, graph = _authority(raw_inputs)
        cls.inputs = type(raw_inputs)(
            audio=raw_inputs.audio,
            base=raw_inputs.base,
            masks=raw_inputs.masks,
            inspection=raw_inputs.inspection,
            requirement=raw_inputs.requirement,
            run=run,
        )
        cls.production_run = run
        cls.storyboard = storyboard
        cls.graph = graph
        cls.mark = canonical_mark_asset(
            run=run, base=cls.inputs.base, source=cls.inputs.masks[4]
        )
        cls._completed = None

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _new_case(
        self,
        slug: str,
        *,
        identity_reader=None,
        script_reader=None,
        font_drift: tuple[str, int] | None = None,
    ):
        repository = SqliteEpisodeProductionEvidenceAdapter(
            self.root / f"{slug}.sqlite3", initialize_if_missing=True
        )
        _seed_real_video_ready(
            repository, self.production_run, self.storyboard, self.graph
        )
        font_fixture = admit_canonical_font(
            run=self.production_run, evidence=repository
        )
        font_authority = font_fixture.service
        if font_drift is not None:
            font_authority = _FontProjectionDriftAuthority(
                font_authority,
                font_drift[0],
                start_at_call=font_drift[1],
            )
        identity = (
            identity_reader
            if identity_reader is not None
            else CurrentIdentityProjectionReader(self.production_run)
        )
        script = (
            script_reader
            if script_reader is not None
            else CurrentScriptTextReader(self.production_run)
        )
        service, composition = _service(
            artifact_root=self.artifact_root,
            repository=repository,
            inputs=self.inputs,
            run=self.production_run,
            graph=self.graph,
            mark=self.mark,
            identity_reader=identity,
            script_reader=script,
            font_authority=font_authority,
        )
        _register_inputs(service, self.inputs)
        return (
            repository,
            font_fixture,
            identity,
            script,
            service,
            composition,
        )

    def _assert_pre_execution_rejection(
        self, repository, composition, command
    ) -> None:
        before = repository.list_records(
            self.production_run["workspaceRef"], self.production_run["productionRunRef"]
        )
        with self.assertRaises(EpisodeProductionError):
            command()
        after = repository.list_records(
            self.production_run["workspaceRef"], self.production_run["productionRunRef"]
        )
        self.assertEqual(composition.overlay_calls, [])
        self.assertEqual(after, before)

    def test_identity_exact_seven_field_drift_is_rejected_before_v4_or_journal(
        self,
    ) -> None:
        cases = {
            "referenceRef": "identity-reference-character-lin-v2",
            "referenceVersionRef": "identity-reference-version-character-lin-2",
            "contentDigest": "a" * 64,
            "mediaType": "video",
            "rightsState": "APPROVED",
            "provenance": "AUTHORITY_APPROVED",
            "approvalRef": "local-evidence-approval-character-lin-v2",
        }
        for index, (field, value) in enumerate(cases.items()):
            with self.subTest(field=field):
                reader = _IdentityDecisionDriftReader(
                    self.production_run, field, value
                )
                repository, _, _, _, service, composition = self._new_case(
                    f"identity-{index}", identity_reader=reader
                )
                self._assert_pre_execution_rejection(
                    repository,
                    composition,
                    lambda: service.execute_deterministic_effect(
                        _face_command(self.production_run, self.inputs.base, self.mark)
                    ),
                )
                self.assertEqual(len(reader.calls), 2)

    def test_script_font_and_mark_drift_are_rejected_before_v4_or_journal(
        self,
    ) -> None:
        script = _SecondReadScriptDrift(self.production_run)
        repository, font_fixture, _, _, service, composition = self._new_case(
            "script", script_reader=script
        )
        self._assert_pre_execution_rejection(
            repository,
            composition,
            lambda: service.execute_deterministic_effect(
                _nameplate_command(
                    self.production_run,
                    self.inputs.base,
                    font_fixture.asset,
                )
            ),
        )
        self.assertEqual(len(script.calls), 2)

        repository, font_fixture, _, _, service, composition = self._new_case(
            "font", font_drift=("license", 2)
        )
        font_authority = service.font_asset_authority
        self._assert_pre_execution_rejection(
            repository,
            composition,
            lambda: service.execute_deterministic_effect(
                _nameplate_command(
                    self.production_run, self.inputs.base, font_fixture.asset
                )
            ),
        )
        self.assertEqual(font_authority.calls, 2)

        repository, _, _, _, service, composition = self._new_case("mark")
        inspect = composition.inspect_deterministic_overlay_image
        calls = 0

        def drifting_mark(asset):
            nonlocal calls
            calls += 1
            measured = inspect(asset)
            if calls == 2:
                measured = deepcopy(measured)
                measured["pixelDigest"] = "sha256:" + "b" * 64
            return measured

        composition.inspect_deterministic_overlay_image = drifting_mark
        self._assert_pre_execution_rejection(
            repository,
            composition,
            lambda: service.execute_deterministic_effect(
                _face_command(self.production_run, self.inputs.base, self.mark)
            ),
        )
        self.assertEqual(calls, 2)

    def _completed_case(self):
        if self.__class__._completed is not None:
            return self.__class__._completed
        (
            repository,
            font_fixture,
            identity,
            script,
            service,
            composition,
        ) = self._new_case("completed")
        smoke_layer = deepcopy(self.inputs.masks[3])
        smoke_layer.pop("payloadDigest")
        smoke_layer["assetVersionRef"] = (
            "asset-version-m13-e3-currentness-smoke-layer"
        )
        smoke_layer["payloadDigest"] = _digest(smoke_layer)
        repository.append_record(
            EvidenceRecord(
                workspaceRef=self.production_run["workspaceRef"],
                productionRunRef=self.production_run["productionRunRef"],
                recordKind="MaskAssetVersion",
                recordRef=smoke_layer["assetVersionRef"],
                recordVersion=1,
                idempotencyKey="m13-e3-currentness-smoke-layer",
                requestDigest=_digest(
                    {"smokeLayer": smoke_layer["payloadDigest"]}
                ),
                createdAt=CREATED_AT,
                payload=smoke_layer,
                payloadDigest=smoke_layer["payloadDigest"],
            )
        )
        e2_chains, _ = _append_e2_profile(
            self.artifact_root,
            repository,
            service,
            self.inputs,
            smoke_layer,
        )
        e2_timeline = _insert_and_bind_timeline(
            service, self.inputs, self.production_run, e2_chains
        )
        nameplate_command = _nameplate_command(
            self.production_run, self.inputs.base, font_fixture.asset
        )
        face_command = _face_command(self.production_run, self.inputs.base, self.mark)
        nameplate = service.execute_deterministic_effect(nameplate_command)
        face = service.execute_deterministic_effect(face_command)
        current, _ = _insert_and_bind_e3(
            service,
            self.production_run,
            e2_timeline,
            [
                nameplate["deterministicEffect"],
                face["deterministicEffect"],
            ],
        )
        self.__class__._completed = {
            "repository": repository,
            "database": self.root / "completed.sqlite3",
            "font": font_fixture,
            "current": current,
            "faceCommand": face_command,
        }
        return self.__class__._completed

    def test_restart_execute_requires_external_identity_reader(self) -> None:
        completed = self._completed_case()
        repository = SqliteEpisodeProductionEvidenceAdapter(
            completed["database"], initialize_if_missing=False
        )
        font_authority = restart_font_authority(
            run=self.production_run,
            evidence=repository,
            fixture=completed["font"],
        )
        service, composition = _service(
            artifact_root=self.artifact_root,
            repository=repository,
            inputs=self.inputs,
            run=self.production_run,
            graph=self.graph,
            mark=self.mark,
            identity_reader=None,
            script_reader=CurrentScriptTextReader(self.production_run),
            font_authority=font_authority,
        )
        _register_inputs(service, self.inputs)
        before = repository.list_records(
            self.production_run["workspaceRef"], self.production_run["productionRunRef"]
        )
        with self.assertRaises(UpstreamNotReadyError):
            service.execute_deterministic_effect(completed["faceCommand"])
        self.assertEqual(composition.overlay_calls, [])
        self.assertEqual(
            repository.list_records(
                self.production_run["workspaceRef"], self.production_run["productionRunRef"]
            ),
            before,
        )

    def test_preview_revalidates_font_file_validation_and_license_drift(
        self,
    ) -> None:
        completed = self._completed_case()
        command = {
            "workspaceRef": self.production_run["workspaceRef"],
            "productionRunRef": self.production_run["productionRunRef"],
            "operationRef": "m13-e3-currentness-preview-compose",
            "idempotencyKey": "m13-e3-currentness-preview-compose-key",
            "expectedRunVersion": 1,
            "expectedEvidenceRevision": completed["current"][
                "evidenceRevision"
            ],
            "timelineVersionRef": completed["current"]["timelineVersion"][
                "timelineVersionRef"
            ],
            "timelineVersionDigest": completed["current"]["timelineVersion"][
                "payloadDigest"
            ],
        }
        for drift in ("file", "validation", "license"):
            with self.subTest(drift=drift):
                repository = SqliteEpisodeProductionEvidenceAdapter(
                    completed["database"], initialize_if_missing=False
                )
                current_font = restart_font_authority(
                    run=self.production_run,
                    evidence=repository,
                    fixture=completed["font"],
                )
                font_authority = _FontProjectionDriftAuthority(
                    current_font, drift, start_at_call=1
                )
                service, _ = _service(
                    artifact_root=self.artifact_root,
                    repository=repository,
                    inputs=self.inputs,
                    run=self.production_run,
                    graph=self.graph,
                    mark=self.mark,
                    identity_reader=CurrentIdentityProjectionReader(self.production_run),
                    script_reader=CurrentScriptTextReader(self.production_run),
                    font_authority=font_authority,
                )
                _register_inputs(service, self.inputs)
                before = repository.list_records(
                    self.production_run["workspaceRef"], self.production_run["productionRunRef"]
                )
                with self.assertRaises(EpisodeProductionError):
                    service.compose_and_qc(command)
                after = repository.list_records(
                    self.production_run["workspaceRef"], self.production_run["productionRunRef"]
                )
                self.assertEqual(after, before)
                self.assertFalse(
                    {
                        "CompositionResult",
                        "PreviewCandidate",
                    }.intersection(item["recordKind"] for item in after)
                )


if __name__ == "__main__":
    unittest.main()
