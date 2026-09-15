"""D1 trusted-host wiring; no CLI-supplied factories or authority decisions.

The host installs pinned files and independent Owner ports. Offline input checks
read only those files: they never open stores or treat historical runtime as live.
An explicit open wires the same existing Operator, not an alternate executor.
"""
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

from . import generation_dispatch_contracts as c
from .generation_dispatch_authority import read_pinned_file
from .generation_dispatch_live_sources import (
    OriginalFile, PinnedLiveMaterials, PinnedPrerequisiteOriginals)
from .generation_dispatch_operator import ExistingStoreOperatorDeployment, OperatorSelection


class D1OperatorHost:
    """Installed by trusted Python composition, never deserialized from CLI JSON.

    Missing live ports are reportable offline, but cannot create a deployment.
    Store arguments retain the original seven-store factory's validation. No
    default path, authority, budget, validity window or execution permission.
    """
    def __init__(self, *, configuration, input_image, selection=None,
            runtime_original=None, runtime_current=None, cost_owner=None,
            prerequisite_originals=None, prerequisite_verifiers=None,
            approval_original=None, approval_evidence=None, approval_reader=None,
            store_arguments=None, image_video_installation=None):
        c.require(type(configuration) is OriginalFile and type(input_image) is OriginalFile,
            "CONFIG_CHANGED")
        c.require(selection is None or type(selection) is OperatorSelection, "APPROVAL_UNAVAILABLE")
        if selection is not None:
            selection.validate()
        if image_video_installation is not None:
            from .image_video import ImageVideoInstallation
            c.require(type(image_video_installation) is ImageVideoInstallation, "CONFIG_CHANGED")
            image_video_installation.validate()
        self.configuration, self.input_image = configuration, input_image
        self.selection = deepcopy(selection)
        self.runtime_original, self.runtime_current = runtime_original, runtime_current
        self.cost_owner = cost_owner
        self.originals = dict(prerequisite_originals or {})
        self.verifiers = dict(prerequisite_verifiers or {})
        self.approval_original, self.approval_evidence = approval_original, approval_evidence
        self.approval_reader = approval_reader
        self.store_arguments = dict(store_arguments or {})
        self.image_video_installation = image_video_installation

    def _missing(self):
        missing = []
        if self.selection is None:
            missing.append("selection_with_explicit_limits")
        if type(self.runtime_original) is not OriginalFile:
            missing.append("runtime_original")
        for name, port, methods in (
                ("runtime_current", self.runtime_current, ("read_current", "assert_output_available")),
                ("cost_owner", self.cost_owner, ("read_current", "proof_originals")),
                ("approval_reader", self.approval_reader, ("resolve",))):
            if not all(callable(getattr(port, method, None)) for method in methods):
                missing.append(name)
        for kind in sorted(c.PREREQUISITES):
            if type(self.originals.get(kind)) is not OriginalFile:
                missing.append("prerequisite_original:" + kind)
            if not callable(self.verifiers.get(kind)):
                missing.append("prerequisite_verifier:" + kind)
        if not self.store_arguments:
            missing.append("existing_store_bindings")
        return missing

    def check_inputs(self):
        """Only verify actual local input bytes against the selected live profile.

        This is not PREPARE, a current-runtime check, a source-Owner decision or
        proof that stores are ready. Missing facts cannot become zero placeholders.
        """
        from services.v4_platform.generation_dispatch_a14b_live import (
            validate_live_profile, LIVE_ADAPTER_IDENTITY, LIVE_CAPABILITY, LIVE_ENDPOINT_CLASS)
        value = self.configuration.read()
        c.exact(value, {"backendDecision", "backendProfile", "executionConfig", "executionCode", "processIdentity"})
        profile = validate_live_profile(value["backendProfile"])
        config = c.validate_execution_config(value["executionConfig"])
        c.validate_process(value["processIdentity"])
        decision = c.backend.validate_decision(value["backendDecision"])
        c.require(decision["adapterIdentity"] == LIVE_ADAPTER_IDENTITY
            and decision["adapterCapability"] == LIVE_CAPABILITY
            and decision["endpointClass"] == LIVE_ENDPOINT_CLASS
            and decision["backendProfileDigest"] == c.digest(profile)
            and decision["backendRef"] == config["backendRef"], "CONFIG_CHANGED")
        raw = read_pinned_file(self.input_image.path, self.input_image.file_sha256)
        c.require(sha256(raw).hexdigest() == profile["parameters"]["input"]["contentDigest"], "SOURCE_CHANGED")
        # PNG structural/header inspection does not decode media or invoke tools.
        c.require(len(raw) >= 33 and raw[:8] == b"\x89PNG\r\n\x1a\n"
            and raw[8:12] == b"\x00\x00\x00\r" and raw[12:16] == b"IHDR", "SOURCE_CHANGED")
        width, height = int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
        output = profile["parameters"]["nativeOutput"]
        # WanImageToVideo owns resizing. Input identity is its exact byte digest;
        # do not introduce an input-size == output-size contract here.
        c.require(0 < width < 2**31 and 0 < height < 2**31, "SOURCE_CHANGED")
        if self.selection is not None:
            command = self.selection.prepare_command
            c.require(command["backendRef"] == config["backendRef"]
                and command["executionConfigRef"] == config["configRef"], "CONFIG_CHANGED")
        return {"operation": "CHECK_INPUTS_ONLY", "inputBytesMatched": True,
            "inputContentDigest": self.input_image.file_sha256, "inputByteSize": len(raw),
            "inputWidth": width, "inputHeight": height,
            "outputWidth": output["width"], "outputHeight": output["height"],
            "configurationFileSha256": self.configuration.file_sha256,
            "backendProfileDigest": c.digest(profile), "modelRoleCount": len(profile["modelFiles"]),
            "missingBindings": self._missing(), "storesOpened": False,
            "liveCurrentnessChecked": False, "operatorPrepareCompleted": False, "sendPermission": "NONE"}

    def deployment(self):
        # Validate all installed readers before opening even an existing store.
        self.check_inputs()
        c.require(not self._missing(), "CURRENTNESS_FENCE_UNAVAILABLE")
        materials = PinnedLiveMaterials(configuration=self.configuration, runtime_original=self.runtime_original,
            runtime_current=self.runtime_current, cost_owner=self.cost_owner)
        prerequisites = PinnedPrerequisiteOriginals(originals=self.originals, verifiers=self.verifiers,
            approval_original=self.approval_original, approval_evidence=self.approval_evidence)
        forbidden = {"selection", "approval_reader", "prerequisite_reader", "material_reader",
            "backend_reader", "runtime_reader", "cost_reader", "image_video_installation"}
        c.require(not forbidden.intersection(self.store_arguments), "CONFIG_CHANGED")
        return ExistingStoreOperatorDeployment(**self.store_arguments, selection=self.selection,
            approval_reader=self.approval_reader, prerequisite_reader=prerequisites,
            material_reader=materials, backend_reader=SimpleNamespace(read_current=materials.backend),
            runtime_reader=SimpleNamespace(read_current=materials.runtime),
            cost_reader=SimpleNamespace(read_current=materials.cost),
            image_video_installation=self.image_video_installation)

    @contextmanager
    def open(self):
        with self.deployment().open() as operator:
            yield operator
