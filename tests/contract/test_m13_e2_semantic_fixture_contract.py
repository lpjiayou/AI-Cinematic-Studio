from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import unittest


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "m13" / "e2"

EXPECTED_FILES = {
    "sh17_stable_lit_base.ppm": {
        "format": "P3",
        "role": "STABLE_LIT_BASE",
        "byteSize": 2006,
        "fileDigest": (
            "sha256:db4106b0c8979dbab8cb785f87d85db5889362b4f8c7b279949ebf7dcf96d126"
        ),
    },
    "flame_mask.pgm": {
        "format": "P2",
        "role": "FLAME_MASK",
        "byteSize": 460,
        "fileDigest": (
            "sha256:1dd57cb4e4e8e683be943aac20b8aa7cb346da3896fbb831d1582ac7f5c4c9c6"
        ),
    },
    "emission_mask.pgm": {
        "format": "P2",
        "role": "SMOKE_EMISSION_MASK",
        "byteSize": 481,
        "fileDigest": (
            "sha256:09f3a7d0335e64adbad5a0c2277b7ee8d32289707f446068194db9a329852f4d"
        ),
    },
    "pinned_smoke_layer.pgm": {
        "format": "P2",
        "role": "PINNED_SMOKE_LAYER",
        "byteSize": 470,
        "fileDigest": (
            "sha256:cf6c5cdeb7fcee3145d8dd525f13301ce3d36debff3f7666a5ae18163e73b5dc"
        ),
    },
}


class M13E2SemanticFixtureContractTests(unittest.TestCase):
    def test_sh17_to_sh18_fixture_is_exact_local_technical_evidence(self) -> None:
        manifest_path = FIXTURE_ROOT / "manifest.json"
        self.assertTrue(manifest_path.is_file())
        self.assertFalse(manifest_path.is_symlink())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(manifest),
            {
                "schemaVersion",
                "classificationLabels",
                "publicationAllowed",
                "canvas",
                "shots",
                "files",
                "liveAuthority",
                "livePathReferences",
            },
        )
        self.assertEqual(
            manifest["schemaVersion"],
            "m13.e2.flame-smoke-semantic-fixture.v1",
        )
        self.assertEqual(
            manifest["classificationLabels"],
            [
                "K2_SEMANTIC_TECHNICAL_FIXTURE",
                "NOT_LIVE_K2",
                "NOT_ADMITTED",
                "NOT_SELECTED",
                "NOT_MASTER",
            ],
        )
        self.assertIs(manifest["publicationAllowed"], False)
        self.assertIs(manifest["liveAuthority"], False)
        self.assertEqual(manifest["livePathReferences"], [])
        self.assertEqual(
            manifest["canvas"],
            {"width": 16, "height": 12, "maxSampleValue": 255},
        )

        self.assertEqual(
            manifest["shots"],
            [
                {
                    "fixtureShotId": "SH17",
                    "semanticIntent": (
                        "Stable lit technical base plate before deterministic "
                        "flame extinguish."
                    ),
                    "sourceRole": "STABLE_LIT_BASE",
                    "sourceFile": "sh17_stable_lit_base.ppm",
                },
                {
                    "fixtureShotId": "SH18",
                    "semanticIntent": (
                        "Deterministic flame extinction, local exposure "
                        "darkening, and one thin smoke plume derived from SH17."
                    ),
                    "sourceRole": "DERIVED_EFFECT_TARGET",
                    "sourceFiles": [
                        "sh17_stable_lit_base.ppm",
                        "flame_mask.pgm",
                        "emission_mask.pgm",
                        "pinned_smoke_layer.pgm",
                    ],
                },
            ],
        )

        listed = {
            item["path"]: {
                key: value for key, value in item.items() if key != "path"
            }
            for item in manifest["files"]
        }
        self.assertEqual(len(manifest["files"]), len(EXPECTED_FILES))
        self.assertEqual(listed, EXPECTED_FILES)
        fixture_root = FIXTURE_ROOT.resolve(strict=True)
        for relative, expected in EXPECTED_FILES.items():
            with self.subTest(relative=relative):
                posix_path = PurePosixPath(relative)
                self.assertFalse(posix_path.is_absolute())
                self.assertNotIn("..", posix_path.parts)
                source = FIXTURE_ROOT.joinpath(*posix_path.parts)
                self.assertTrue(source.is_file())
                self.assertFalse(source.is_symlink())
                self.assertEqual(source.resolve(strict=True).parent, fixture_root)
                content = source.read_bytes()
                self.assertEqual(len(content), expected["byteSize"])
                self.assertEqual(
                    "sha256:" + sha256(content).hexdigest(),
                    expected["fileDigest"],
                )


if __name__ == "__main__":
    unittest.main()
