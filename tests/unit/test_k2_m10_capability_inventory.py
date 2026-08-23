import unittest

from scripts.k2_m10_comfyui_capability_inventory import analyze_inventory


def node(*required, optional=()):
    return {
        "input": {
            "required": {field: ["VALUE"] for field in required},
            "optional": {field: ["VALUE"] for field in optional},
        }
    }


STATS = {
    "system": {"comfyui_version": "test"},
    "devices": [
        {"name": "NVIDIA A100-PCIE-40GB", "type": "cuda", "vram_total": 1}
    ],
}


class K2M10CapabilityInventoryTests(unittest.TestCase):
    def test_candidate_nodes_are_inventory_not_a_fabricated_pass(self):
        report = analyze_inventory(
            {
                "LoadImage": node("image"),
                "IPAdapterAdvanced": node("model", "image", "image_negative"),
                "Wan22ImageToVideoLatent": node(
                    "vae", "width", "height", optional=("start_image",)
                ),
            },
            STATS,
        )
        self.assertEqual(
            report["decisionState"], "UNPROVEN_CANDIDATE_NODES_DISCOVERED"
        )
        self.assertFalse(report["multiReferenceCapabilityPassed"])
        self.assertTrue(report["loadImagePresent"])
        self.assertTrue(report["wanStartImageInputPresent"])
        self.assertEqual(
            [item["node"] for item in report["candidateNodes"]],
            ["IPAdapterAdvanced"],
        )

    def test_missing_multi_reference_nodes_fail_closed(self):
        report = analyze_inventory(
            {
                "LoadImage": node("image"),
                "Wan22ImageToVideoLatent": node(
                    "vae", "width", "height", optional=("start_image",)
                ),
            },
            STATS,
        )
        self.assertEqual(
            report["decisionState"],
            "BLOCKED_MULTI_REFERENCE_NODES_NOT_DISCOVERED",
        )
        self.assertFalse(report["multiReferenceCapabilityPassed"])

    def test_runtime_requires_exactly_one_cuda_device(self):
        report = analyze_inventory(
            {
                "LoadImage": node("image"),
                "IPAdapter": node("image", "reference_image"),
            },
            {"system": {}, "devices": []},
        )
        self.assertEqual(
            report["decisionState"], "BLOCKED_RUNTIME_NOT_EXACTLY_ONE_CUDA"
        )


if __name__ == "__main__":
    unittest.main()
