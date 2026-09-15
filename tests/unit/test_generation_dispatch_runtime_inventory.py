"""Synthetic metadata only: additions must not conceal selected runtime drift."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_live_sources import (
    LiveRuntimeCurrentReader, OriginalFile, PinnedLiveMaterials,
)
from tests.unit.test_generation_dispatch_d1_live import live_profile, live_runtime


class RuntimeInventoryCompatibilityTests(unittest.TestCase):
    def fixture(self, *, enable=True):
        temporary = TemporaryDirectory(prefix="test-runtime-inventory-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        def file(name, value):
            raw = c.canonical(value)
            path = root / name
            path.write_bytes(raw)
            return OriginalFile(path, sha256(raw).hexdigest())
        nodes = {
            "LoadImage": {"input": {"required": {"image": [["anchor.png", "retained.png"], {"image_upload": True}]}}},
            "LoadImageMask": {"input": {"required": {"image": [["anchor.png"], {"image_upload": True}]}}},
            "LoadAudio": {"input": {"required": {"audio": ["COMBO", {"options": ["old.wav"]}]}}},
            "LoadVideo": {"input": {"required": {"file": ["COMBO", {"options": ["old.mp4"]}]}}},
            "UNETLoader": {"input": {"required": {"unet_name": [["selected.safetensors"]]}}},
        }
        profile = live_profile()
        original = live_runtime(profile)
        original["facts"]["objectInfoDigest"] = c.digest(nodes)
        original = c.sealed({**original, "factsDigest": c.digest(original["facts"])})
        current = deepcopy(nodes)
        current["LoadImage"]["input"]["required"]["image"][0].append("unrelated.png")
        configuration = {"backendProfile": profile, "processIdentity": original["facts"]["processIdentity"],
            "executionConfig": {"launchConfiguration": original["facts"]["launchConfiguration"],
                "launchConfigDigest": original["facts"]["launchConfigDigest"],
                "inputRoot": {"absolutePathDigest": "1" * 64}, "artifactRoot": {"absolutePathDigest": "2" * 64}}}
        source = {"inputName": profile["parameters"]["input"]["imageName"],
            "contentDigest": profile["parameters"]["input"]["contentDigest"],
            "inputRootDigest": "1" * 64, "outputRootDigest": "2" * 64, "outputPrefixAbsent": True}
        f = SimpleNamespace(nodes=nodes, current=current, original=original, source=source,
            configuration=configuration, lease=SimpleNamespace(assert_held=lambda: None), facts_delta={},
            evidence=None)
        def observe(config, lease):
            result = deepcopy(original)
            result["facts"].update(objectInfoDigest=c.digest(f.current), **f.facts_delta)
            result["factsDigest"] = c.digest(result["facts"])
            return c.sealed(result)
        reader = LiveRuntimeCurrentReader(host_observer=observe,
            input_observer=lambda config, lease: deepcopy(f.source),
            tool_observer=lambda: deepcopy(profile["parameters"]["postprocess"]["toolIdentity"]))
        f.inventory_file = file("nodes.json", nodes)
        if enable:
            reader = reader.with_file_inventory_baseline(f.inventory_file,
                lambda config, lease: deepcopy(f.current if f.evidence is None else f.evidence))
        f.reader = reader
        f.materials = PinnedLiveMaterials(configuration=file("configuration.json", configuration),
            runtime_original=file("runtime.json", original), runtime_current=reader,
            cost_owner=SimpleNamespace(read_current=lambda *a: None, proof_originals=lambda *a: ()))
        # Unrelated backend selection is tested by the existing Operator suite.
        f.materials._read = lambda lease: deepcopy(configuration)
        return f

    def assert_rejected(self, f, code="RUNTIME_CHANGED"):
        with self.assertRaises(c.DispatchError) as stopped:
            f.materials.runtime(None, f.lease)
        self.assertEqual(stopped.exception.code, code)

    def test_material_reader_additions_preserve_original_and_actual_digest(self):
        f = self.fixture()
        before = deepcopy(f.original)
        result = f.materials.runtime(None, f.lease)
        self.assertEqual(result.attestation, before)
        observed = f.reader.read_current(f.configuration, f.lease)
        self.assertEqual(observed["objectInfoDigest"], c.digest(f.current))
        self.assertNotEqual(observed["objectInfoDigest"], before["facts"]["objectInfoDigest"])
        self.assertEqual(f.original, before)

    def test_default_reader_without_original_inventory_remains_strict(self):
        self.assert_rejected(self.fixture(enable=False))

    def test_all_four_file_lists_allow_additions_only(self):
        for node, key, tail in (("LoadImage", "image", None), ("LoadImageMask", "image", None),
                ("LoadAudio", "audio", "options"), ("LoadVideo", "file", "options")):
            f = self.fixture()
            target = f.current[node]["input"]["required"][key]
            values = target[1][tail] if tail else target[0]
            values.insert(0, "new-unrelated-file")
            self.assertEqual(f.materials.runtime(None, f.lease).attestation, f.original)

    def test_removal_reorder_duplicate_type_or_node_contract_change_rejected(self):
        for mutation in (lambda n: n["LoadImage"]["input"]["required"]["image"][0].remove("anchor.png"),
                lambda n: n["LoadImage"]["input"]["required"]["image"][0].reverse(),
                lambda n: n["LoadImage"]["input"]["required"]["image"][0].append("anchor.png"),
                lambda n: n["LoadImage"]["input"]["required"].update(image="invalid"),
                lambda n: n["LoadImage"]["input"]["required"]["image"][1].update(image_upload=False),
                lambda n: n["UNETLoader"]["input"]["required"]["unet_name"][0].append("other-model"),
                lambda n: n.update(NewNode={}), lambda n: n.pop("LoadVideo")):
            f = self.fixture()
            mutation(f.current)
            self.assert_rejected(f)

    def test_wrong_original_pin_or_current_preimage_rejected(self):
        f = self.fixture()
        f.evidence = f.nodes
        self.assert_rejected(f)
        f = self.fixture()
        f.inventory_file.path.write_bytes(b'{}')
        self.assert_rejected(f, "APPROVAL_UNAVAILABLE")

    def test_input_bytes_and_non_inventory_facts_remain_strict(self):
        f = self.fixture()
        f.source["contentDigest"] = "f" * 64
        self.assert_rejected(f, "SOURCE_CHANGED")
        f = self.fixture()
        f.facts_delta["pythonVersion"] = "changed"
        self.assert_rejected(f)

    def test_fresh_read_cannot_reuse_previous_compatible_result(self):
        f = self.fixture()
        f.materials.runtime(None, f.lease)
        f.current["LoadImage"]["input"]["required"]["image"][0].remove("anchor.png")
        self.assert_rejected(f)
