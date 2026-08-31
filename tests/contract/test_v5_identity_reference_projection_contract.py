from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
import unittest

from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    ExternalAuthorityConfigurationError,
    RejectingIdentityReferenceCurrentReader,
    StaticIdentityReferenceAuthority,
    create_in_memory_boundary,
    create_local_development_boundary,
    identity_reference_authority_from_environment,
)
from services.v5_core_os.episode_production.foundation import _digest
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    activate_k2_m6_baseline,
    g2_command,
    run_command,
    seed_k2_roots,
    sqlite_tables,
)


PROJECTION_SCHEMA = "v5.identity-reference-version-projection.v1"
PROJECTION_FIELDS = {
    "schemaVersion",
    "workspaceRef",
    "productionRunRef",
    "characterRef",
    "scriptCharacterName",
    "identityLockRef",
    "identityLockVersionRef",
    "identityLockDigest",
    "referenceRef",
    "referenceVersionRef",
    "contentDigest",
    "mediaType",
    "rightsState",
    "provenance",
    "approvalRef",
    "externalDecisionDigest",
    "projectionCheckedAt",
    "projectionDigest",
}


def _identity_decisions() -> dict[str, dict[str, str]]:
    def decision(character_ref: str, media_type: str) -> dict[str, str]:
        return {
            "referenceRef": f"identity-reference-{character_ref}",
            "referenceVersionRef": f"identity-reference-version-{character_ref}-1",
            "contentDigest": sha256(
                f"{character_ref}:local-reference:v1".encode()
            ).hexdigest(),
            "mediaType": media_type,
            "rightsState": "LOCAL_EVIDENCE_ONLY",
            "provenance": "LOCAL_EVIDENCE",
            "approvalRef": f"local-evidence-approval-{character_ref}",
        }

    return {
        "character-lin": decision("character-lin", "image"),
        "character-gu": decision("character-gu", "identity-direction"),
    }


def _write_identity_bundle(
    path: Path,
    run_ref: str,
    decisions: dict[str, dict[str, str]],
    *,
    authority_ref: str = "identity-authority-projection-contract-v1",
) -> tuple[dict[str, str], str]:
    bundle = {
        "schemaVersion": "v5.external-identity-reference-authority-bundle.v1",
        "authorityRef": authority_ref,
        "references": [
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": run_ref,
                "characterRef": character_ref,
                **deepcopy(decision),
            }
            for character_ref, decision in sorted(decisions.items())
        ],
    }
    payload = json.dumps(
        bundle,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    path.write_bytes(payload)
    digest = sha256(payload).hexdigest()
    return {
        "CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_PATH": str(path),
        "CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_SHA256": digest,
    }, digest


class MutableCurrentReader:
    def __init__(self, decisions: dict[str, dict[str, str]]) -> None:
        self.decisions = deepcopy(decisions)
        self.calls: list[dict[str, str]] = []
        self.on_first_call = None

    def require_current_reference(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        character_ref: str,
        locked_reference_ref: str,
        locked_reference_version_ref: str,
        locked_content_digest: str,
    ) -> dict[str, str]:
        self.calls.append(
            {
                "workspaceRef": workspace_ref,
                "productionRunRef": production_run_ref,
                "characterRef": character_ref,
                "lockedReferenceRef": locked_reference_ref,
                "lockedReferenceVersionRef": locked_reference_version_ref,
                "lockedContentDigest": locked_content_digest,
            }
        )
        if len(self.calls) == 1 and self.on_first_call is not None:
            self.on_first_call()
        try:
            return deepcopy(self.decisions[character_ref])
        except KeyError as exc:
            raise RuntimeError("unexpected current-reader character") from exc


class MutableClock:
    def __init__(self, value: str) -> None:
        self.value = value

    def __call__(self) -> str:
        return self.value


class DriftableM6Boundary:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.drift = False

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def get_m6_episode_baseline(self, *args, **kwargs):
        baseline = deepcopy(
            self.delegate.get_m6_episode_baseline(*args, **kwargs)
        )
        if self.drift:
            baseline["activationRevision"] += 1
            baseline["m6BaselineCanonicalDigest"] = "f" * 64
        return baseline


class IdentityReferenceProjectionContractTests(unittest.TestCase):
    def fixture(self, *, m6_wrapper: bool = False):
        assembly, refs, project, series, episode, generated = seed_k2_roots(
            with_m6_authority=True
        )
        activate_k2_m6_baseline(assembly, project, series)
        decisions = _identity_decisions()
        reader = MutableCurrentReader(decisions)
        clock = MutableClock("2026-08-31T07:30:00Z")
        script_boundary = (
            DriftableM6Boundary(assembly.script_studio)
            if m6_wrapper
            else assembly.script_studio
        )
        boundary = create_in_memory_boundary(
            project_boundary=assembly.project_context,
            series_episode_boundary=assembly.series_episode,
            series_planning_boundary=assembly.series_planning,
            script_studio_boundary=script_boundary,
            identity_reference_authority=StaticIdentityReferenceAuthority(decisions),
            identity_reference_current_reader=reader,
            ref_factory=refs,
            clock=clock,
        )
        run = boundary.create_run(run_command(project, series, episode))
        locked = boundary.authorize_and_lock(g2_command(run))
        return {
            "assembly": assembly,
            "refs": refs,
            "project": project,
            "series": series,
            "episode": episode,
            "generated": generated,
            "decisions": decisions,
            "reader": reader,
            "clock": clock,
            "scriptBoundary": script_boundary,
            "boundary": boundary,
            "run": run,
            "locked": locked,
        }

    @staticmethod
    def project(fixture, character_ref: str = "character-lin"):
        return fixture["boundary"].require_current_identity_reference_projection(
            WORKSPACE,
            fixture["run"]["productionRunRef"],
            character_ref,
        )

    def test_exact_projection_maps_existing_lock_and_fresh_external_decision(self):
        fixture = self.fixture()
        projection = self.project(fixture)
        identity_lock = fixture["locked"]["identityLock"]
        locked = next(
            item
            for item in identity_lock["identities"]
            if item["characterRef"] == "character-lin"
        )
        decision = fixture["decisions"]["character-lin"]

        self.assertEqual(set(projection), PROJECTION_FIELDS)
        self.assertEqual(projection["schemaVersion"], PROJECTION_SCHEMA)
        self.assertEqual(projection["workspaceRef"], WORKSPACE)
        self.assertEqual(
            projection["productionRunRef"], fixture["run"]["productionRunRef"]
        )
        self.assertEqual(projection["characterRef"], "character-lin")
        self.assertEqual(projection["scriptCharacterName"], "林澈")
        self.assertEqual(projection["identityLockRef"], identity_lock["identityLockRef"])
        self.assertEqual(
            projection["identityLockVersionRef"],
            identity_lock["identityLockVersionRef"],
        )
        self.assertEqual(projection["identityLockDigest"], identity_lock["payloadDigest"])
        self.assertEqual(
            {field: projection[field] for field in decision},
            locked["reference"],
        )
        self.assertEqual(projection["externalDecisionDigest"], _digest(decision))
        projection_base = {
            key: value
            for key, value in projection.items()
            if key not in {"projectionCheckedAt", "projectionDigest"}
        }
        self.assertEqual(projection["projectionDigest"], _digest(projection_base))
        matching_call = next(
            item
            for item in fixture["reader"].calls
            if item["characterRef"] == "character-lin"
        )
        self.assertEqual(
            matching_call,
            {
                "workspaceRef": WORKSPACE,
                "productionRunRef": fixture["run"]["productionRunRef"],
                "characterRef": "character-lin",
                "lockedReferenceRef": decision["referenceRef"],
                "lockedReferenceVersionRef": decision["referenceVersionRef"],
                "lockedContentDigest": decision["contentDigest"],
            },
        )
        self.assertEqual(
            {item["characterRef"] for item in fixture["reader"].calls},
            {"character-lin", "character-gu"},
        )

    def test_each_external_decision_field_drift_is_stale(self):
        cases = {
            "referenceRef": "identity-reference-character-lin-drifted",
            "referenceVersionRef": "identity-reference-version-character-lin-2",
            "contentDigest": "e" * 64,
            "mediaType": "video",
            "rightsState": "APPROVED",
            "provenance": "AUTHORITY_APPROVED",
            "approvalRef": "local-evidence-approval-character-lin-drifted",
        }
        for field, changed_value in cases.items():
            with self.subTest(field=field):
                fixture = self.fixture()
                fixture["reader"].decisions["character-lin"][field] = changed_value
                with self.assertRaises(EpisodeProductionPublicError) as caught:
                    self.project(fixture)
                self.assertEqual(
                    (caught.exception.status, caught.exception.code),
                    (409, "stale_input"),
                )

    def test_missing_reader_unknown_character_and_foreign_workspace_fail_closed(self):
        assembly, refs, project, series, episode, _ = seed_k2_roots(
            with_m6_authority=True
        )
        activate_k2_m6_baseline(assembly, project, series)
        decisions = _identity_decisions()
        boundary = create_in_memory_boundary(
            project_boundary=assembly.project_context,
            series_episode_boundary=assembly.series_episode,
            series_planning_boundary=assembly.series_planning,
            script_studio_boundary=assembly.script_studio,
            identity_reference_authority=StaticIdentityReferenceAuthority(decisions),
            identity_reference_current_reader=RejectingIdentityReferenceCurrentReader(),
            ref_factory=refs,
            clock=lambda: "2026-08-31T07:30:00Z",
        )
        run = boundary.create_run(run_command(project, series, episode))
        boundary.authorize_and_lock(g2_command(run))
        with self.assertRaises(EpisodeProductionPublicError) as missing:
            boundary.require_current_identity_reference_projection(
                WORKSPACE, run["productionRunRef"], "character-lin"
            )
        self.assertEqual(
            (missing.exception.status, missing.exception.code),
            (403, "authority_required"),
        )

        fixture = self.fixture()
        with self.assertRaises(EpisodeProductionPublicError) as unknown:
            self.project(fixture, "character-unknown")
        self.assertEqual(
            (unknown.exception.status, unknown.exception.code),
            (404, "not_found"),
        )
        with self.assertRaises(EpisodeProductionPublicError) as foreign:
            fixture["boundary"].require_current_identity_reference_projection(
                "workspace-other",
                fixture["run"]["productionRunRef"],
                "character-lin",
            )
        self.assertEqual(
            (foreign.exception.status, foreign.exception.code),
            (404, "not_found"),
        )

    def test_projection_digest_is_repeatable_and_checked_at_is_non_content(self):
        fixture = self.fixture()
        first = self.project(fixture)
        fixture["clock"].value = "2026-08-31T08:45:00Z"
        second = self.project(fixture)
        self.assertNotEqual(first["projectionCheckedAt"], second["projectionCheckedAt"])
        self.assertEqual(first["externalDecisionDigest"], second["externalDecisionDigest"])
        self.assertEqual(first["projectionDigest"], second["projectionDigest"])
        first_without_time = {
            key: value for key, value in first.items() if key != "projectionCheckedAt"
        }
        second_without_time = {
            key: value for key, value in second.items() if key != "projectionCheckedAt"
        }
        self.assertEqual(first_without_time, second_without_time)

    def test_projection_and_authorization_replay_do_not_mutate_identity_lock_v1(self):
        fixture = self.fixture()
        original = deepcopy(fixture["locked"]["identityLock"])
        first = self.project(fixture)
        second = self.project(fixture)
        replay = fixture["boundary"].authorize_and_lock(g2_command(fixture["run"]))
        restored = fixture["boundary"].get_authority_identity(
            WORKSPACE, fixture["run"]["productionRunRef"]
        )["identityLock"]

        self.assertEqual(original["schemaVersion"], "v5.identity-lock.v1")
        self.assertEqual(first, second)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["identityLock"], original)
        self.assertEqual(restored, original)
        self.assertEqual(restored["payloadDigest"], original["payloadDigest"])

    def test_root_and_m6_currentness_regressions_remain_fail_closed(self):
        root_fixture = self.fixture()
        content = {
            key: deepcopy(root_fixture["generated"]["scriptVersion"][key])
            for key in (
                "title",
                "logline",
                "synopsis",
                "targetDurationSec",
                "scenes",
            )
        }
        content["scenes"][1]["action"] += " 身份投影前再次变更。"
        changed = root_fixture["assembly"].script_studio.create_version(
            {
                "workspaceRef": WORKSPACE,
                "seriesRef": root_fixture["series"]["seriesRef"],
                "episodeRef": root_fixture["episode"]["episodeRef"],
                "scriptRef": root_fixture["generated"]["script"]["scriptRef"],
                "baseScriptVersionRef": root_fixture["generated"]["scriptVersion"][
                    "scriptVersionRef"
                ],
                "changeKind": "manual-edit",
                "content": content,
            }
        )
        root_fixture["assembly"].script_studio.confirm_version(
            {
                "workspaceRef": WORKSPACE,
                "seriesRef": root_fixture["series"]["seriesRef"],
                "episodeRef": root_fixture["episode"]["episodeRef"],
                "scriptRef": changed["script"]["scriptRef"],
                "scriptVersionRef": changed["scriptVersion"]["scriptVersionRef"],
                "humanConfirmed": True,
            }
        )
        with self.assertRaises(EpisodeProductionPublicError) as root_stale:
            self.project(root_fixture)
        self.assertEqual(
            (root_stale.exception.status, root_stale.exception.code),
            (409, "stale_input"),
        )

        m6_fixture = self.fixture(m6_wrapper=True)
        m6_fixture["scriptBoundary"].drift = True
        with self.assertRaises(EpisodeProductionPublicError) as m6_stale:
            self.project(m6_fixture)
        self.assertEqual(
            (m6_stale.exception.status, m6_stale.exception.code),
            (409, "stale_input"),
        )

    def test_reader_triggered_m6_drift_is_rejected_by_final_reread(self):
        fixture = self.fixture(m6_wrapper=True)
        fixture["reader"].on_first_call = lambda: setattr(
            fixture["scriptBoundary"],
            "drift",
            True,
        )

        with self.assertRaises(EpisodeProductionPublicError) as stale:
            self.project(fixture)
        self.assertEqual(
            (stale.exception.status, stale.exception.code),
            (409, "stale_input"),
        )
        self.assertGreaterEqual(len(fixture["reader"].calls), 1)

    def test_malformed_current_decision_fields_are_stale(self):
        for shape in ("missing", "extra"):
            with self.subTest(shape=shape):
                fixture = self.fixture()
                if shape == "missing":
                    fixture["reader"].decisions["character-lin"].pop(
                        "approvalRef"
                    )
                else:
                    fixture["reader"].decisions["character-lin"][
                        "identityVersionRef"
                    ] = "caller-forged-identity-version"

                with self.assertRaises(EpisodeProductionPublicError) as stale:
                    self.project(fixture)
                self.assertEqual(
                    (stale.exception.status, stale.exception.code),
                    (409, "stale_input"),
                )

    def test_current_reader_runtime_failure_is_repository_unavailable(self):
        fixture = self.fixture()

        def fail_reader():
            raise RuntimeError("external current reader failed")

        fixture["reader"].on_first_call = fail_reader
        with self.assertRaises(EpisodeProductionPublicError) as unavailable:
            self.project(fixture)
        self.assertEqual(
            (unavailable.exception.status, unavailable.exception.code),
            (503, "episode_production_unavailable"),
        )

    def test_current_pin_configuration_and_duplicate_scope_fail_closed(self):
        decisions = _identity_decisions()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_path = root / "identity-authority.json"
            environment, digest = _write_identity_bundle(
                bundle_path,
                "production-run-pin-contract",
                decisions,
            )
            path_key = "CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_PATH"
            digest_key = "CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_SHA256"
            invalid_configurations = {
                "path-only": {path_key: str(bundle_path)},
                "digest-only": {digest_key: digest},
                "missing-file": {
                    path_key: str(root / "missing-identity-authority.json"),
                    digest_key: digest,
                },
                "relative-path": {
                    path_key: "identity-authority.json",
                    digest_key: digest,
                },
            }
            for case, configuration in invalid_configurations.items():
                with self.subTest(case=case):
                    with self.assertRaises(ExternalAuthorityConfigurationError):
                        identity_reference_authority_from_environment(
                            configuration
                        )

            duplicate_scope_bundle = json.loads(
                bundle_path.read_text(encoding="utf-8")
            )
            duplicate_scope_bundle["references"].append(
                deepcopy(duplicate_scope_bundle["references"][0])
            )
            duplicate_payload = json.dumps(
                duplicate_scope_bundle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            bundle_path.write_bytes(duplicate_payload)
            duplicate_environment = dict(environment)
            duplicate_environment[digest_key] = sha256(
                duplicate_payload
            ).hexdigest()
            with self.assertRaises(ExternalAuthorityConfigurationError):
                identity_reference_authority_from_environment(
                    duplicate_environment
                )

    def test_sqlite_restart_requires_fresh_reader_and_adds_no_identity_table(self):
        assembly, _, project, series, episode, _ = seed_k2_roots(
            with_m6_authority=True
        )
        activate_k2_m6_baseline(assembly, project, series)
        decisions = _identity_decisions()
        reader = MutableCurrentReader(decisions)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-production.sqlite3"
            evidence = Path(directory) / "episode-evidence.sqlite3"

            def boundary(*, current_reader, include_authority: bool = True):
                return create_local_development_boundary(
                    database,
                    project_boundary=assembly.project_context,
                    series_episode_boundary=assembly.series_episode,
                    series_planning_boundary=assembly.series_planning,
                    script_studio_boundary=assembly.script_studio,
                    evidence_database_path=evidence,
                    identity_reference_authority=(
                        StaticIdentityReferenceAuthority(decisions)
                        if include_authority
                        else None
                    ),
                    identity_reference_current_reader=current_reader,
                    clock=lambda: "2026-08-31T09:00:00Z",
                )

            first_boundary = boundary(current_reader=reader)
            run = first_boundary.create_run(run_command(project, series, episode))
            locked = first_boundary.authorize_and_lock(g2_command(run))["identityLock"]

            restarted = boundary(current_reader=reader)
            projection = restarted.require_current_identity_reference_projection(
                WORKSPACE, run["productionRunRef"], "character-lin"
            )
            self.assertEqual(projection["identityLockDigest"], locked["payloadDigest"])

            missing_reader = boundary(
                current_reader=None,
                include_authority=False,
            )
            with self.assertRaises(EpisodeProductionPublicError) as missing:
                missing_reader.require_current_identity_reference_projection(
                    WORKSPACE, run["productionRunRef"], "character-lin"
                )
            self.assertEqual(
                (missing.exception.status, missing.exception.code),
                (403, "authority_required"),
            )

            reader.decisions["character-lin"]["contentDigest"] = "d" * 64
            drifted = boundary(current_reader=reader)
            with self.assertRaises(EpisodeProductionPublicError) as stale:
                drifted.require_current_identity_reference_projection(
                    WORKSPACE, run["productionRunRef"], "character-lin"
                )
            self.assertEqual(
                (stale.exception.status, stale.exception.code),
                (409, "stale_input"),
            )
            self.assertEqual(
                {row[0] for row in sqlite_tables(database)},
                {"v5_episode_production_schema", "v5_episode_production_runs"},
            )
            self.assertEqual(
                {row[0] for row in sqlite_tables(evidence)},
                {
                    "v5_episode_production_evidence_schema",
                    "v5_episode_production_gates",
                    "v5_episode_production_facts",
                    "v5_episode_production_transitions",
                    "v5_episode_production_records",
                },
            )

    def test_sqlite_restart_reloads_digest_pinned_environment_bundle(self):
        assembly, _, project, series, episode, _ = seed_k2_roots(
            with_m6_authority=True
        )
        activate_k2_m6_baseline(assembly, project, series)
        decisions = _identity_decisions()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "episode-production.sqlite3"
            evidence = root / "episode-evidence.sqlite3"
            bundle_path = root / "identity-authority.json"

            def boundary(authority=None):
                current_reader = (
                    authority
                    if callable(
                        getattr(authority, "require_current_reference", None)
                    )
                    else None
                )
                return create_local_development_boundary(
                    database,
                    project_boundary=assembly.project_context,
                    series_episode_boundary=assembly.series_episode,
                    series_planning_boundary=assembly.series_planning,
                    script_studio_boundary=assembly.script_studio,
                    evidence_database_path=evidence,
                    identity_reference_authority=authority,
                    identity_reference_current_reader=current_reader,
                    clock=lambda: "2026-08-31T09:30:00Z",
                )

            roots_only = boundary()
            run = roots_only.create_run(run_command(project, series, episode))
            environment, pinned_digest = _write_identity_bundle(
                bundle_path,
                run["productionRunRef"],
                decisions,
            )
            initial_authority = identity_reference_authority_from_environment(
                environment
            )
            locked_boundary = boundary(initial_authority)
            locked = locked_boundary.authorize_and_lock(g2_command(run))["identityLock"]

            reloaded_environment, reloaded_digest = _write_identity_bundle(
                bundle_path,
                run["productionRunRef"],
                decisions,
            )
            self.assertEqual(reloaded_digest, pinned_digest)
            reloaded_authority = identity_reference_authority_from_environment(
                reloaded_environment
            )
            self.assertIsNot(reloaded_authority, initial_authority)
            restarted = boundary(reloaded_authority)
            projection = restarted.require_current_identity_reference_projection(
                WORKSPACE,
                run["productionRunRef"],
                "character-lin",
            )
            self.assertEqual(projection["identityLockDigest"], locked["payloadDigest"])

            repacked_environment, repacked_digest = _write_identity_bundle(
                bundle_path,
                run["productionRunRef"],
                decisions,
                authority_ref="identity-authority-projection-contract-v2",
            )
            self.assertNotEqual(repacked_digest, pinned_digest)
            repacked = boundary(
                identity_reference_authority_from_environment(
                    repacked_environment
                )
            ).require_current_identity_reference_projection(
                WORKSPACE,
                run["productionRunRef"],
                "character-lin",
            )
            self.assertEqual(
                repacked["externalDecisionDigest"],
                projection["externalDecisionDigest"],
            )

            decisions_with_unrelated_entry = deepcopy(decisions)
            decisions_with_unrelated_entry["character-unrelated"] = {
                "referenceRef": "identity-reference-character-unrelated",
                "referenceVersionRef": (
                    "identity-reference-version-character-unrelated-1"
                ),
                "contentDigest": sha256(
                    b"character-unrelated:local-reference:v1"
                ).hexdigest(),
                "mediaType": "image",
                "rightsState": "LOCAL_EVIDENCE_ONLY",
                "provenance": "LOCAL_EVIDENCE",
                "approvalRef": (
                    "local-evidence-approval-character-unrelated"
                ),
            }
            unrelated_environment, unrelated_digest = _write_identity_bundle(
                bundle_path,
                run["productionRunRef"],
                decisions_with_unrelated_entry,
                authority_ref="identity-authority-projection-contract-v3",
            )
            self.assertNotEqual(unrelated_digest, repacked_digest)
            unrelated = boundary(
                identity_reference_authority_from_environment(
                    unrelated_environment
                )
            ).require_current_identity_reference_projection(
                WORKSPACE,
                run["productionRunRef"],
                "character-lin",
            )
            self.assertEqual(
                unrelated["projectionDigest"],
                projection["projectionDigest"],
            )

            unavailable = boundary(identity_reference_authority_from_environment({}))
            with self.assertRaises(EpisodeProductionPublicError) as missing:
                unavailable.require_current_identity_reference_projection(
                    WORKSPACE,
                    run["productionRunRef"],
                    "character-lin",
                )
            self.assertEqual(
                (missing.exception.status, missing.exception.code),
                (403, "authority_required"),
            )

            drift_cases = {
                "referenceVersionRef": {
                    "referenceVersionRef": "identity-reference-version-character-lin-2"
                },
                "contentDigest": {"contentDigest": "d" * 64},
                "approvalRef": {
                    "approvalRef": "local-evidence-approval-character-lin-v2"
                },
                "rightsState-and-provenance": {
                    "rightsState": "APPROVED",
                    "provenance": "AUTHORITY_APPROVED",
                },
            }
            for field, changes in drift_cases.items():
                with self.subTest(field=field):
                    drifted_decisions = deepcopy(decisions)
                    drifted_decisions["character-lin"].update(changes)
                    drifted_environment, drifted_digest = _write_identity_bundle(
                        bundle_path,
                        run["productionRunRef"],
                        drifted_decisions,
                    )
                    self.assertNotEqual(drifted_digest, pinned_digest)

                    stale_pin = dict(drifted_environment)
                    stale_pin[
                        "CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_SHA256"
                    ] = pinned_digest
                    with self.assertRaises(ExternalAuthorityConfigurationError):
                        identity_reference_authority_from_environment(stale_pin)

                    drifted_authority = (
                        identity_reference_authority_from_environment(
                            drifted_environment
                        )
                    )
                    drifted = boundary(drifted_authority)
                    with self.assertRaises(EpisodeProductionPublicError) as stale:
                        drifted.require_current_identity_reference_projection(
                            WORKSPACE,
                            run["productionRunRef"],
                            "character-lin",
                        )
                    self.assertEqual(
                        (stale.exception.status, stale.exception.code),
                        (409, "stale_input"),
                    )

    def test_projection_creates_no_identity_repository_or_creator_http_route(self):
        repo_root = Path(__file__).resolve().parents[2]
        episode_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(
                (repo_root / "services/v5_core_os/episode_production").glob("*.py")
            )
        )
        self.assertIsNone(
            re.search(
                r"class\s+\w*Identity(?:Reference|Version|Projection)\w*"
                r"(?:Repository|Adapter)\b",
                episode_sources,
            )
        )
        for relative in (
            "apps/creator_workspace_mvp/server.py",
            "apps/creator_workspace_mvp/public_contract.py",
        ):
            source = (repo_root / relative).read_text(encoding="utf-8")
            self.assertNotIn("identity-reference-version-projection", source)
            self.assertNotIn("identity-reference-projection", source)
            self.assertNotIn(
                "require_current_identity_reference_projection",
                source,
            )


if __name__ == "__main__":
    unittest.main()
