import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_PATH = (
    ROOT
    / "experiments"
    / "k2-002-changan-preproduction"
    / "k2-002-changan-preproduction.v2.json"
)
HISTORICAL_PACKAGE_PATH = (
    ROOT
    / "experiments"
    / "k2-002-changan-preproduction"
    / "k2-002-changan-preproduction.v1.json"
)


class K2002PreproductionPackageContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
        cls.historical_package = json.loads(
            HISTORICAL_PACKAGE_PATH.read_text(encoding="utf-8")
        )

    def test_v14_rebase_lineage_is_exact_and_acceptance_is_not_invented(self):
        source = self.package["source"]
        normalized_source = ROOT / source["repositoryV12NormalizedPath"]
        prior_reviewed = ROOT / source["priorCoreReviewedV13Path"]
        external_v14 = ROOT / source["externalOwnerRevisionV14Path"]
        active_v14 = ROOT / source["activeRevisionCandidatePath"]
        self.assertEqual(
            hashlib.sha256(normalized_source.read_bytes()).hexdigest(),
            source["repositoryV12NormalizedSha256"],
        )
        self.assertEqual(
            hashlib.sha256(prior_reviewed.read_bytes()).hexdigest(),
            source["priorCoreReviewedV13Sha256"],
        )
        self.assertEqual(
            hashlib.sha256(external_v14.read_bytes()).hexdigest(),
            source["externalOwnerRevisionV14Sha256"],
        )
        self.assertEqual(
            hashlib.sha256(active_v14.read_bytes()).hexdigest(),
            source["activeRevisionCandidateSha256"],
        )
        self.assertEqual(
            source["repositoryIngestAuthorizationState"], "OWNER_AUTHORIZED"
        )
        self.assertEqual(
            source["scriptOwnerAcceptanceState"],
            "PENDING_EXPLICIT_CONTENT_ACCEPTANCE",
        )
        self.assertFalse(self.package["truthBoundary"]["domainFact"])

    def test_historical_v13_package_and_candidate_are_immutable_evidence(self):
        self.assertEqual(
            hashlib.sha256(HISTORICAL_PACKAGE_PATH.read_bytes()).hexdigest(),
            "b9ee0ac17d5bacdc0b7c4bd65abf5a009b8de169326d37b3d08f5652e97db7a7",
        )
        source = self.historical_package["source"]
        reviewed = ROOT / source["reviewedCandidatePath"]
        self.assertEqual(
            hashlib.sha256(reviewed.read_bytes()).hexdigest(),
            "5e33f3469765a79c91ef0c4ffa150e259d500bc596d2eef94da1fc6441a7ae8f",
        )
        self.assertEqual(source["ownerAcceptanceState"], "PENDING")

    def test_repository_text_digests_are_lf_checkout_stable(self):
        attributes = set(
            (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        )
        for path in (
            "docs/16-k2-production/k2-002-changan/"
            "K2-002-CHANGAN-SERIES-AND-EP01-03-v1.3.md",
            "docs/16-k2-production/k2-002-changan/"
            "K2-002-CHANGAN-SERIES-AND-EP01-03-v1.4.md",
            "docs/16-k2-production/k2-002-changan/source/"
            "K2-002-CHANGAN-SOURCE-v1.2.md",
            "docs/16-k2-production/k2-002-changan/source/"
            "K2-002-CHANGAN-UPLOADED-OWNER-REVISION-v1.4.md",
        ):
            self.assertIn(
                f"{path} text eol=lf whitespace=-trailing-space",
                attributes,
            )

    def test_ep01_has_twelve_exact_contiguous_shots_and_720_frames(self):
        shots = self.package["episode01"]["shots"]
        self.assertEqual(len(shots), 12)
        self.assertEqual([item["globalOrder"] for item in shots], list(range(1, 13)))
        self.assertEqual(
            [item["durationFrames"] for item in shots],
            [60, 60, 48, 60, 60, 48, 60, 60, 48, 72, 72, 72],
        )
        self.assertEqual(sum(item["durationFrames"] for item in shots), 720)
        self.assertTrue(all(item["actionBeat"].strip() for item in shots))
        self.assertTrue(all("dialogueRequirement" in item for item in shots))
        self.assertTrue(
            all(item["dialogueRequirement"]["text"].strip() for item in shots)
        )
        self.assertEqual(shots[10]["dialogueRequirement"]["text"], "今夜，")
        self.assertEqual(
            shots[11]["dialogueRequirement"]["text"], "你能认出几个字？"
        )
        self.assertEqual(
            shots[2]["dialogueRequirement"]["text"],
            "浮出了一个不该存在的字。",
        )
        self.assertIn("空白名牌", shots[7]["actionBeat"])
        self.assertEqual(
            shots[2]["postprocessRequirements"][0]["inputAssetRequirementKeys"],
            [
                "residual-scroll-master",
                "modern-tweezers-action",
                "ep01-postprocess-manifest",
            ],
        )
        self.assertEqual(
            shots[7]["postprocessRequirements"][0]["inputAssetRequirementKeys"],
            [
                "nameplate-blank-v1",
                "scene-l1-master",
                "scene-l1-north-rack-slot-anchor",
                "ep01-postprocess-manifest",
            ],
        )
        self.assertEqual(
            shots[9]["dialogueRequirement"],
            {
                "speaker": None,
                "text": "一次克制吸气，无台词。",
                "sourceMode": "SFX_OR_SILENCE",
            },
        )
        self.assertEqual(shots[9]["dialogueSyncMode"], "NONE")

    def test_mixed_identity_and_non_lipsync_dialogue_are_explicit(self):
        shots = self.package["episode01"]["shots"]
        self.assertEqual(
            shots[9]["visibleIdentityBindings"],
            [
                {"characterName": "沈知微", "bindingMode": "FACE_LOCK"},
                {"characterName": "裴昀", "bindingMode": "BODY_ONLY"},
            ],
        )
        for shot in shots:
            if shot["dialogueRequirement"]["sourceMode"] in {"DIALOGUE", "NARRATION"}:
                self.assertEqual(
                    shot["dialogueSyncMode"],
                    "OFF_CAMERA_OR_NON_VISIBLE_MOUTH",
                )

    def test_vertical_profiles_and_controlled_extension_are_exact(self):
        profile = self.package["outputProfile"]
        self.assertEqual(profile["generationCanvas"], {"width": 704, "height": 1280, "aspectRatio": "11:20"})
        self.assertEqual(profile["editMaster"], {"width": 720, "height": 1280, "aspectRatio": "9:16"})
        self.assertEqual(profile["releaseMaster"], {"width": 1080, "height": 1920, "aspectRatio": "9:16"})
        algorithm = profile["controlledExtensionAlgorithm"]
        canonical = json.dumps(
            algorithm,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            profile["controlledExtensionAlgorithmDigest"],
        )
        self.assertFalse(algorithm["cropAllowed"])
        self.assertFalse(algorithm["stretchAllowed"])

    def test_missing_assets_and_all_generation_paths_remain_fail_closed(self):
        requirements = self.package["requiredAssets"]
        self.assertEqual(
            [item["designFilename"] for item in requirements[:6]],
            [
                "shen_front_CROP.png",
                "shen_3q_a_CROP.png",
                "shen_3q_b_CROP.png",
                "pei_front_CROP.png",
                "pei_3q_CROP.png",
                "pei_x_CROP.png",
            ],
        )
        self.assertTrue(all(item["status"] != "ADMITTED" for item in requirements))
        by_key = {item["requirementKey"]: item for item in requirements}
        self.assertEqual(len(by_key), 24)
        self.assertEqual(
            sum(1 in item["applicableEpisodeNumbers"] for item in requirements),
            16,
        )
        self.assertEqual(
            {
                item["requirementKey"]
                for item in requirements
                if 1 not in item["applicableEpisodeNumbers"]
            },
            {
                "scene-l2-master",
                "lantern-entity-01",
                "copper-mirror-primary",
                "glyph-guan-v1",
                "glyph-shi-v1",
                "shen-wrist-scar-overlay",
                "ep02-postprocess-manifest",
                "ep03-postprocess-manifest",
            },
        )
        self.assertEqual(by_key["lamp-primary-01"]["designKey"], "lamp_primary_01")
        self.assertEqual(by_key["lamp-remote-01"]["designKey"], "lamp_remote_01")
        self.assertEqual(
            by_key["lantern-entity-01"]["designKey"], "lantern_entity_01"
        )
        self.assertEqual(
            by_key["nameplate-blank-v1"]["designKey"], "nameplate_blank_01"
        )
        self.assertEqual(
            by_key["scene-l1-north-rack-slot-anchor"]["designKey"],
            "L1_NORTH_RACK_SLOT",
        )
        self.assertIn("residual-scroll-master", by_key)
        self.assertIn("modern-tweezers-action", by_key)
        boundary = self.package["truthBoundary"]
        self.assertFalse(boundary["providerDispatchAllowed"])
        self.assertFalse(boundary["legacyExecutionAllowed"])
        self.assertFalse(boundary["candidateAdmissionAllowed"])
        self.assertFalse(boundary["gpuDispatchStarted"])
        self.assertFalse(boundary["bulkGenerationAllowed"])
        self.assertFalse(boundary["publicationAllowed"])
        self.assertEqual(
            boundary["shotPlanAuthorityState"],
            "LOCAL_STRUCTURAL_REPRESENTATION_NOT_APPROVED",
        )
        self.assertEqual(boundary["shotPlanApprovalState"], "NOT_VERIFIED")

        for shot in self.package["episode01"]["shots"]:
            for requirement in shot["postprocessRequirements"]:
                self.assertTrue(requirement["inputAssetRequirementKeys"])
                self.assertTrue(
                    set(requirement["inputAssetRequirementKeys"]) <= set(by_key)
                )

    def test_external_asset_evidence_and_ep01_continuity_remain_fail_closed(self):
        evidence = self.package["externalAssetEvidence"]
        self.assertEqual(
            evidence["packageSha256"],
            "532765d91b56692e611cabb9fcbd3d8ecc916f169f5c4e2b3b9e82a56bbe99c6",
        )
        self.assertEqual(evidence["assetVersionAdmissionState"], "NONE_ADMITTED")
        self.assertEqual(evidence["scriptBindingState"], "V1_3_STALE_FOR_V1_4")
        continuity = self.package["episode01"]["continuityStateAtEpisodeEnd"]
        self.assertTrue(
            {
                "episodeId",
                "lanternTransitionState",
                "sceneState",
                "sceneAnchorVersionRefs",
                "characterMemoryState",
                "shenChoice",
                "assetVersionRefs",
                "shotGraphDigest",
                "qcDecisionRef",
            }
            <= set(continuity)
        )
        self.assertEqual(continuity["recognizedCharacterCount"], 1)
        self.assertEqual(continuity["unlockedCharacterCount"], 2)
        self.assertEqual(continuity["characterGateState"], "EP02_UNLOCKED")
        self.assertEqual(continuity["lampRemote01State"], "OFF")
        self.assertEqual(continuity["nameplateLocation"], "L1_NORTH_RACK_SLOT")
        self.assertEqual(continuity["nameplateInscriptionState"], "BLANK")
        self.assertEqual(continuity["lastTraceDamageState"], "PROTECTED")
        self.assertEqual(continuity["sceneAnchorVersionRefs"], [])
        self.assertEqual(continuity["sceneAnchorAuthorityState"], "NOT_READY")
        self.assertEqual(continuity["assetVersionRefs"], [])
        self.assertEqual(continuity["assetVersionAuthorityState"], "NONE_ADMITTED")
        self.assertIsNone(continuity["shotGraphDigest"])
        self.assertEqual(continuity["shotGraphState"], "NOT_COMPILED")
        self.assertIsNone(continuity["qcDecisionRef"])
        self.assertEqual(continuity["qcDecisionState"], "NOT_STARTED")


if __name__ == "__main__":
    unittest.main()
