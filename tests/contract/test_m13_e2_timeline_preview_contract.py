from __future__ import annotations

from copy import deepcopy
import unittest

from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.timeline_preview import (
    EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION,
    EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V2,
    TimelinePreviewContractError,
    TimelineSourceBindingError,
    _effect_preview_bindings,
)


def _binding(ordinal: int, effect_mode: str) -> dict:
    digest = format(ordinal + 1, "x") * 64
    return {
        "clipRef": f"effect-clip-{ordinal}",
        "clipDigest": digest,
        "effectMode": effect_mode,
        "requirementRef": f"effect-requirement-{ordinal}",
        "requirementDigest": digest,
        "resultRef": f"effect-result-{ordinal}",
        "resultDigest": digest,
        "executionRequestRef": f"effect-execution-{ordinal}",
        "executionRequestDigest": digest,
        "artifactEvidenceRef": f"effect-artifact-{ordinal}",
        "artifactEvidenceDigest": digest,
        "runtimeEvidenceRef": f"effect-runtime-{ordinal}",
        "runtimeEvidenceDigest": digest,
        "frameRangeStartInclusive": 0,
        "frameRangeEndExclusive": 24,
    }


GLYPH = {
    "clipRef": "glyph-effect-clip",
    "clipDigest": "a" * 64,
    "requirementRef": "glyph-requirement",
    "requirementDigest": "b" * 64,
}


class M13E2TimelinePreviewContractTests(unittest.TestCase):
    def test_legacy_two_stage_digest_is_unchanged(self) -> None:
        bindings = [
            _binding(0, "SCRATCH_REVEAL"),
            _binding(1, "LOCAL_EXPOSURE"),
        ]
        normalized, glyph, digest = _effect_preview_bindings(
            bindings, GLYPH
        )
        self.assertEqual(normalized, bindings)
        self.assertEqual(glyph, GLYPH)
        self.assertEqual(
            digest,
            _digest(
                {
                    "schemaVersion": EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION,
                    "effectResultBindings": bindings,
                    "glyphRequirementBinding": GLYPH,
                }
            ),
        )

    def test_e2_four_stage_profile_has_additive_digest_version(self) -> None:
        bindings = [
            _binding(0, "LIGHT_SWEEP"),
            _binding(1, "LOCAL_EXPOSURE"),
            _binding(2, "FLAME_EXTINGUISH"),
            _binding(3, "SMOKE"),
        ]
        normalized, glyph, digest = _effect_preview_bindings(
            bindings, GLYPH
        )
        self.assertEqual(normalized, bindings)
        self.assertEqual(glyph, GLYPH)
        self.assertEqual(
            digest,
            _digest(
                {
                    "schemaVersion": EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V2,
                    "effectResultBindings": bindings,
                    "glyphRequirementBinding": GLYPH,
                }
            ),
        )

    def test_partial_or_reordered_e2_profile_is_rejected(self) -> None:
        profile = [
            _binding(0, "SCRATCH_REVEAL"),
            _binding(1, "LOCAL_EXPOSURE"),
            _binding(2, "FLAME_EXTINGUISH"),
            _binding(3, "SMOKE"),
        ]
        with self.assertRaises(TimelinePreviewContractError):
            _effect_preview_bindings(profile[:3], GLYPH)
        reordered = deepcopy(profile)
        reordered[2], reordered[3] = reordered[3], reordered[2]
        with self.assertRaises(TimelineSourceBindingError):
            _effect_preview_bindings(reordered, GLYPH)


if __name__ == "__main__":
    unittest.main()
