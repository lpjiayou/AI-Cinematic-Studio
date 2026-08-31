from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from services.v3_render_core import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    IMAGE_PIXEL_DIGEST_SPEC,
)
from services.v4_platform import masked_surface_effects as subject
from services.v5_core_os.episode_production.deterministic_effects import (
    build_flame_extinguish_requirement,
    build_flame_smoke_execution_request,
    build_smoke_requirement,
)
from tests.contract.test_m13_e2_deterministic_effects_contract import (
    _digest,
    _execution_evidence,
    _flame_command,
    _local_chain,
    _seal,
    _smoke_command,
)


class M13E2FlameSmokeV4ContractTests(unittest.TestCase):
    def _flame(self):
        local, _, local_evidence = _local_chain()
        requirement = build_flame_extinguish_requirement(
            _flame_command(local)
        )
        request = build_flame_smoke_execution_request(
            requirement,
            local_exposure_requirement=local,
            local_exposure_result=local_evidence["result"],
        )
        return requirement, request.as_dict()

    def test_accepts_exact_v5_flame_and_both_smoke_source_variants(self):
        _, flame = self._flame()
        self.assertEqual(
            subject.validate_flame_smoke_execution_request(flame), flame
        )
        for procedural in (False, True):
            smoke = build_smoke_requirement(
                _smoke_command(procedural=procedural)
            )
            request = build_flame_smoke_execution_request(smoke).as_dict()
            self.assertEqual(
                subject.validate_flame_smoke_execution_request(request),
                request,
            )

    def test_rejects_resealed_request_parameter_drift_from_requirement(self):
        smoke = build_smoke_requirement(_smoke_command(procedural=True))
        request = build_flame_smoke_execution_request(smoke).as_dict()
        request["opacitySchedule"][0]["valuePermille"] = 999
        request = _seal(request)
        with self.assertRaises(subject.MaskedSurfaceRequestValidationError):
            subject.validate_flame_smoke_execution_request(request)

    def test_rejects_fully_resealed_nonzero_dark_curve(self):
        requirement, request = self._flame()
        requirement_value = requirement.as_dict()
        requirement_value.pop("payloadDigest")
        requirement_value["brightnessCurve"][-1]["valuePermille"] = 100
        request["brightnessCurve"][-1]["valuePermille"] = 100
        request["requirementDigest"] = _digest(requirement_value)
        request["executionRequestRef"] = (
            subject._flame_smoke_execution_request_ref(request)
        )
        request = _seal(request)
        with self.assertRaises(subject.MaskedSurfaceRequestValidationError):
            subject.validate_flame_smoke_execution_request(request)

    def test_rejects_free_filter_path_argv_and_unknown_seed_keys(self):
        smoke = build_smoke_requirement(_smoke_command(procedural=True))
        original = build_flame_smoke_execution_request(smoke).as_dict()
        for key, value in (
            ("filterGraph", "null"),
            ("inputPath", "/tmp/input"),
            ("argv", ["ffmpeg"]),
            ("systemTimeSeed", 1),
        ):
            request = deepcopy(original)
            request[key] = value
            request = _seal(request)
            with self.subTest(key=key):
                with self.assertRaises(
                    subject.MaskedSurfaceRequestValidationError
                ):
                    subject.validate_flame_smoke_execution_request(request)

    def test_rejects_flame_smoke_and_emission_asset_digest_drift(self):
        def resolved_base(binding):
            return {
                **deepcopy(binding),
                "storageKey": "unused/base.mp4",
                "pixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
                "width": 16,
                "height": 12,
                "frameCount": 8,
                "frameRate": 24,
                "pixelFormat": "yuv420p",
            }

        def resolved_image(binding, name):
            return {
                **deepcopy(binding),
                "storageKey": f"unused/{name}.png",
                "pixelDigestSpec": IMAGE_PIXEL_DIGEST_SPEC,
                "pixelMode": "RGBA",
                "width": 8,
                "height": 8,
            }

        _, flame = self._flame()
        smoke = build_flame_smoke_execution_request(
            build_smoke_requirement(_smoke_command(procedural=False))
        ).as_dict()
        cases = (
            (flame, "flameMask"),
            (smoke, "smokeLayer"),
            (smoke, "emissionMask"),
        )
        for request, drifted_name in cases:
            names = (
                ("basePlate", "flameMask")
                if request["effectMode"] == "FLAME_EXTINGUISH"
                else ("basePlate", "emissionMask", "smokeLayer")
            )
            authorities = {
                request[name]["assetVersionRef"]: (
                    resolved_base(request[name])
                    if name == "basePlate"
                    else resolved_image(request[name], name)
                )
                for name in names
            }
            authorities[
                request[drifted_name]["assetVersionRef"]
            ]["fileDigest"] = "sha256:" + "0" * 64
            with self.subTest(asset=drifted_name):
                with self.assertRaises(
                    subject.MaskedSurfaceAssetResolutionError
                ):
                    subject._resolve_flame_smoke_assets(
                        request,
                        authorities,
                        artifact_root=Path.cwd(),
                    )

    def test_rejects_cross_mode_runtime_and_artifact_evidence_swap(self):
        _, flame_request = self._flame()
        smoke = build_smoke_requirement(_smoke_command(procedural=True))
        smoke_request = build_flame_smoke_execution_request(smoke)
        smoke_evidence = _execution_evidence(smoke, smoke_request)
        with self.assertRaisesRegex(
            subject.MaskedSurfaceExecutionError,
            "does not bind the resolved execution request",
        ):
            subject._validate_effect_request_evidence_lineage(
                flame_request,
                smoke_evidence["runtime"],
                smoke_evidence["artifact"],
            )

    def test_rejects_resealed_e2_result_output_drift_from_artifact(self):
        smoke = build_smoke_requirement(_smoke_command(procedural=False))
        request_wrapper = build_flame_smoke_execution_request(smoke)
        request = request_wrapper.as_dict()
        evidence = _execution_evidence(smoke, request_wrapper)
        artifact = evidence["artifact"]
        runtime = evidence["runtime"]
        result = evidence["result"].as_dict()
        binding = {
            "resultRef": result["resultRef"],
            "resultDigest": result["payloadDigest"],
        }
        subject._validate_e2_result_binding(
            result,
            binding=binding,
            request=request,
            artifact=artifact,
            runtime=runtime,
        )
        changed = deepcopy(result)
        changed["outputFileDigest"] = "sha256:" + "0" * 64
        changed = _seal(changed)
        changed_binding = {
            **binding,
            "resultDigest": changed["payloadDigest"],
        }
        with self.assertRaisesRegex(
            subject.MaskedSurfaceExecutionError,
            "Result evidence is stale",
        ):
            subject._validate_e2_result_binding(
                changed,
                binding=changed_binding,
                request=request,
                artifact=artifact,
                runtime=runtime,
            )


if __name__ == "__main__":
    unittest.main()
