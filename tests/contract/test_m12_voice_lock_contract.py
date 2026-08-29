from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RepositoryUnavailableError,
    _digest,
)
from services.v5_core_os.episode_production.voice import (
    InMemoryVoiceLockAdapter,
    K2VoiceLockService,
    SqliteVoiceLockAdapter,
    VoiceLockConflictError,
    VoiceLockImmutableError,
    VoiceLockNotConfirmedError,
    validate_confirmed_voice_lock_bundle,
)


SCOPE = {
    "workspaceRef": "workspace-a",
    "projectRef": "project-a",
    "seriesRef": "series-a",
}


class Refs:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def __call__(self, prefix: str) -> str:
        value = self.counts.get(prefix, 0) + 1
        self.counts[prefix] = value
        return f"{prefix}-{value}"


class CollidingVoiceRefs:
    def __call__(self, prefix: str) -> str:
        if prefix == "voice-lock":
            return "voice-lock-1"
        return f"{prefix}-collision"


def command(key: str, *, character_ref: str = "character-lin") -> dict:
    return {
        **SCOPE,
        "characterRef": character_ref,
        "engineFamily": "local-neural-tts-v1",
        "voiceId": f"voice-{character_ref}",
        "gender": "female",
        "apparentAge": 28,
        "pitchSemitones": -1.5,
        "rateScale": 0.95,
        "timbreDescriptor": "中低音，稳定胸腔共鸣",
        "idempotencyKey": key,
    }


def confirm_command(created: dict, key: str) -> dict:
    return {
        **SCOPE,
        "voiceRef": created["voiceLock"]["voiceRef"],
        "voiceLockVersionRef": created["voiceLockVersion"][
            "voiceLockVersionRef"
        ],
        "voiceLockDigest": created["voiceLockVersion"]["payloadDigest"],
        "expectedRevision": created["voiceLock"]["revision"],
        "idempotencyKey": key,
    }


def successor_command(confirmed: dict, key: str) -> dict:
    return {
        **SCOPE,
        "voiceRef": confirmed["voiceLock"]["voiceRef"],
        "baseVoiceLockVersionRef": confirmed["voiceLockVersion"][
            "voiceLockVersionRef"
        ],
        "baseVoiceLockDigest": confirmed["voiceLockVersion"]["payloadDigest"],
        "expectedRevision": confirmed["voiceLock"]["revision"],
        "engineFamily": "local-neural-tts-v1",
        "voiceId": "voice-character-lin-v2",
        "gender": "female",
        "apparentAge": 30,
        "pitchSemitones": -0.5,
        "rateScale": 1.0,
        "timbreDescriptor": "中低音，略带疲惫颗粒感",
        "languageCode": "zh-CN",
        "idempotencyKey": key,
    }


class VoiceLockContractMixin:
    def service(self) -> K2VoiceLockService:
        raise NotImplementedError

    def test_series_character_uniqueness_default_and_closed_world(self):
        service = self.service()
        first = service.create_voice_lock(command("create-lin"))
        self.assertEqual(first["voiceLockVersion"]["languageCode"], "zh-CN")
        self.assertEqual(first["voiceLockVersion"]["state"], "CANDIDATE")
        self.assertTrue(first["voiceLockVersion"]["immutable"])

        replay = service.create_voice_lock(command("create-lin"))
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["voiceLockVersion"], first["voiceLockVersion"])

        with self.assertRaises(VoiceLockConflictError):
            service.create_voice_lock(command("duplicate-lin"))

        other_series = command("create-lin-other-series")
        other_series["seriesRef"] = "series-b"
        isolated = service.create_voice_lock(other_series)
        self.assertEqual(isolated["voiceLock"]["seriesRef"], "series-b")

        changed = command("create-lin")
        changed["rateScale"] = 1.1
        with self.assertRaises(IdempotencyConflictError):
            service.create_voice_lock(changed)

        injected = command("unknown-field")
        injected["unexpected"] = True
        with self.assertRaises(EpisodeProductionError):
            service.create_voice_lock(injected)

        invalid_gender = command("invalid-gender")
        invalid_gender["gender"] = []
        with self.assertRaises(EpisodeProductionError):
            service.create_voice_lock(invalid_gender)

    def test_unconfirmed_voice_lock_is_not_resolvable(self):
        service = self.service()
        service.create_voice_lock(command("unconfirmed"))
        with self.assertRaises(VoiceLockNotConfirmedError):
            service.get_confirmed_voice_lock(
                SCOPE["workspaceRef"],
                SCOPE["projectRef"],
                SCOPE["seriesRef"],
                "character-lin",
            )

    def test_confirmation_is_digest_pinned_and_cannot_be_reapplied(self):
        service = self.service()
        created = service.create_voice_lock(command("create-confirm"))
        candidate_before = deepcopy(created["voiceLockVersion"])
        confirmed = service.confirm_voice_lock(
            confirm_command(created, "confirm-v1")
        )
        self.assertEqual(
            confirmed["voiceLockConfirmation"]["voiceLockDigest"],
            candidate_before["payloadDigest"],
        )
        self.assertEqual(confirmed["voiceLockVersion"], candidate_before)
        canonical_bundle = validate_confirmed_voice_lock_bundle(confirmed)
        self.assertEqual(
            set(canonical_bundle),
            {"voiceLock", "voiceLockVersion", "voiceLockConfirmation"},
        )

        invalid_replay = deepcopy(confirmed)
        invalid_replay["idempotentReplay"] = "false"
        with self.assertRaises(RepositoryUnavailableError):
            validate_confirmed_voice_lock_bundle(invalid_replay)

        replay = service.confirm_voice_lock(confirm_command(created, "confirm-v1"))
        self.assertTrue(replay["idempotentReplay"])

        reapplied = confirm_command(created, "confirm-v1-again")
        reapplied["expectedRevision"] = confirmed["voiceLock"]["revision"]
        with self.assertRaises(VoiceLockImmutableError):
            service.confirm_voice_lock(reapplied)

        in_place = successor_command(confirmed, "in-place-mutation")
        in_place["voiceLockVersionRef"] = candidate_before[
            "voiceLockVersionRef"
        ]
        with self.assertRaises(EpisodeProductionError):
            service.create_voice_lock_version(in_place)

    def test_explicit_successor_preserves_parent_and_confirmation_lineage(self):
        service = self.service()
        created = service.create_voice_lock(command("create-v1"))
        v1 = service.confirm_voice_lock(confirm_command(created, "confirm-v1"))
        v1_candidate = deepcopy(v1["voiceLockVersion"])

        successor = service.create_voice_lock_version(
            successor_command(v1, "create-v2")
        )
        v2 = successor["voiceLockVersion"]
        self.assertEqual(v2["versionNumber"], 2)
        self.assertEqual(
            v2["parentVoiceLockVersionRef"],
            v1_candidate["voiceLockVersionRef"],
        )
        self.assertEqual(
            v2["parentVoiceLockDigest"], v1_candidate["payloadDigest"]
        )
        self.assertEqual(v1["voiceLockVersion"], v1_candidate)
        self.assertEqual(
            successor["voiceLock"]["confirmedVoiceLockVersionRef"],
            v1_candidate["voiceLockVersionRef"],
        )

        still_v1 = service.get_confirmed_voice_lock(
            SCOPE["workspaceRef"],
            SCOPE["projectRef"],
            SCOPE["seriesRef"],
            "character-lin",
        )
        self.assertEqual(still_v1["voiceLockVersion"], v1_candidate)

        with self.assertRaises(VoiceLockNotConfirmedError):
            service.create_voice_lock_version(
                {
                    **successor_command(v1, "illegal-v3"),
                    "expectedRevision": successor["voiceLock"]["revision"],
                }
            )

        v2_confirmed = service.confirm_voice_lock(
            confirm_command(successor, "confirm-v2")
        )
        current = service.get_confirmed_voice_lock(
            SCOPE["workspaceRef"],
            SCOPE["projectRef"],
            SCOPE["seriesRef"],
            "character-lin",
        )
        self.assertEqual(current["voiceLockVersion"], v2_confirmed["voiceLockVersion"])
        detail = service.get_voice_lock(
            SCOPE["workspaceRef"],
            SCOPE["projectRef"],
            SCOPE["seriesRef"],
            v2_confirmed["voiceLock"]["voiceRef"],
        )
        self.assertEqual(
            [item["versionNumber"] for item in detail["voiceLockVersions"]],
            [1, 2],
        )


class InMemoryVoiceLockContractTests(
    VoiceLockContractMixin, unittest.TestCase
):
    def service(self) -> K2VoiceLockService:
        return K2VoiceLockService(
            InMemoryVoiceLockAdapter(),
            ref_factory=Refs(),
            clock=lambda: "2026-08-29T12:00:00Z",
        )

    def test_voice_ref_is_unique_inside_the_series_scope(self):
        repository = InMemoryVoiceLockAdapter()
        first = K2VoiceLockService(
            repository,
            ref_factory=Refs(),
            clock=lambda: "2026-08-29T12:00:00Z",
        )
        first.create_voice_lock(command("voice-ref-first"))
        collision = K2VoiceLockService(
            repository,
            ref_factory=CollidingVoiceRefs(),
            clock=lambda: "2026-08-29T12:00:01Z",
        )
        with self.assertRaises(VoiceLockConflictError):
            collision.create_voice_lock(
                command("voice-ref-collision", character_ref="character-gu")
            )

class SqliteVoiceLockContractTests(VoiceLockContractMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "voice-lock.sqlite3"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def service(self) -> K2VoiceLockService:
        return K2VoiceLockService(
            SqliteVoiceLockAdapter(self.database),
            ref_factory=Refs(),
            clock=lambda: "2026-08-29T12:00:00Z",
        )

    def test_confirmed_voice_lock_survives_restart(self):
        first = self.service()
        created = first.create_voice_lock(command("restart-create"))
        confirmed = first.confirm_voice_lock(
            confirm_command(created, "restart-confirm")
        )

        restarted_refs = Refs()
        restarted_refs.counts["voice-lock-version"] = 1
        restarted = K2VoiceLockService(
            SqliteVoiceLockAdapter(
                self.database, initialize_if_missing=False
            ),
            ref_factory=restarted_refs,
            clock=lambda: "2026-08-29T12:01:00Z",
        )
        restored = restarted.get_confirmed_voice_lock(
            SCOPE["workspaceRef"],
            SCOPE["projectRef"],
            SCOPE["seriesRef"],
            "character-lin",
        )
        self.assertEqual(restored["voiceLockVersion"], confirmed["voiceLockVersion"])
        self.assertEqual(
            restored["voiceLockConfirmation"],
            confirmed["voiceLockConfirmation"],
        )
        replay = restarted.confirm_voice_lock(
            confirm_command(created, "restart-confirm")
        )
        self.assertTrue(replay["idempotentReplay"])
        successor = restarted.create_voice_lock_version(
            successor_command(confirmed, "restart-successor")
        )
        self.assertEqual(successor["voiceLockVersion"]["versionNumber"], 2)

    def test_voice_ref_is_unique_inside_the_series_scope(self):
        first = self.service()
        first.create_voice_lock(command("voice-ref-first"))
        collision = K2VoiceLockService(
            SqliteVoiceLockAdapter(self.database),
            ref_factory=CollidingVoiceRefs(),
            clock=lambda: "2026-08-29T12:00:01Z",
        )
        with self.assertRaises(VoiceLockConflictError):
            collision.create_voice_lock(
                command("voice-ref-collision", character_ref="character-gu")
            )

    def test_repository_schema_drift_fails_closed(self):
        self.service()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "ALTER TABLE v5_voice_locks ADD COLUMN untrusted_drift TEXT"
            )
        with self.assertRaises(RepositoryUnavailableError):
            SqliteVoiceLockAdapter(
                self.database, initialize_if_missing=False
            )

    def test_repository_trigger_drift_fails_closed(self):
        self.service()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TRIGGER ignore_voice_lock_insert BEFORE INSERT ON "
                "v5_voice_locks BEGIN SELECT RAISE(IGNORE); END"
            )
        with self.assertRaises(RepositoryUnavailableError):
            SqliteVoiceLockAdapter(
                self.database, initialize_if_missing=False
            )

    def test_runtime_trigger_drift_stops_before_write(self):
        service = self.service()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TRIGGER ignore_operation_insert BEFORE INSERT ON "
                "v5_voice_lock_operations BEGIN SELECT RAISE(IGNORE); END"
            )
        with self.assertRaises(RepositoryUnavailableError):
            service.create_voice_lock(command("runtime-trigger"))
        with sqlite3.connect(self.database) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM v5_voice_locks"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_confirmation_and_operation_sql_keys_are_digest_pinned(self):
        service = self.service()
        created = service.create_voice_lock(command("projection-create"))
        service.confirm_voice_lock(
            confirm_command(created, "projection-confirm")
        )
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "UPDATE v5_voice_lock_confirmations SET "
                "voice_lock_confirmation_ref='tampered-confirmation'"
            )
        with self.assertRaises(RepositoryUnavailableError):
            service.get_confirmed_voice_lock(
                SCOPE["workspaceRef"],
                SCOPE["projectRef"],
                SCOPE["seriesRef"],
                "character-lin",
            )

        second_database = Path(self.directory.name) / "voice-lock-operation.sqlite3"
        operation_service = K2VoiceLockService(
            SqliteVoiceLockAdapter(second_database),
            ref_factory=Refs(),
            clock=lambda: "2026-08-29T12:00:00Z",
        )
        operation_service.create_voice_lock(command("original-key"))
        with sqlite3.connect(second_database) as connection:
            connection.execute(
                "UPDATE v5_voice_lock_operations SET "
                "idempotency_key='tampered-key'"
            )
        with self.assertRaises(RepositoryUnavailableError):
            operation_service.create_voice_lock(command("tampered-key"))

    def test_version_parent_chain_is_verified_on_read(self):
        service = self.service()
        created = service.create_voice_lock(command("chain-create"))
        confirmed = service.confirm_voice_lock(
            confirm_command(created, "chain-confirm")
        )
        successor = service.create_voice_lock_version(
            successor_command(confirmed, "chain-successor")
        )
        tampered = deepcopy(successor["voiceLockVersion"])
        tampered["parentVoiceLockVersionRef"] = "missing-version"
        tampered["parentVoiceLockDigest"] = "f" * 64
        tampered.pop("payloadDigest")
        tampered["payloadDigest"] = _digest(tampered)
        payload = json.dumps(
            tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "UPDATE v5_voice_lock_versions SET parent_version_ref=?, "
                "parent_version_digest=?, payload_json=?, payload_digest=? "
                "WHERE voice_lock_version_ref=?",
                (
                    tampered["parentVoiceLockVersionRef"],
                    tampered["parentVoiceLockDigest"],
                    payload,
                    tampered["payloadDigest"],
                    tampered["voiceLockVersionRef"],
                ),
            )
        with self.assertRaises(RepositoryUnavailableError):
            service.get_voice_lock(
                SCOPE["workspaceRef"],
                SCOPE["projectRef"],
                SCOPE["seriesRef"],
                successor["voiceLock"]["voiceRef"],
            )
        tampered_confirmation = confirm_command(successor, "tampered-confirm")
        tampered_confirmation["voiceLockDigest"] = tampered["payloadDigest"]
        with self.assertRaises(RepositoryUnavailableError):
            service.confirm_voice_lock(tampered_confirmation)

    def test_general_read_validates_confirmed_character_lineage(self):
        service = self.service()
        created = service.create_voice_lock(command("character-create"))
        confirmed = service.confirm_voice_lock(
            confirm_command(created, "character-confirm")
        )
        successor = service.create_voice_lock_version(
            successor_command(confirmed, "character-successor")
        )
        confirmation = deepcopy(confirmed["voiceLockConfirmation"])
        confirmation["characterRef"] = "character-other"
        confirmation.pop("payloadDigest")
        confirmation["payloadDigest"] = _digest(confirmation)
        payload = json.dumps(
            confirmation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "UPDATE v5_voice_lock_confirmations SET payload_json=?, "
                "payload_digest=?",
                (payload, confirmation["payloadDigest"]),
            )
        with self.assertRaises(RepositoryUnavailableError):
            service.get_voice_lock(
                SCOPE["workspaceRef"],
                SCOPE["projectRef"],
                SCOPE["seriesRef"],
                confirmed["voiceLock"]["voiceRef"],
            )
        with self.assertRaises(RepositoryUnavailableError):
            service.confirm_voice_lock(
                confirm_command(successor, "character-successor-confirm")
            )

    def test_successor_rejects_corrupt_confirmed_bundle(self):
        service = self.service()
        created = service.create_voice_lock(command("successor-create"))
        confirmed = service.confirm_voice_lock(
            confirm_command(created, "successor-confirm")
        )
        confirmation = deepcopy(confirmed["voiceLockConfirmation"])
        confirmation["characterRef"] = "character-other"
        confirmation.pop("payloadDigest")
        confirmation["payloadDigest"] = _digest(confirmation)
        payload = json.dumps(
            confirmation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "UPDATE v5_voice_lock_confirmations SET payload_json=?, "
                "payload_digest=?",
                (payload, confirmation["payloadDigest"]),
            )
        with self.assertRaises(RepositoryUnavailableError):
            service.create_voice_lock_version(
                successor_command(confirmed, "corrupt-successor")
            )


if __name__ == "__main__":
    unittest.main()
