import unittest

from services.v5_core_os.episode_production import create_in_memory_boundary
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    activate_k2_m6_baseline,
    g2_command,
    g3_command,
    k2_identity_authority,
    run_command,
    seed_k2_roots,
)


class M12DialogueAudioDomainIntegrationTests(unittest.TestCase):
    def test_current_shot_graph_dialogue_maps_to_confirmed_series_voices(self):
        assembly, refs, project, series, episode, _ = seed_k2_roots(
            with_m6_authority=True
        )
        activate_k2_m6_baseline(assembly, project, series)
        production = create_in_memory_boundary(
            project_boundary=assembly.project_context,
            series_episode_boundary=assembly.series_episode,
            series_planning_boundary=assembly.series_planning,
            script_studio_boundary=assembly.script_studio,
            identity_reference_authority=k2_identity_authority(),
            ref_factory=refs,
            clock=lambda: "2026-08-29T00:00:00Z",
        )
        run = production.create_run(run_command(project, series, episode))
        production.authorize_and_lock(g2_command(run))
        production.compile_shot_graph(g3_command(run))

        for character_ref, gender, age in (
            ("character-lin", "female", 28),
            ("character-gu", "male", 42),
        ):
            created = production.create_voice_lock(
                {
                    "workspaceRef": WORKSPACE,
                    "projectRef": project["projectRef"],
                    "seriesRef": series["seriesRef"],
                    "characterRef": character_ref,
                    "engineFamily": "local-neural-tts-v1",
                    "voiceId": f"voice-{character_ref}",
                    "gender": gender,
                    "apparentAge": age,
                    "pitchSemitones": 0.0,
                    "rateScale": 1.0,
                    "timbreDescriptor": "中低音，稳定胸腔共鸣",
                    "idempotencyKey": f"voice-create-{character_ref}",
                }
            )
            production.confirm_voice_lock(
                {
                    "workspaceRef": WORKSPACE,
                    "projectRef": project["projectRef"],
                    "seriesRef": series["seriesRef"],
                    "voiceRef": created["voiceLock"]["voiceRef"],
                    "voiceLockVersionRef": created["voiceLockVersion"][
                        "voiceLockVersionRef"
                    ],
                    "voiceLockDigest": created["voiceLockVersion"][
                        "payloadDigest"
                    ],
                    "expectedRevision": created["voiceLock"]["revision"],
                    "idempotencyKey": f"voice-confirm-{character_ref}",
                }
            )

        plan = production.plan_dialogue_audio(
            WORKSPACE, run["productionRunRef"]
        )

        requests = plan["generationRequests"]
        self.assertEqual(plan["summary"], {"dialogueRequests": 2})
        self.assertEqual(
            [request["parameters"]["text"] for request in requests],
            [
                "从现在起，只相信我们亲眼看到的。",
                "它被删掉了，但没有消失。",
            ],
        )
        self.assertEqual(
            [request["characterRef"] for request in requests],
            ["character-gu", "character-lin"],
        )
        self.assertEqual([request["ordinal"] for request in requests], [1, 2])
        self.assertTrue(
            all(request["parameters"]["speechSynthesis"] for request in requests)
        )
        self.assertFalse(plan["dispatchAllowed"])


if __name__ == "__main__":
    unittest.main()
