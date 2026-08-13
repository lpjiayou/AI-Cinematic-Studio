import copy
import threading
import unittest

from services.v5_core_os.lifecycle_integrity import (
    AssemblyPoisonedError,
    LifecycleAssembly,
    LifecycleOperation,
    LifecycleRollbackError,
)
from services.v5_core_os.series_intelligence import M6Scope, VerifiedApproval
from services.v5_core_os.series_intelligence.canonical import digest
from services.v5_core_os.series_intelligence.errors import AuthorityUnavailableError
from services.v5_core_os.series_intelligence.public import SeriesIntelligencePublicError
from tests.unit.test_series_planning_m5 import valid_candidate


NOW = "2026-08-13T00:00:00.000Z"


class Refs:
    def __init__(self):
        self.counts = {}

    def __call__(self, prefix):
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}-m6-{self.counts[prefix]}"


class ScopeAuthority:
    def resolve_scope(self, workspace_ref, project_ref, series_ref):
        return M6Scope("series-production", f"tenant-{workspace_ref}", workspace_ref, project_ref, series_ref)


class ApprovalAuthority:
    def verify_approval(self, *, scope, approval_ref, action):
        if approval_ref != "approval-human":
            raise AuthorityUnavailableError()
        return VerifiedApproval(approval_ref, "actor-owner", "human")


class ProviderApprovalAuthority:
    def verify_approval(self, *, scope, approval_ref, action):
        return VerifiedApproval(approval_ref, "deepseek", "provider")


def bible_content(location_ref="location-lamp"):
    return {
        "worldRules": [{"worldRuleRef": "rule-light", "statement": "灯不会说话"}],
        "glossaryTerms": [{"glossaryTermRef": "term-lamp", "term": "晚灯", "definition": "旧路灯"}],
        "locations": [{"locationRef": location_ref, "name": "旧街角"}],
        "factions": [{"factionRef": "faction-residents", "name": "夜归人"}],
        "props": [{"propRef": "prop-letter", "name": "旧信"}],
        "timelineEvents": [{
            "timelineEventRef": "event-first",
            "summary": "第一次相遇",
            "locationRef": location_ref,
            "factionRefs": ["faction-residents"],
            "propRefs": ["prop-letter"],
        }],
        "visualConstraints": [{"visualConstraintRef": "visual-warm", "rule": "暖黄"}],
        "prohibitedNarrativePatterns": [{"prohibitedNarrativePatternRef": "ban-speech", "rule": "灯不能说话"}],
    }


def character_content(episode_refs, location_ref="location-lamp", *, bindings=None):
    return {
        "characters": [
            {"characterRef": "character-lamp", "name": "晚灯", "motivation": "陪伴"},
            {"characterRef": "character-traveler", "name": "旅人", "motivation": "回家"},
        ],
        "stateIntervals": [{
            "intervalRef": "interval-location-1",
            "characterRef": "character-lamp",
            "category": "Location",
            "startEpisodePlanItemRef": episode_refs[0],
            "endEpisodePlanItemRef": episode_refs[-1],
            "valueRef": location_ref,
        }],
        "relationships": [{
            "relationshipRef": "relationship-watch",
            "fromCharacterRef": "character-lamp",
            "toCharacterRef": "character-traveler",
            "relationshipType": "watches-over",
        }],
        "identityBindings": bindings or [],
    }


def base_command(context, operation):
    return {
        "workspaceRef": context["workspaceRef"],
        "projectRef": context["projectRef"],
        "seriesRef": context["seriesRef"],
        "operationRef": operation,
        "idempotencyKey": operation,
    }


def seed_assembly(
    *, outbox_hook=None, journal_registrar=None, workspace="workspace-m6",
    approval_authority=None,
):
    refs = Refs()
    assembly = LifecycleAssembly.in_memory(
        ref_factory=refs,
        clock=lambda: NOW,
        journal_registrar=journal_registrar,
        m6_scope_authority=ScopeAuthority(),
        m6_approval_authority=approval_authority or ApprovalAuthority(),
        m6_outbox_hook=outbox_hook,
    )
    series = assembly.series_episode.create_series({
        "workspaceRef": workspace,
        "contentProfileRef": f"profile-{workspace}",
        "title": "晚灯",
        "plannedEpisodeCount": 4,
    })
    project = assembly.project_context.create_project({
        "workspaceRef": workspace,
        "contentProfileRef": f"profile-{workspace}",
        "projectType": "series",
        "seriesRef": series["seriesRef"],
        "title": "晚灯系列制作",
        "plannedEpisodeCount": 4,
    })
    plan = assembly.series_planning.confirm_candidate({
        "workspaceRef": workspace,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
        "humanConfirmed": True,
        "candidate": valid_candidate(),
    })
    context = {
        "workspaceRef": workspace,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
        "plan": plan,
    }
    return assembly, context


def confirmed_components(assembly, context):
    m6 = assembly.series_intelligence
    bible = m6.create_bible_version({
        **base_command(context, "create-bible"), "candidate": True, "content": bible_content()
    })
    bible = m6.confirm_bible_version({
        **base_command(context, "confirm-bible"),
        "seriesBibleRef": bible["root"]["seriesBibleRef"],
        "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
        "expectedRevision": bible["root"]["revision"],
        "approvalRef": "approval-human",
    })
    source = assembly.series_planning.get_confirmed_m6_source_snapshot(
        context["workspaceRef"], context["projectRef"], context["seriesRef"]
    )
    characters = m6.create_character_version({
        **base_command(context, "create-characters"),
        "candidate": True,
        "seriesBibleRef": bible["root"]["seriesBibleRef"],
        "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
        "content": character_content([item["episodePlanItemRef"] for item in source["episodePlanItems"]]),
    })
    characters = m6.confirm_character_version({
        **base_command(context, "confirm-characters"),
        "characterContinuityRef": characters["root"]["characterContinuityRef"],
        "characterContinuityVersionRef": characters["version"]["characterContinuityVersionRef"],
        "expectedRevision": characters["root"]["revision"],
        "approvalRef": "approval-human",
    })
    return bible, characters


class CanonicalContractTests(unittest.TestCase):
    def test_unicode_and_key_order_produce_same_lowercase_sha256(self):
        first = digest({"z": "e\u0301", "a": [1, None]})
        second = digest({"a": [1, None], "z": "é"})
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_floats_are_rejected(self):
        with self.assertRaises(ValueError):
            digest({"forbidden": 1.5})


class SeriesIntelligenceLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.assembly, self.context = seed_assembly()
        self.m6 = self.assembly.series_intelligence

    def test_default_authority_fails_closed_and_client_scope_claims_are_rejected(self):
        default = LifecycleAssembly.in_memory()
        with self.assertRaises(SeriesIntelligencePublicError) as unavailable:
            default.series_intelligence.get_workspace("w", "p", "s")
        self.assertEqual(unavailable.exception.code, "authority_unavailable")
        command = {**base_command(self.context, "bad-scope"), "tenantId": "client-tenant", "content": bible_content()}
        with self.assertRaises(SeriesIntelligencePublicError) as mismatch:
            self.m6.create_bible_version(command)
        self.assertEqual(mismatch.exception.code, "scope_mismatch")

    def test_m5_source_snapshot_is_deterministic_and_digest_owned_upstream(self):
        args = (self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"])
        first = self.assembly.series_planning.get_confirmed_m6_source_snapshot(*args)
        second = self.assembly.series_planning.get_confirmed_m6_source_snapshot(*args)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "confirmed")
        self.assertEqual(len(first["episodePlanItems"]), 4)
        self.assertRegex(first["seriesPlanVersionDigest"], r"^[0-9a-f]{64}$")

    def test_bible_draft_candidate_confirm_and_immutable_new_version(self):
        first = self.m6.create_bible_version({
            **base_command(self.context, "bible-draft"), "content": bible_content()
        })
        self.assertEqual(first["version"]["status"], "DRAFT")
        candidate = self.m6.submit_bible_candidate({
            **base_command(self.context, "bible-submit"),
            "seriesBibleRef": first["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": first["version"]["seriesBibleVersionRef"],
            "expectedRevision": 1,
        })
        confirmed = self.m6.confirm_bible_version({
            **base_command(self.context, "bible-confirm"),
            "seriesBibleRef": first["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": first["version"]["seriesBibleVersionRef"],
            "expectedRevision": 2,
            "approvalRef": "approval-human",
        })
        self.assertEqual(confirmed["version"]["status"], "CONFIRMED")
        second_content = bible_content("location-square")
        second = self.m6.create_bible_version({
            **base_command(self.context, "bible-v2"),
            "seriesBibleRef": first["root"]["seriesBibleRef"],
            "expectedRevision": 3,
            "content": second_content,
        })
        self.assertEqual(second["version"]["versionNumber"], 2)
        self.assertEqual(second["version"]["parentSeriesBibleVersionRef"], first["version"]["seriesBibleVersionRef"])
        self.assertNotEqual(second["version"]["contentDigest"], first["version"]["contentDigest"])

    def test_provider_or_untrusted_approval_cannot_confirm(self):
        bible = self.m6.create_bible_version({
            **base_command(self.context, "candidate-provider"), "candidate": True, "content": bible_content()
        })
        with self.assertRaises(SeriesIntelligencePublicError) as denied:
            self.m6.confirm_bible_version({
                **base_command(self.context, "confirm-provider"),
                "seriesBibleRef": bible["root"]["seriesBibleRef"],
                "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
                "expectedRevision": 1,
                "approvalRef": "provider-self-approved",
                "actorRole": "owner",
            })
        self.assertEqual(denied.exception.code, "authority_unavailable")

        provider_assembly, provider_context = seed_assembly(
            approval_authority=ProviderApprovalAuthority()
        )
        provider_bible = provider_assembly.series_intelligence.create_bible_version({
            **base_command(provider_context, "provider-candidate"), "candidate": True,
            "content": bible_content(),
        })
        with self.assertRaises(SeriesIntelligencePublicError) as provider_denied:
            provider_assembly.series_intelligence.confirm_bible_version({
                **base_command(provider_context, "provider-confirm"),
                "seriesBibleRef": provider_bible["root"]["seriesBibleRef"],
                "seriesBibleVersionRef": provider_bible["version"]["seriesBibleVersionRef"],
                "expectedRevision": 1,
                "approvalRef": "approval-human",
            })
        self.assertEqual(provider_denied.exception.code, "confirmation_required")

    def test_actor_approval_and_time_metadata_do_not_change_content_digest(self):
        first = self.m6.create_bible_version({
            **base_command(self.context, "digest-metadata-a"),
            "approvalRef": "ignored-a", "actorRef": "actor-a", "createdAt": "old",
            "content": bible_content(),
        })
        second = self.m6.create_bible_version({
            **base_command(self.context, "digest-metadata-b"),
            "seriesBibleRef": first["root"]["seriesBibleRef"],
            "expectedRevision": 1,
            "approvalRef": "ignored-b", "actorRef": "actor-b", "createdAt": "new",
            "content": bible_content(),
        })
        self.assertEqual(first["version"]["contentDigest"], second["version"]["contentDigest"])

    def test_m6_source_reader_rejects_unconfirmed_plan(self):
        assembly = LifecycleAssembly.in_memory(
            ref_factory=Refs(), clock=lambda: NOW,
            m6_scope_authority=ScopeAuthority(), m6_approval_authority=ApprovalAuthority(),
        )
        series = assembly.series_episode.create_series({
            "workspaceRef": "workspace-unconfirmed", "contentProfileRef": "profile-unconfirmed",
            "title": "Unconfirmed", "plannedEpisodeCount": 4,
        })
        project = assembly.project_context.create_project({
            "workspaceRef": "workspace-unconfirmed", "contentProfileRef": "profile-unconfirmed",
            "projectType": "series", "seriesRef": series["seriesRef"], "title": "Project",
            "plannedEpisodeCount": 4,
        })
        context = {"workspaceRef": "workspace-unconfirmed", "projectRef": project["projectRef"], "seriesRef": series["seriesRef"]}
        with self.assertRaises(SeriesIntelligencePublicError) as unconfirmed:
            assembly.series_intelligence.create_bible_version({
                **base_command(context, "unconfirmed"), "content": bible_content()
            })
        self.assertEqual(unconfirmed.exception.code, "confirmation_required")

    def test_identity_binding_and_unknown_reference_fail_closed(self):
        bible, _ = confirmed_components(self.assembly, self.context)
        source = self.assembly.series_planning.get_confirmed_m6_source_snapshot(
            self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"]
        )
        for operation, content in (
            ("identity", character_content([item["episodePlanItemRef"] for item in source["episodePlanItems"]], bindings=[{"identityBindingRef": "identity-1"}])),
            ("unknown", character_content(["missing", *[item["episodePlanItemRef"] for item in source["episodePlanItems"]][1:]])),
        ):
            with self.subTest(operation=operation), self.assertRaises(SeriesIntelligencePublicError):
                self.m6.create_character_version({
                    **base_command(self.context, operation),
                    "seriesBibleRef": bible["root"]["seriesBibleRef"],
                    "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
                    "content": content,
                })

        refs = [item["episodePlanItemRef"] for item in source["episodePlanItems"]]
        unknown_cases = []
        for field in ("locationRefs", "propRefs", "timelineEventRefs"):
            content = character_content(refs)
            content["characters"][0][field] = ["missing-ref"]
            unknown_cases.append((field, content))
        relationship = character_content(refs)
        relationship["relationships"][0]["toCharacterRef"] = "character-missing"
        unknown_cases.append(("relationship-character", relationship))
        for name, content in unknown_cases:
            with self.subTest(unknown=name), self.assertRaises(SeriesIntelligencePublicError) as invalid:
                self.m6.create_character_version({
                    **base_command(self.context, f"unknown-{name}"),
                    "seriesBibleRef": bible["root"]["seriesBibleRef"],
                    "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
                    "content": content,
                })
            self.assertEqual(invalid.exception.code, "invalid_reference")

    def test_exclusive_intervals_reject_overlap_but_nonexclusive_can_coexist(self):
        bible, _ = confirmed_components(self.assembly, self.context)
        source = self.assembly.series_planning.get_confirmed_m6_source_snapshot(
            self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"]
        )
        refs = [item["episodePlanItemRef"] for item in source["episodePlanItems"]]
        content = character_content(refs)
        content["stateIntervals"].append({
            "intervalRef": "overlap", "characterRef": "character-lamp", "category": "Location",
            "startEpisodePlanItemRef": refs[1], "endEpisodePlanItemRef": refs[3], "valueRef": "location-lamp",
        })
        with self.assertRaises(SeriesIntelligencePublicError) as conflict:
            self.m6.create_character_version({
                **base_command(self.context, "overlap"),
                "seriesBibleRef": bible["root"]["seriesBibleRef"],
                "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
                "content": content,
            })
        self.assertEqual(conflict.exception.code, "version_conflict")

    def test_activation_lineage_events_order_idempotency_and_revision_conflict(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        command = {
            **base_command(self.context, "activate-1"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": characters["version"]["characterContinuityVersionRef"],
            "expectedActivationRevision": 0,
            "approvalRef": "approval-human",
        }
        first = self.m6.activate_baseline(command)
        replay = self.m6.activate_baseline(copy.deepcopy(command))
        self.assertEqual(first, replay)
        self.assertEqual(first["activationRevision"], 1)
        self.assertEqual(first["seriesPlanVersionRef"], self.context["plan"]["version"]["seriesPlanVersionRef"])
        self.assertEqual([item["eventType"] for item in self.m6.get_outbox()], ["M6BaselineConfirmed"])
        envelope = self.m6.get_outbox()[0]
        self.assertEqual(
            {
                "eventId", "eventType", "eventVersion", "aggregateType", "aggregateRef",
                "businessDomain", "tenantId", "workspaceId", "projectRef", "seriesRef",
                "correlationId", "causationId", "operationRef", "occurredAt", "payload",
                "schemaVersion",
            },
            set(envelope),
        )
        same_inputs_new_key = self.m6.activate_baseline({
            **command,
            "operationRef": "activate-same-components",
            "idempotencyKey": "activate-same-components",
            "expectedActivationRevision": 1,
        })
        self.assertEqual(first, same_inputs_new_key)
        self.assertEqual(len(self.m6.get_outbox()), 1)
        with self.assertRaises(SeriesIntelligencePublicError) as stale:
            self.m6.activate_baseline({**command, "operationRef": "stale", "idempotencyKey": "stale"})
        self.assertEqual(stale.exception.code, "version_conflict")

    def test_same_idempotency_key_different_payload_conflicts(self):
        command = {**base_command(self.context, "idem"), "content": bible_content()}
        self.m6.create_bible_version(command)
        changed = copy.deepcopy(command)
        changed["content"]["worldRules"][0]["statement"] = "changed"
        with self.assertRaises(SeriesIntelligencePublicError) as conflict:
            self.m6.create_bible_version(changed)
        self.assertEqual(conflict.exception.code, "idempotency_conflict")

    def test_same_refs_in_two_workspaces_are_isolated(self):
        other, other_context = seed_assembly(workspace="workspace-other")
        first = self.m6.create_bible_version({
            **base_command(self.context, "same-ref-a"), "content": bible_content()
        })
        second = other.series_intelligence.create_bible_version({
            **base_command(other_context, "same-ref-b"), "content": bible_content()
        })
        self.assertEqual(first["root"]["seriesBibleRef"], second["root"]["seriesBibleRef"])
        self.assertNotEqual(first["root"]["tenantId"], second["root"]["tenantId"])

    def test_root_uniqueness_ip_universe_and_cross_scope_are_rejected(self):
        first = self.m6.create_bible_version({
            **base_command(self.context, "unique-root"), "content": bible_content()
        })
        with self.assertRaises(SeriesIntelligencePublicError) as duplicate:
            self.m6.create_bible_version({
                **base_command(self.context, "duplicate-root"), "content": bible_content()
            })
        self.assertEqual(duplicate.exception.code, "duplicate_record")
        with self.assertRaises(SeriesIntelligencePublicError) as universe:
            self.m6.create_bible_version({
                **base_command(self.context, "ip-universe"), "ipUniverseRef": "ip-1",
                "seriesBibleRef": first["root"]["seriesBibleRef"], "expectedRevision": 1,
                "content": bible_content(),
            })
        self.assertEqual(universe.exception.code, "scope_mismatch")
        wrong = {**base_command(self.context, "wrong-project"), "projectRef": "project-other", "content": bible_content()}
        with self.assertRaises(SeriesIntelligencePublicError) as mismatch:
            self.m6.create_bible_version(wrong)
        self.assertEqual(mismatch.exception.code, "scope_mismatch")

    def test_expected_revision_concurrent_writers_have_one_winner(self):
        first = self.m6.create_bible_version({
            **base_command(self.context, "race-root"), "content": bible_content()
        })
        barrier = threading.Barrier(3)
        results = []
        def writer(index):
            command = {
                **base_command(self.context, f"race-{index}"),
                "seriesBibleRef": first["root"]["seriesBibleRef"],
                "expectedRevision": 1,
                "content": bible_content(f"location-race-{index}"),
            }
            barrier.wait()
            try:
                results.append(("ok", self.m6.create_bible_version(command)))
            except Exception as exc:
                results.append(("error", exc))
        threads = [threading.Thread(target=writer, args=(index,)) for index in (1, 2)]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads: thread.join(5)
        self.assertEqual([item[0] for item in results].count("ok"), 1)
        errors = [item[1] for item in results if item[0] == "error"]
        self.assertEqual(errors[0].code, "version_conflict")
        workspace = self.m6.get_workspace(
            self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"]
        )
        self.assertEqual(workspace["seriesBible"]["revision"], 2)

    def test_fact_sets_sort_by_ref_while_nested_narrative_order_is_preserved(self):
        first_content = bible_content()
        first_content["worldRules"] = [
            {"worldRuleRef": "rule-z", "beats": ["first", "second"]},
            {"worldRuleRef": "rule-a", "beats": ["alpha", "beta"]},
        ]
        second_content = copy.deepcopy(first_content)
        second_content["worldRules"].reverse()
        first = self.m6.create_bible_version({
            **base_command(self.context, "sort-a"), "content": first_content
        })
        second = self.m6.create_bible_version({
            **base_command(self.context, "sort-b"),
            "seriesBibleRef": first["root"]["seriesBibleRef"],
            "expectedRevision": 1,
            "content": second_content,
        })
        self.assertEqual(first["version"]["contentDigest"], second["version"]["contentDigest"])
        self.assertEqual(second["version"]["content"]["worldRules"][1]["beats"], ["first", "second"])

    def test_historical_rollback_derives_new_candidate_without_mutating_history(self):
        first = self.m6.create_bible_version({
            **base_command(self.context, "history-v1"), "candidate": True, "content": bible_content()
        })
        second = self.m6.create_bible_version({
            **base_command(self.context, "history-v2"),
            "seriesBibleRef": first["root"]["seriesBibleRef"], "expectedRevision": 1,
            "content": bible_content("location-history-v2"),
        })
        rollback = self.m6.create_bible_version({
            **base_command(self.context, "history-rollback"),
            "seriesBibleRef": first["root"]["seriesBibleRef"], "expectedRevision": 2,
            "baseSeriesBibleVersionRef": first["version"]["seriesBibleVersionRef"],
            "content": copy.deepcopy(first["version"]["content"]),
        })
        self.assertEqual(rollback["version"]["status"], "CANDIDATE")
        self.assertEqual(rollback["version"]["parentSeriesBibleVersionRef"], first["version"]["seriesBibleVersionRef"])
        self.assertEqual(rollback["version"]["contentDigest"], first["version"]["contentDigest"])
        self.assertEqual(second["version"]["status"], "DRAFT")

    def test_source_change_marks_candidate_stale_at_confirmation(self):
        bible = self.m6.create_bible_version({
            **base_command(self.context, "stale-bible-create"), "candidate": True, "content": bible_content()
        })
        original = self.context["plan"]
        keys = {
            "seriesConcept", "premise", "logline", "mainNarrativeDirection", "mainArcs",
            "subArcs", "characterArcIntents", "episodePlanItems", "narrativeRhythm",
            "worldIntent", "continuityIntent", "foreshadowingContext", "productionAssumptions",
        }
        content = {key: copy.deepcopy(original["version"][key]) for key in keys}
        content["premise"] = "M5 changed after M6 candidate creation"
        second = self.assembly.series_planning.create_manual_version({
            "workspaceRef": self.context["workspaceRef"],
            "projectRef": self.context["projectRef"],
            "seriesRef": self.context["seriesRef"],
            "seriesPlanRef": original["plan"]["seriesPlanRef"],
            "expectedPlanVersion": original["plan"]["version"],
            "content": content,
        })
        self.assembly.series_planning.confirm_version({
            "workspaceRef": self.context["workspaceRef"],
            "seriesPlanRef": second["plan"]["seriesPlanRef"],
            "seriesPlanVersionRef": second["version"]["seriesPlanVersionRef"],
            "expectedPlanVersion": second["plan"]["version"],
            "humanConfirmed": True,
        })
        with self.assertRaises(SeriesIntelligencePublicError) as stale:
            self.m6.confirm_bible_version({
                **base_command(self.context, "stale-bible-confirm"),
                "seriesBibleRef": bible["root"]["seriesBibleRef"],
                "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
                "expectedRevision": bible["root"]["revision"],
                "approvalRef": "approval-human",
            })
        self.assertEqual(stale.exception.code, "stale_source")

    def test_new_m5_version_derives_stale_compatibility_without_mutating_old_baseline(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        active = self.m6.activate_baseline({
            **base_command(self.context, "compat-activate"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": characters["version"]["characterContinuityVersionRef"],
            "expectedActivationRevision": 0,
            "approvalRef": "approval-human",
        })
        old_digest = active["contentDigest"]
        original = self.context["plan"]
        keys = {
            "seriesConcept", "premise", "logline", "mainNarrativeDirection", "mainArcs",
            "subArcs", "characterArcIntents", "episodePlanItems", "narrativeRhythm",
            "worldIntent", "continuityIntent", "foreshadowingContext", "productionAssumptions",
        }
        content = {key: copy.deepcopy(original["version"][key]) for key in keys}
        content["logline"] = "New confirmed M5 source"
        second = self.assembly.series_planning.create_manual_version({
            "workspaceRef": self.context["workspaceRef"], "projectRef": self.context["projectRef"],
            "seriesRef": self.context["seriesRef"], "seriesPlanRef": original["plan"]["seriesPlanRef"],
            "expectedPlanVersion": original["plan"]["version"], "content": content,
        })
        self.assembly.series_planning.confirm_version({
            "workspaceRef": self.context["workspaceRef"], "seriesPlanRef": second["plan"]["seriesPlanRef"],
            "seriesPlanVersionRef": second["version"]["seriesPlanVersionRef"],
            "expectedPlanVersion": second["plan"]["version"], "humanConfirmed": True,
        })
        workspace = self.m6.get_workspace(
            self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"]
        )
        self.assertEqual(workspace["sourceCompatibility"], "STALE")
        self.assertEqual(workspace["activeBaseline"]["contentDigest"], old_digest)

    def test_replacement_activation_supersedes_then_confirms_in_event_order(self):
        bible, characters = confirmed_components(self.assembly, self.context)
        activate = {
            **base_command(self.context, "activate-initial"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": characters["version"]["characterContinuityVersionRef"],
            "expectedActivationRevision": 0,
            "approvalRef": "approval-human",
        }
        first = self.m6.activate_baseline(activate)
        v2 = self.m6.create_bible_version({
            **base_command(self.context, "bible-v2-create"),
            "seriesBibleRef": bible["root"]["seriesBibleRef"],
            "expectedRevision": bible["root"]["revision"],
            "candidate": True,
            "content": bible_content("location-v2"),
        })
        v2 = self.m6.confirm_bible_version({
            **base_command(self.context, "bible-v2-confirm"),
            "seriesBibleRef": v2["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": v2["version"]["seriesBibleVersionRef"],
            "expectedRevision": v2["root"]["revision"],
            "approvalRef": "approval-human",
        })
        source = self.assembly.series_planning.get_confirmed_m6_source_snapshot(
            self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"]
        )
        cv2 = self.m6.create_character_version({
            **base_command(self.context, "character-v2-create"),
            "characterContinuityRef": characters["root"]["characterContinuityRef"],
            "expectedRevision": characters["root"]["revision"],
            "candidate": True,
            "seriesBibleRef": v2["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": v2["version"]["seriesBibleVersionRef"],
            "content": character_content(
                [item["episodePlanItemRef"] for item in source["episodePlanItems"]], "location-v2"
            ),
        })
        cv2 = self.m6.confirm_character_version({
            **base_command(self.context, "character-v2-confirm"),
            "characterContinuityRef": cv2["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": cv2["version"]["characterContinuityVersionRef"],
            "expectedRevision": cv2["root"]["revision"],
            "approvalRef": "approval-human",
        })
        second = self.m6.activate_baseline({
            **base_command(self.context, "activate-replacement"),
            "seriesBibleRef": v2["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": v2["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": cv2["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": cv2["version"]["characterContinuityVersionRef"],
            "expectedActivationRevision": 1,
            "approvalRef": "approval-human",
        })
        self.assertEqual(second["activationRevision"], 2)
        events = self.m6.get_outbox()
        self.assertEqual(
            [item["eventType"] for item in events],
            ["M6BaselineConfirmed", "M6BaselineSuperseded", "M6BaselineConfirmed"],
        )
        workspace = self.m6.get_workspace(
            self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"]
        )
        self.assertEqual(workspace["activeBaseline"]["m6BaselineSnapshotRef"], second["m6BaselineSnapshotRef"])
        self.assertEqual([item["status"] for item in workspace["baselineHistory"]], ["SUPERSEDED", "ACTIVE"])
        self.assertNotEqual(first["contentDigest"], second["contentDigest"])

    def test_outbox_failure_rolls_back_without_partial_snapshot_or_event(self):
        failures = {"enabled": False}
        def hook(_event):
            if failures["enabled"]:
                raise RuntimeError("outbox failed")
        assembly, context = seed_assembly(outbox_hook=hook)
        bible, characters = confirmed_components(assembly, context)
        failures["enabled"] = True
        with self.assertRaises(RuntimeError):
            assembly.series_intelligence.activate_baseline({
                **base_command(context, "outbox-fail"),
                "seriesBibleRef": bible["root"]["seriesBibleRef"],
                "seriesBibleVersionRef": bible["version"]["seriesBibleVersionRef"],
                "characterContinuityRef": characters["root"]["characterContinuityRef"],
                "characterContinuityVersionRef": characters["version"]["characterContinuityVersionRef"],
                "expectedActivationRevision": 0,
                "approvalRef": "approval-human",
            })
        self.assertEqual(assembly.series_intelligence.diagnostic_snapshot()["snapshotCount"], 0)
        self.assertEqual(assembly.series_intelligence.get_outbox(), [])

    def test_poisoned_assembly_rejects_m6_reads_and_writes(self):
        self.assembly.state.register_resource(
            "m6-fault", lambda: {}, lambda _snapshot: (_ for _ in ()).throw(RuntimeError("undo"))
        )
        with self.assembly.state.lease(
            workspace_ref=self.context["workspaceRef"], operation=LifecycleOperation.CREATE_PROJECT
        ) as lease:
            with self.assertRaises(LifecycleRollbackError):
                self.assembly.state.apply_preimaged(
                    lease, lambda: (_ for _ in ()).throw(RuntimeError("mutation"))
                )
        with self.assertRaises(AssemblyPoisonedError):
            self.m6.get_workspace(self.context["workspaceRef"], self.context["projectRef"], self.context["seriesRef"])
        with self.assertRaises(AssemblyPoisonedError):
            self.m6.create_bible_version({
                **base_command(self.context, "poisoned"), "content": bible_content()
            })


if __name__ == "__main__":
    unittest.main()
