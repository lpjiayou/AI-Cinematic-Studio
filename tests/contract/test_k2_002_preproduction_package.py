import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_PATH = (
    ROOT
    / "experiments"
    / "k2-002-changan-preproduction"
    / "k2-002-changan-preproduction.v1.json"
)


class K2002PreproductionPackageContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))

    def test_reviewed_candidate_digest_is_exact_and_acceptance_is_not_invented(self):
        source = self.package["source"]
        normalized_source = ROOT / source["repositoryV12NormalizedPath"]
        reviewed = ROOT / source["reviewedCandidatePath"]
        self.assertEqual(
            hashlib.sha256(normalized_source.read_bytes()).hexdigest(),
            source["repositoryV12NormalizedSha256"],
        )
        self.assertEqual(
            hashlib.sha256(reviewed.read_bytes()).hexdigest(),
            source["reviewedCandidateSha256"],
        )
        self.assertEqual(source["ownerAcceptanceState"], "PENDING")
        self.assertFalse(self.package["truthBoundary"]["domainFact"])

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
        self.assertEqual(len(by_key), 14)
        self.assertEqual(
            sum(1 in item["applicableEpisodeNumbers"] for item in requirements),
            12,
        )
        self.assertEqual(
            {
                item["requirementKey"]
                for item in requirements
                if 1 not in item["applicableEpisodeNumbers"]
            },
            {"scene-l2-master", "lantern-entity-01"},
        )
        self.assertEqual(by_key["lamp-primary-01"]["designKey"], "lamp_primary_01")
        self.assertEqual(by_key["lamp-remote-01"]["designKey"], "lamp_remote_01")
        self.assertEqual(
            by_key["lantern-entity-01"]["designKey"], "lantern_entity_01"
        )
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


if __name__ == "__main__":
    unittest.main()
