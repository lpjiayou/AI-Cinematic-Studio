from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest

from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    StaleInputError,
)
from services.v5_core_os.episode_production.voice import (
    CLONE_VOICE_ENGINE_FAMILY,
    CLONE_VOICE_MODEL_ID,
    InMemoryVoiceLockAdapter,
    K2VoiceLockService,
    SqliteVoiceLockAdapter,
    VOICE_LOCK_SCHEMA_VERSION,
    VOICE_LOCK_VERSION_SCHEMA_VERSION,
    VOICE_LOCK_VERSION_V2_SCHEMA_VERSION,
    VoiceLockNotConfirmedError,
    validate_confirmed_clone_voice_lock_bundle,
    validate_confirmed_voice_lock_bundle,
)


SCOPE = {
    "workspaceRef": "workspace-voice-v2",
    "projectRef": "project-voice-v2",
    "seriesRef": "series-voice-v2",
}


class Refs:
    def __init__(self, *, version_count: int = 0) -> None:
        self.counts = {"voice-lock-version": version_count}

    def __call__(self, prefix: str) -> str:
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}-{self.counts[prefix]}"


def fixed_command(key: str) -> dict:
    return {
        **SCOPE,
        "characterRef": "character-zhen",
        "engineFamily": "local-neural-tts-v1",
        "voiceId": "fixed-voice-zhen",
        "gender": "female",
        "apparentAge": 31,
        "pitchSemitones": -1.0,
        "rateScale": 0.96,
        "timbreDescriptor": "stable fixed identity",
        "languageCode": "zh-CN",
        "idempotencyKey": key,
    }


def confirm_command(candidate: dict, key: str) -> dict:
    return {
        **SCOPE,
        "voiceRef": candidate["voiceLock"]["voiceRef"],
        "voiceLockVersionRef": candidate["voiceLockVersion"][
            "voiceLockVersionRef"
        ],
        "voiceLockDigest": candidate["voiceLockVersion"]["payloadDigest"],
        "expectedRevision": candidate["voiceLock"]["revision"],
        "idempotencyKey": key,
    }


def clone_command(
    confirmed_parent: dict,
    key: str,
    *,
    source_suffix: str = "a",
) -> dict:
    parent = confirmed_parent["voiceLockVersion"]
    identity_version_ref = (
        parent["voiceIdentityVersionRef"]
        if parent["schemaVersion"] == VOICE_LOCK_VERSION_V2_SCHEMA_VERSION
        else parent["voiceLockVersionRef"]
    )
    identity_digest = (
        parent["voiceIdentityDigest"]
        if parent["schemaVersion"] == VOICE_LOCK_VERSION_V2_SCHEMA_VERSION
        else parent["payloadDigest"]
    )
    return {
        **SCOPE,
        "voiceRef": confirmed_parent["voiceLock"]["voiceRef"],
        "baseVoiceLockVersionRef": parent["voiceLockVersionRef"],
        "baseVoiceLockDigest": parent["payloadDigest"],
        "expectedRevision": confirmed_parent["voiceLock"]["revision"],
        "sourceRecordingBindingRef": f"source-binding-{source_suffix}",
        "sourceRecordingBindingDigest": "1" * 64,
        "consentGrantVersionRef": f"consent-version-{source_suffix}",
        "consentGrantVersionDigest": "2" * 64,
        "rightsBindingRef": f"rights-binding-{source_suffix}",
        "rightsBindingDigest": "3" * 64,
        "voiceIdentityRef": confirmed_parent["voiceLock"]["voiceRef"],
        "voiceIdentityVersionRef": identity_version_ref,
        "voiceIdentityDigest": identity_digest,
        "subjectRef": "subject-zhen",
        "engineFamily": CLONE_VOICE_ENGINE_FAMILY,
        "voiceId": CLONE_VOICE_MODEL_ID,
        "gender": "female",
        "apparentAge": 31,
        "pitchSemitones": -1.0,
        "rateScale": 0.96,
        "timbreDescriptor": "consent-bound clone identity",
        "languageCode": "zh-CN",
        "idempotencyKey": key,
    }


def confirmed_v1(service: K2VoiceLockService) -> dict:
    created = service.create_voice_lock(fixed_command("create-fixed"))
    return service.confirm_voice_lock(confirm_command(created, "confirm-fixed"))


class VoiceLockV2ContractMixin:
    def make_repository(self):
        raise NotImplementedError

    def make_service(self, repository, *, version_count: int = 0):
        return K2VoiceLockService(
            repository,
            ref_factory=Refs(version_count=version_count),
            clock=lambda: "2026-08-30T10:00:00Z",
        )

    def test_v1_and_v2_share_root_sequence_cas_and_exact_consumers(self):
        service = self.make_service(self.make_repository())
        v1 = confirmed_v1(service)
        with self.assertRaises(VoiceLockNotConfirmedError):
            service.get_confirmed_clone_voice_lock(
                SCOPE["workspaceRef"],
                SCOPE["projectRef"],
                SCOPE["seriesRef"],
                v1["voiceLock"]["voiceRef"],
            )
        candidate = service.create_clone_voice_lock_version(
            clone_command(v1, "create-clone-v2")
        )
        self.assertEqual(candidate["voiceLock"]["schemaVersion"], VOICE_LOCK_SCHEMA_VERSION)
        self.assertEqual(
            candidate["voiceLock"]["voiceRef"], v1["voiceLock"]["voiceRef"]
        )
        self.assertEqual(
            candidate["voiceLockVersion"]["schemaVersion"],
            VOICE_LOCK_VERSION_V2_SCHEMA_VERSION,
        )
        self.assertEqual(candidate["voiceLockVersion"]["versionNumber"], 2)
        self.assertEqual(
            candidate["voiceLockVersion"]["parentVoiceLockVersionRef"],
            v1["voiceLockVersion"]["voiceLockVersionRef"],
        )
        self.assertEqual(
            candidate["voiceLock"]["revision"], v1["voiceLock"]["revision"] + 1
        )

        with self.assertRaises(VoiceLockNotConfirmedError):
            service.confirm_voice_lock(confirm_command(candidate, "wrong-fixed-confirm"))
        confirmed = service.confirm_clone_voice_lock(
            confirm_command(candidate, "confirm-clone-v2")
        )
        validate_confirmed_clone_voice_lock_bundle(confirmed)
        with self.assertRaises(VoiceLockNotConfirmedError):
            validate_confirmed_voice_lock_bundle(confirmed)
        with self.assertRaises(VoiceLockNotConfirmedError):
            service.get_confirmed_voice_lock(
                SCOPE["workspaceRef"],
                SCOPE["projectRef"],
                SCOPE["seriesRef"],
                "character-zhen",
            )
        current = service.get_confirmed_clone_voice_lock(
            SCOPE["workspaceRef"],
            SCOPE["projectRef"],
            SCOPE["seriesRef"],
            v1["voiceLock"]["voiceRef"],
        )
        self.assertEqual(current["voiceLockVersion"], confirmed["voiceLockVersion"])
        detail = service.get_voice_lock(
            SCOPE["workspaceRef"],
            SCOPE["projectRef"],
            SCOPE["seriesRef"],
            v1["voiceLock"]["voiceRef"],
        )
        self.assertEqual(detail["voiceLockVersions"][0], v1["voiceLockVersion"])

    def test_caller_cannot_forge_or_change_voice_identity_pin(self):
        service = self.make_service(self.make_repository())
        v1 = confirmed_v1(service)
        forged = clone_command(v1, "forged-identity")
        forged["voiceIdentityVersionRef"] = "caller-selected-version"
        forged["voiceIdentityDigest"] = "f" * 64
        with self.assertRaises(EpisodeProductionError):
            service.create_clone_voice_lock_version(forged)

        v2_candidate = service.create_clone_voice_lock_version(
            clone_command(v1, "create-v2")
        )
        v2 = service.confirm_clone_voice_lock(
            confirm_command(v2_candidate, "confirm-v2")
        )
        changed = clone_command(v2, "changed-identity", source_suffix="b")
        changed["voiceIdentityVersionRef"] = v2["voiceLockVersion"][
            "voiceLockVersionRef"
        ]
        changed["voiceIdentityDigest"] = v2["voiceLockVersion"]["payloadDigest"]
        with self.assertRaises(EpisodeProductionError):
            service.create_clone_voice_lock_version(changed)

        v3 = service.create_clone_voice_lock_version(
            clone_command(v2, "create-v3", source_suffix="c")
        )
        self.assertEqual(v3["voiceLockVersion"]["versionNumber"], 3)
        self.assertEqual(
            v3["voiceLockVersion"]["voiceIdentityVersionRef"],
            v1["voiceLockVersion"]["voiceLockVersionRef"],
        )
        self.assertEqual(
            v3["voiceLockVersion"]["voiceIdentityDigest"],
            v1["voiceLockVersion"]["payloadDigest"],
        )

    def test_fixed_successor_cannot_downgrade_a_confirmed_clone_v2(self):
        service = self.make_service(self.make_repository())
        v1 = confirmed_v1(service)
        candidate = service.create_clone_voice_lock_version(
            clone_command(v1, "clone-before-downgrade")
        )
        v2 = service.confirm_clone_voice_lock(
            confirm_command(candidate, "confirm-before-downgrade")
        )
        downgrade = {
            **SCOPE,
            "voiceRef": v2["voiceLock"]["voiceRef"],
            "baseVoiceLockVersionRef": v2["voiceLockVersion"][
                "voiceLockVersionRef"
            ],
            "baseVoiceLockDigest": v2["voiceLockVersion"]["payloadDigest"],
            "expectedRevision": v2["voiceLock"]["revision"],
            "engineFamily": "local-neural-tts-v1",
            "voiceId": "fixed-downgrade",
            "gender": "female",
            "apparentAge": 31,
            "pitchSemitones": 0.0,
            "rateScale": 1.0,
            "timbreDescriptor": "forbidden downgrade",
            "languageCode": "zh-CN",
            "idempotencyKey": "fixed-downgrade",
        }
        with self.assertRaises(VoiceLockNotConfirmedError):
            service.create_voice_lock_version(downgrade)

    def test_clone_operation_uses_existing_idempotency_scope(self):
        service = self.make_service(self.make_repository())
        v1 = confirmed_v1(service)
        with self.assertRaises(IdempotencyConflictError):
            service.create_clone_voice_lock_version(
                clone_command(v1, "create-fixed", source_suffix="cross-kind")
            )
        command = clone_command(v1, "clone-idempotency")
        first = service.create_clone_voice_lock_version(command)
        replay = service.create_clone_voice_lock_version(command)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["voiceLockVersion"], first["voiceLockVersion"])

        changed = clone_command(v1, "clone-idempotency", source_suffix="changed")
        with self.assertRaises(IdempotencyConflictError):
            service.create_clone_voice_lock_version(changed)

    def test_same_expected_revision_concurrent_clone_successors_have_one_winner(self):
        repository = self.make_repository()
        baseline = self.make_service(repository)
        v1 = confirmed_v1(baseline)
        services = (
            self.make_service(repository, version_count=1),
            self.make_service(repository, version_count=1),
        )
        commands = (
            clone_command(v1, "concurrent-a", source_suffix="a"),
            clone_command(v1, "concurrent-b", source_suffix="b"),
        )

        def write(index: int):
            try:
                return services[index].create_clone_voice_lock_version(
                    commands[index]
                )
            except Exception as exc:  # asserted below
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, (0, 1)))
        winners = [item for item in results if isinstance(item, dict)]
        losers = [item for item in results if isinstance(item, Exception)]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(losers), 1)
        self.assertIsInstance(losers[0], StaleInputError)

    def test_authoritative_descendant_query_reads_v2_from_same_store(self):
        service = self.make_service(self.make_repository())
        v1 = confirmed_v1(service)
        self.assertEqual(
            service.list_clone_voice_lock_versions(**{
                "workspace_ref": SCOPE["workspaceRef"],
                "project_ref": SCOPE["projectRef"],
                "series_ref": SCOPE["seriesRef"],
            }),
            [],
        )
        v2 = service.create_clone_voice_lock_version(
            clone_command(v1, "descendant-v2")
        )
        descendants = service.list_clone_voice_lock_versions(
            SCOPE["workspaceRef"], SCOPE["projectRef"], SCOPE["seriesRef"]
        )
        self.assertEqual(descendants, [v2["voiceLockVersion"]])


class InMemoryVoiceLockV2ContractTests(
    VoiceLockV2ContractMixin, unittest.TestCase
):
    def make_repository(self):
        return InMemoryVoiceLockAdapter()


class SqliteVoiceLockV2ContractTests(
    VoiceLockV2ContractMixin, unittest.TestCase
):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "voice-lock-v2.sqlite3"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def make_repository(self):
        return SqliteVoiceLockAdapter(self.database)

    def test_v1_v2_chain_survives_restart_without_second_store(self):
        first = self.make_service(self.make_repository())
        v1 = confirmed_v1(first)
        candidate = first.create_clone_voice_lock_version(
            clone_command(v1, "restart-create-v2")
        )
        confirmed = first.confirm_clone_voice_lock(
            confirm_command(candidate, "restart-confirm-v2")
        )

        restarted = self.make_service(
            SqliteVoiceLockAdapter(
                self.database, initialize_if_missing=False
            ),
            version_count=2,
        )
        restored = restarted.get_confirmed_clone_voice_lock(
            SCOPE["workspaceRef"],
            SCOPE["projectRef"],
            SCOPE["seriesRef"],
            confirmed["voiceLock"]["voiceRef"],
        )
        self.assertEqual(restored["voiceLockVersion"], confirmed["voiceLockVersion"])
        detail = restarted.get_voice_lock(
            SCOPE["workspaceRef"],
            SCOPE["projectRef"],
            SCOPE["seriesRef"],
            confirmed["voiceLock"]["voiceRef"],
        )
        self.assertEqual(
            [item["schemaVersion"] for item in detail["voiceLockVersions"]],
            [VOICE_LOCK_VERSION_SCHEMA_VERSION, VOICE_LOCK_VERSION_V2_SCHEMA_VERSION],
        )
        with sqlite3.connect(self.database) as connection:
            version_tables = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                "AND name='v5_voice_lock_versions'"
            ).fetchone()[0]
            clone_tables = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                "AND name LIKE '%clone%voice%lock%'"
            ).fetchone()[0]
        self.assertEqual(version_tables, 1)
        self.assertEqual(clone_tables, 0)


if __name__ == "__main__":
    unittest.main()
