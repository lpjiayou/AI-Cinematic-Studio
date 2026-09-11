"""TEST_ONLY complete original-Owner workset; no live inputs or send paths.

External human/identity/rights/provider/cost/runtime observations are explicit
synthetic trusted ports. Source/Run/M5/M6/Script/M7/input and SQLite are real.
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
from uuid import uuid4

from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.episode_production import public
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_foundation import BackendObservation, RuntimeObservation
from services.v5_core_os.episode_production.generation_dispatch_authority import PinnedApprovalReader, RejectingApprovalReader
from services.v5_core_os.episode_production.generation_dispatch_readers import VerifiedOwnerContribution, VerifiedOriginalObservation
from services.v5_core_os.episode_production.generation_dispatch_composition import compose_generation_dispatch
from services.v5_core_os.lifecycle_integrity.generation_dispatch_coordination import ControlledStorageDomain
from services.v4_platform import MediaJobCoordinator, SqliteMediaJobAdapter
from services.v4_platform.comfyui import ComfyUIConfigurationError, validate_runtime_attestation
from tests.integration.test_generic_upstream_method_closure import (
    load_fixture, GenericRefs, GenericScopeAuthority, GenericApprovalAuthority,
    activate_generic_baseline, SCRIPT_CONTENT_FIELDS, validation_command, source_span, NoCallVideoAdapter,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_series_planning_m5 import valid_candidate
from tests.unit.test_method_aware_input_image_admission_e3a import InputImageFixture, png_bytes
from tests.unit.test_method_aware_media_m10_m11 import method_service
from tests.support.generation_dispatch_fixtures import make_package, ControlledClock, SyntheticOriginals, approval_for


def export_evidence(name, value):
    location = os.environ.get("PKG2_TEST_EVIDENCE_DIR")
    if location:
        path = Path(location) / (name + ".json")
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


class ForwardingSqliteConnection:
    """Test phase observer; every SQL/transaction operation goes to real SQLite."""
    def __init__(self, connection, observer):
        object.__setattr__(self, "inner", connection)
        object.__setattr__(self, "observer", observer)

    def __getattr__(self, name): return getattr(self.inner, name)
    def __setattr__(self, name, value): setattr(self.inner, name, value)
    def execute(self, sql, *args):
        result = self.inner.execute(sql, *args)
        self.observer("AFTER_" + sql.strip().split()[0].upper(), self.inner)
        return result
    def commit(self):
        self.observer("BEFORE_COMMIT", self.inner)
        result = self.inner.commit()
        self.observer("AFTER_COMMIT", self.inner)
        return result
    def rollback(self):
        self.observer("BEFORE_ROLLBACK", self.inner)
        result = self.inner.rollback()
        self.observer("AFTER_ROLLBACK", self.inner)
        return result
    def close(self):
        self.observer("BEFORE_CLOSE", self.inner)
        result = self.inner.close()
        self.observer("AFTER_CLOSE", self.inner)
        return result
    def __enter__(self): self.inner.__enter__(); return self
    def __exit__(self, *args): return self.inner.__exit__(*args)


# Exactly one bounded cooperative CPU helper may be alive. The task runner
# pins these bytes and the interpreter/arguments; this is never a business worker.
COOPERATIVE_ACCESS_HELPER = r'''
import json, os, select, sys
from pathlib import Path
sys.dont_write_bytecode = True
root, database, repository = (Path(x).resolve() for x in sys.argv[1:])
assert root.is_absolute() and database.is_relative_to(root)
assert Path(os.environ['TMPDIR']).resolve() == root
observed = {'sqliteConnections': 0, 'networkCalls': 0, 'processCalls': 0}
def audit(event, args):
    if event == 'sqlite3.connect':
        assert Path(os.fsdecode(args[0])).resolve() == database
        observed['sqliteConnections'] += 1
    if event.startswith('socket.') and event != 'socket.__new__':
        observed['networkCalls'] += 1
        raise RuntimeError('helper network prohibited')
    if event == 'subprocess.Popen' or event.startswith('os.exec') or event in ('os.system','os.posix_spawn','os.posix_spawnp'):
        observed['processCalls'] += 1
        raise RuntimeError('helper subprocess prohibited')
sys.addaudithook(audit)
sys.path.insert(0, str(repository))
from services.v4_platform.media_jobs import SqliteMediaJobAdapter
from services.v4_platform.generation_dispatch_jobs import storage_access_snapshot
adapter = SqliteMediaJobAdapter(database, initialize_if_missing=False)
connection = adapter._connect()
try:
    connection.execute('BEGIN IMMEDIATE')
    print(json.dumps({'phase':'READY', 'pid':os.getpid(), 'inTransaction':connection.in_transaction,
        'access':storage_access_snapshot(database), 'fileIdentity':[database.stat().st_dev,database.stat().st_ino]}), flush=True)
    assert select.select([sys.stdin], [], [], 10)[0], 'bounded parent release missing'
    assert sys.stdin.readline().strip() == 'release'
    connection.rollback()
finally:
    connection.close()
print(json.dumps({'phase':'RELEASED', 'access':storage_access_snapshot(database), 'isolation':observed}), flush=True)
'''


def schema_snapshot(paths):
    result = {}
    for path in paths:
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA query_only=ON")
            result[path.name] = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        finally:
            connection.close()
    return result


class ObservedClock(ControlledClock):
    def __init__(self):
        super().__init__()
        self.on_now = None

    def now(self):
        if self.on_now is not None:
            self.on_now()
        return super().now()

def seed_native_portrait_roots(assembly: LifecycleAssembly, fixture: dict) -> dict:
    workspace = fixture["workspaceRef"]
    profile = fixture["contentProfileRef"]
    series = assembly.series_episode.create_series(
        {
            "workspaceRef": workspace,
            "contentProfileRef": profile,
            "title": fixture["series"]["title"],
            "description": fixture["series"]["description"],
            "plannedEpisodeCount": 1,
        }
    )
    project = assembly.project_context.create_project(
        {
            "workspaceRef": workspace,
            "contentProfileRef": profile,
            "projectType": "series",
            "seriesRef": series["seriesRef"],
            "title": fixture["project"]["title"],
            "description": fixture["project"]["description"],
            "targetPlatform": "technical-evidence",
            "aspectRatio": "9:16",
            "plannedEpisodeCount": 1,
        }
    )
    director_plan = valid_plan()
    director_plan["storyDirection"]["title"] = fixture["episode"]["title"]
    director_plan["productionPlan"]["characters"] = [
        item["name"] for item in fixture["characters"]
    ]
    brief = valid_brief()
    brief["character"] = "Ari Vale and Mina Sol"
    creative = assembly.series_episode.confirm_creative_plan(
        {
            "workspaceRef": workspace,
            "humanConfirmed": True,
            "sourcePlanRef": "director-plan-generic-upstream",
            "sourcePlanSchemaVersion": director_plan["schemaVersion"],
            "sourcePlanVersion": 1,
            "brief": brief,
            "sourcePlan": director_plan,
        }
    )
    episode = assembly.series_episode.create_episode(
        {
            "workspaceRef": workspace,
            "seriesRef": series["seriesRef"],
            "creativePlanRef": creative["creativePlanRef"],
            "episodeNumber": 1,
            "seasonNumber": 1,
            "volumeNumber": 1,
            "title": fixture["episode"]["title"],
        }
    )
    candidate = valid_candidate(1)
    candidate["seriesConcept"] = "A generic technical relay-recovery series."
    candidate["episodePlanItems"][0]["title"] = fixture["episode"]["title"]
    initial_plan = assembly.series_planning.confirm_candidate(
        {
            "workspaceRef": workspace,
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "humanConfirmed": True,
            "candidate": candidate,
        }
    )
    bound_plan = assembly.series_planning.create_episode_plan_item_binding_version(
        {
            "workspaceRef": workspace,
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "seriesPlanRef": initial_plan["plan"]["seriesPlanRef"],
            "expectedPlanVersion": initial_plan["plan"]["version"],
            "episodePlanItemBindings": [
                {
                    "episodeRef": episode["episodeRef"],
                    "episodePlanItemRef": initial_plan["version"][
                        "episodePlanItems"
                    ][0]["episodePlanItemRef"],
                }
            ],
        }
    )
    assembly.series_planning.confirm_version(
        {
            "workspaceRef": workspace,
            "seriesPlanRef": bound_plan["plan"]["seriesPlanRef"],
            "seriesPlanVersionRef": bound_plan["version"]["seriesPlanVersionRef"],
            "expectedPlanVersion": bound_plan["plan"]["version"],
            "humanConfirmed": True,
        }
    )
    historical = assembly.script_studio.create_version(
        {
            "workspaceRef": workspace,
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "changeKind": "ai-generation",
            "content": deepcopy(fixture["scriptContent"]),
        }
    )
    baseline = activate_generic_baseline(assembly, fixture)
    successor_content = deepcopy(
        {
            field: historical["scriptVersion"][field]
            for field in SCRIPT_CONTENT_FIELDS
        }
    )
    successor_content["scenes"][1]["productionNotes"].append(
        "Bind this version to the active episode baseline."
    )
    bound_script = assembly.script_studio.create_version(
        {
            "workspaceRef": workspace,
            "projectRef": project["projectRef"],
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "scriptRef": historical["script"]["scriptRef"],
            "baseScriptVersionRef": historical["scriptVersion"][
                "scriptVersionRef"
            ],
            "changeKind": "manual-edit",
            "content": successor_content,
        }
    )
    assembly.script_studio.confirm_version(
        {
            "workspaceRef": workspace,
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "scriptRef": bound_script["script"]["scriptRef"],
            "scriptVersionRef": bound_script["scriptVersion"][
                "scriptVersionRef"
            ],
            "humanConfirmed": True,
        }
    )
    return {
        "project": project,
        "series": series,
        "episode": episode,
        "historical": historical,
        "boundScript": bound_script,
        "baseline": baseline,
    }


class TestOnlyExternalOwners:
    """Explicit independent CPU sources, pinned as full original test files.

    This is not a real deployment/rights/Owner adapter. It never supplies the
    formal upstream read set, queue behavior or Grant persistence.
    """
    TEST_ONLY = True

    def __init__(self, fixture):
        self.fixture = fixture
        self.template, self.attestation = make_package()
        self.originals = {}
        for key in c.PREREQUISITES:
            self.originals[key] = {"TEST_ONLY": True, "scope": deepcopy(fixture.scope),
                "authorityRef": "test-independent-" + key,
                "acceptedScriptVersionRef": fixture.seed["boundScript"]["scriptVersion"]["scriptVersionRef"],
                "acceptedScriptVersionDigest": c.digest(fixture.seed["boundScript"]["scriptVersion"]),
                "decision": "APPROVED_FOR_SYNTHETIC_CPU_FIXTURE", "evidence": key}
        self.prerequisites = {k: {"ref": "test-" + k, "digest": c.digest(v)} for k, v in self.originals.items()}
        cost = self.template["materials"]["costBasis"]
        self.proof_files, self.proof_originals, self.proof_roles = {}, {}, {}
        self.proof_read_observations = []
        self.expected_proof_objects = []
        attestation_ref = self.attestation["attestationRef"]
        self._store_proof("attestation", attestation_ref, self.attestation,
            "RUNTIME_PROCESS", "RuntimeAttestation", self.attestation["payloadDigest"])
        self.template["plan"]["executionBinding"]["runtimeBinding"]["attestationFileSha256"] = self.proof_files[attestation_ref]["sha256"]
        # These are independently retained TEST_ONLY originals, not reconstructed
        # from the old fixture's illustrative pin digests. Every original carries
        # the unchanged rate/bound values and continuing-charge responsibility.
        source_pins = []
        for role, reference in (("source:0", "test-billing-primary"),
                ("source:1", "test-billing-secondary"), ("continuing", "test-continuing")):
            original = self._cost_original(reference, cost)
            self._store_proof(role, reference, original, "V4_BACKEND_CONFIG", "CostEvidence", c.digest(original))
            pin = {"ref": reference, "digest": c.digest(original)}
            if role.startswith("source:"):
                source_pins.append(pin)
            else:
                cost["billingResponsibility"]["continuingChargesEvidence"] = pin
        cost["sourceEvidence"] = sorted(source_pins, key=lambda item: item["ref"])
        cost["reviewDecision"] = deepcopy(self.prerequisites["costReview"])
        cost.pop("payloadDigest")
        self.template["materials"]["costBasis"] = c.sealed(cost)
        self.template["plan"]["executionBinding"]["costBasis"] = {
            "ref": cost["costBasisRef"], "digest": self.template["materials"]["costBasis"]["payloadDigest"]}
        self.expected_proof_objects.sort(key=lambda item: (item["owner"], item["objectKind"], item["objectRef"]))
        self.path = fixture.root / "test-external-owners.json"
        value = {"templateMaterials": self.template["materials"],
            "backendBinding": self.template["plan"]["executionBinding"],
            "attestation": self.attestation, "originals": self.originals}
        self.path.write_bytes(c.canonical(value))
        self.pin = sha256(self.path.read_bytes()).hexdigest()
        self.calls = []
        self.approval_original = None

    def _cost_original(self, reference, cost):
        return {"schemaVersion": "test-only.cost-evidence.v1", "TEST_ONLY": True,
            "evidenceRef": reference, "scope": deepcopy(self.fixture.scope),
            "sourceAuthorityRef": "test-independent-cost-source", "costBasisRef": cost["costBasisRef"],
            "currency": cost["currency"], "validFrom": cost["validFrom"], "validUntil": cost["validUntil"],
            "costScope": cost["costScope"],
            "rateAndBounds": {key: cost[key] for key in ("fixedCostMinor", "computeUnitSeconds",
                "computeUnitCostMinor", "computeMinimumUnits", "storageBoundMinor", "transferBoundMinor",
                "otherBoundMinor", "roundingMode")},
            "continuingCharges": {"outsideWindow": "TEST_ONLY_RENTAL_AND_STORAGE_CAN_CONTINUE",
                "automaticStopOnComfyUIExit": False,
                "powerStopOwnerRef": cost["billingResponsibility"]["powerStopOwnerRef"],
                "dataRetentionOwnerRef": cost["billingResponsibility"]["dataRetentionOwnerRef"]}}

    def _store_proof(self, role, reference, original, owner, kind, object_digest):
        path = self.fixture.root / ("test-proof-" + role.replace(":", "-") + ".json")
        raw = c.canonical(original) + b"\n"
        path.write_bytes(raw)
        self.proof_files[reference] = {"path": path, "sha256": sha256(raw).hexdigest()}
        self.proof_originals[reference] = deepcopy(original)
        self.proof_roles[role] = reference
        # Expected values are built from fixture creation originals and the
        # explicit role mapping, independently of production proof-set helpers.
        self.expected_proof_objects.append({"owner": owner, "objectKind": kind,
            "objectRef": reference, "objectDigest": object_digest})

    def _read_proof(self, reference, proof_files, lease, error_code):
        lease.assert_held()
        specification = proof_files.get(reference)
        c.require(type(specification) is dict, error_code)
        path = specification["path"]
        try:
            c.require(path.is_absolute() and path.is_relative_to(self.fixture.root)
                and not path.is_symlink(), error_code)
            before = path.stat()
            raw = path.read_bytes()
            after = path.stat()
        except OSError as exc:
            self.proof_read_observations.append({"reference": reference, "path": str(path),
                "stage": "ORIGINAL_UNAVAILABLE", "errorCode": error_code})
            raise c.DispatchError(error_code) from exc
        c.require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            and sha256(raw).hexdigest() == specification["sha256"], error_code)
        try:
            original = c.strict_json(raw)
        except c.DispatchError as exc:
            raise c.DispatchError(error_code) from exc
        self.proof_read_observations.append({"reference": reference, "path": str(path),
            "stage": "INDEPENDENT_PIN_VERIFIED", "fileSha256": sha256(raw).hexdigest(),
            "bytes": len(raw), "fileIdentity": [after.st_dev, after.st_ino], "TEST_ONLY": True})
        return original, sha256(raw).hexdigest()

    def _runtime_original(self, lease, proof_files):
        reference = self.template["plan"]["executionBinding"]["backendDecision"]["runtimeAttestationRef"]
        original, file_sha = self._read_proof(reference, proof_files, lease, "RUNTIME_CHANGED")
        try:
            facts = validate_runtime_attestation(original)
        except (ComfyUIConfigurationError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise c.DispatchError("RUNTIME_CHANGED") from exc
        decision = self.template["plan"]["executionBinding"]["backendDecision"]
        c.require(original["attestationRef"] == reference
            and original["payloadDigest"] == decision["runtimeAttestationDigest"]
            and original["capabilityMode"] == "IMAGE_TO_VIDEO"
            and facts["modelFiles"] == self.template["materials"]["backendProfile"]["modelFiles"], "RUNTIME_CHANGED")
        self.proof_read_observations.append({"reference": reference, "stage": "ORIGINAL_VALIDATED",
            "validator": "services.v4_platform.comfyui.validate_runtime_attestation",
            "objectDigest": original["payloadDigest"], "fileSha256": file_sha, "TEST_ONLY": True})
        return original, file_sha

    def _cost_proof_observations(self, package, lease, proof_files):
        cost = c.validate_cost(package["materials"]["costBasis"])
        pins = [*cost["sourceEvidence"], cost["billingResponsibility"]["continuingChargesEvidence"]]
        observations, seen = [], {}
        for pin in pins:
            original, file_sha = self._read_proof(pin["ref"], proof_files, lease, "COST_BOUND_UNVERIFIED")
            c.require(original == self._cost_original(pin["ref"], cost)
                and c.digest(original) == pin["digest"], "COST_BOUND_UNVERIFIED")
            self.proof_read_observations.append({"reference": pin["ref"], "stage": "ORIGINAL_VALIDATED",
                "validator": "TEST_ONLY complete rate/bound and continuing-charge responsibility comparison",
                "objectDigest": c.digest(original), "fileSha256": file_sha, "TEST_ONLY": True})
            if pin["ref"] in seen:
                c.require(seen[pin["ref"]] == pin["digest"], "COST_BOUND_UNVERIFIED")
                continue
            seen[pin["ref"]] = pin["digest"]
            observations.append(VerifiedOriginalObservation("V4_BACKEND_CONFIG", "CostEvidence", pin["ref"], original))
        return tuple(observations)

    def proof_material_port(self, role=None, fault=None):
        return TestOnlyProofMaterialPort(self, role, fault)

    def proof_evidence(self):
        return {"TEST_ONLY": True, "expectedObjects": deepcopy(self.expected_proof_objects),
            "originals": [{"reference": reference, "original": deepcopy(self.proof_originals[reference]),
                "path": str(specification["path"]), "independentFilePin": specification["sha256"]}
                for reference, specification in sorted(self.proof_files.items())],
            "actualReadsAndValidation": deepcopy(self.proof_read_observations)}

    def read_original_file(self, lease):
        lease.assert_held()
        before = self.path.stat()
        raw = self.path.read_bytes()
        after = self.path.stat()
        c.require(self.path.is_absolute() and not self.path.is_symlink()
            and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
              == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            and sha256(raw).hexdigest() == self.pin, "CONFIG_CHANGED")
        self.calls.append("pinned-original-reread")
        return json.loads(raw)

    def verify_subject(self, resolved, lease):
        value = self.read_original_file(lease)
        for original in value["originals"].values():
            c.require(original["scope"] == resolved.scope
                and original["acceptedScriptVersionRef"] == resolved.subject["scriptVersion"]["ref"]
                and original["acceptedScriptVersionDigest"] == resolved.subject["scriptVersion"]["digest"], "SOURCE_CHANGED")
        return value

    def prepare_prerequisites(self, resolved, command, lease):
        del command
        value = self.verify_subject(resolved, lease)
        return {k: {"ref": "test-" + k, "digest": c.digest(v)} for k, v in value["originals"].items()}

    def backend(self, package, lease):
        del package
        data = self.read_original_file(lease)
        m, b = data["templateMaterials"], data["backendBinding"]
        return BackendObservation(b["backendDecision"], m["backendProfile"], m["executionConfig"], b["executionCode"])

    def runtime(self, package, lease):
        del package
        data = self.read_original_file(lease)
        original, file_sha = self._runtime_original(lease, self.proof_files)
        return RuntimeObservation(data["templateMaterials"]["processIdentity"],
            file_sha, original)

    def cost(self, package, lease):
        del package
        return self.read_original_file(lease)["templateMaterials"]["costBasis"]

    def prepare_materials(self, resolved, command, lease):
        del command
        self.verify_subject(resolved, lease)
        return {"backend": self.backend(None, lease), "runtime": self.runtime(None, lease), "costBasis": self.cost(None, lease)}

    def current_prerequisites(self, resolved, package, approval, phase, lease):
        data = self.verify_subject(resolved, lease)
        mapping = {"scriptOwnerAcceptance": ("V5_SCRIPT", None), "costReview": ("V4_BACKEND_CONFIG", None),
            "identityReferenceEvaluation": ("V5_IDENTITY", "CURRENT_IDENTITY_REFERENCE"),
            "rightsEvaluation": ("V5_RIGHTS", "CURRENT_RIGHTS_EVALUATION"),
            "providerPolicyEvaluation": ("V5_PROVIDER_POLICY", "CURRENT_PROVIDER_POLICY")}
        originals, selectors = [], {}
        for kind, (owner, selector) in mapping.items():
            original = data["originals"][kind]
            observation = VerifiedOriginalObservation(owner, kind, "test-" + kind, original)
            originals.append(observation)
            pin = {"ref": observation.object_ref, "digest": observation.as_object()["objectDigest"]}
            c.require(pin == package["materials"]["prerequisiteEvidence"][kind], "SOURCE_CHANGED")
            if selector:
                selectors[selector] = (pin["ref"], pin["digest"])
        if phase != "PREPARE":
            c.require(approval is not None and self.approval_original is not None, "APPROVAL_UNAVAILABLE")
            originals.extend((VerifiedOriginalObservation("OWNER_APPROVAL", "OwnerDecision",
                approval["authorityDecisionRef"], deepcopy(approval), "authorityDecisionDigest"),
                VerifiedOriginalObservation("OWNER_APPROVAL", "ApprovalOriginal",
                    approval["approvalEvidenceRef"], deepcopy(self.approval_original))))
            selectors["CURRENT_OWNER_APPROVAL"] = (approval["authorityDecisionRef"], approval["authorityDecisionDigest"])
        return VerifiedOwnerContribution(tuple(originals), selectors)

    def current_materials(self, resolved, package, approval, phase, lease):
        return self._current_materials(resolved, package, approval, phase, lease, self.proof_files)

    def _current_materials(self, resolved, package, approval, phase, lease, proof_files):
        del resolved, approval, phase
        m = self.read_original_file(lease)["templateMaterials"]
        b = package["plan"]["executionBinding"]
        observations = (
            VerifiedOriginalObservation("V4_BACKEND_CONFIG", "ExecutionConfig", m["executionConfig"]["configRef"], m["executionConfig"]),
            VerifiedOriginalObservation("V4_BACKEND_CONFIG", "BackendProfile", b["executionProfile"]["ref"], m["backendProfile"]),
            VerifiedOriginalObservation("V4_BACKEND_CONFIG", "CostBasis", m["costBasis"]["costBasisRef"], m["costBasis"], "payloadDigest"),
            VerifiedOriginalObservation("RUNTIME_PROCESS", "ProcessIdentity", m["processIdentity"]["instanceRef"], m["processIdentity"]),
        )
        attestation, file_sha = self._runtime_original(lease, proof_files)
        c.require(file_sha == b["runtimeBinding"]["attestationFileSha256"], "RUNTIME_CHANGED")
        proofs = (VerifiedOriginalObservation("RUNTIME_PROCESS", "RuntimeAttestation",
            attestation["attestationRef"], attestation, "payloadDigest"),
            *self._cost_proof_observations(package, lease, proof_files))
        return VerifiedOwnerContribution((*observations, *proofs), {
            "CURRENT_BACKEND_CONFIG": (observations[0].object_ref, observations[0].as_object()["objectDigest"]),
            "CURRENT_RUNTIME_PROCESS": (observations[3].object_ref, observations[3].as_object()["objectDigest"])})


class TestOnlyProofContribution(VerifiedOwnerContribution):
    """Negative fixture: valid originals are followed by a corrupt contribution.

    This deliberately preserves the original defect's order: original readers
    and production original validation succeed, then final objects lose binding.
    """
    def __init__(self, contribution, reference, fault, log):
        super().__init__(contribution.originals, contribution.selectors)
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "fault", fault)
        object.__setattr__(self, "log", log)

    def read(self):
        objects, selectors = super().read()
        indexes = [index for index, item in enumerate(objects) if item["objectRef"] == self.reference]
        c.require(len(indexes) == 1, "SOURCE_CHANGED")
        index = indexes[0]
        before = deepcopy(objects[index])
        if self.fault == "omit_contribution":
            objects.pop(index)
        elif self.fault == "wrong_ref":
            objects[index]["objectRef"] = "test-unrelated-proof"
        elif self.fault == "wrong_digest":
            objects[index]["objectDigest"] = "f" * 64
        elif self.fault == "wrong_owner":
            objects[index]["owner"] = "OWNER_APPROVAL"
        else:
            raise AssertionError("unknown TEST_ONLY proof fault")
        self.log.append({"TEST_ONLY": True, "stage": "CONTRIBUTION_FAULT_AFTER_ORIGINAL_VALIDATION",
            "reference": self.reference, "fault": self.fault, "originalObject": before})
        return objects, selectors


class TestOnlyProofMaterialPort:
    """Selected only through the original controlled material-port boundary."""
    def __init__(self, external, role, fault):
        self.external, self.role, self.fault = external, role, fault
        self.proof_files = deepcopy(external.proof_files)
        if fault is not None:
            if role not in external.proof_roles:
                raise AssertionError("unknown TEST_ONLY proof role")
            if fault == "missing_original":
                reference = external.proof_roles[role]
                path = external.fixture.root / ("test-missing-proof-" + role.replace(":", "-") + ".json")
                if path.exists():
                    raise AssertionError("negative proof path already exists")
                self.proof_files[reference]["path"] = path

    def prepare(self, *args):
        return self.external.prepare_materials(*args)

    def read_current(self, resolved, package, approval, phase, lease):
        contribution = self.external._current_materials(resolved, package, approval, phase, lease, self.proof_files)
        if self.fault is not None and self.fault != "missing_original":
            return TestOnlyProofContribution(contribution, self.external.proof_roles[self.role],
                self.fault, self.external.proof_read_observations)
        return contribution


class BindingFixture(InputImageFixture):
    """Reuse only the original input-authority fixture's command/file helpers."""
    def __init__(self, case):
        self.temp = tempfile.TemporaryDirectory(prefix="test-pkg2-")
        case.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        os.chmod(self.root, 0o700)
        self.fixture = fixture = load_fixture()
        self.refs = GenericRefs(fixture)
        self.clock = ObservedClock()
        # The original lifecycle contract uses milliseconds; Grant retains its
        # Accepted six-digit trusted-clock encoding. They denote the same time.
        self.core_clock = lambda: self.clock.now().replace(".000000Z", ".000Z")
        self.assembly = LifecycleAssembly.sqlite(self.root / "lifecycle.sqlite3", initialize_or_upgrade=True,
            ref_factory=self.refs, clock=self.core_clock, m6_scope_authority=GenericScopeAuthority(),
            m6_approval_authority=GenericApprovalAuthority(), canonical_target_ref="test-pkg2-canonical-target")
        self.seed = seed_native_portrait_roots(self.assembly, fixture)
        self.seed["assembly"] = self.assembly
        self.boundary = public.create_local_development_boundary(self.root / "runs.sqlite3",
            project_boundary=self.assembly.project_context, series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning, script_studio_boundary=self.assembly.script_studio,
            ref_factory=self.refs, clock=self.core_clock)
        self.seed["boundary"] = self.boundary
        script = self.seed["boundScript"]["scriptVersion"]
        budgets = self.v2_shot_budgets(script)
        root_command = {k: fixture[k] for k in ("workspaceRef", "projectRef", "seriesRef", "episodeRef")}
        self.run = self.boundary.create_run({**root_command, "idempotencyKey": "test-pkg2-run", "shotBudgets": budgets})
        self.seed["run"] = self.run
        validation = self.boundary.create_narrative_validation(validation_command(fixture, self.run, key="test-pkg2-m7"))
        shots = []
        for index, budget in enumerate(budgets):
            scene = next(s for s in script["scenes"] if s["scriptSceneRef"] == budget["scriptSceneRef"])
            duration = budget["durationFrames"]
            selected = index == 0
            beats = [{"beatRef": "test-pkg2-beat-" + str(index), "beatOrder": 1,
                "sourceSpan": source_span(scene, "ACTION"), "subjectRefs": [fixture["characters"][0]["characterRef"]],
                "targetRefs": [], "frameRangeStartInclusive": 0, "frameRangeEndExclusive": 48 if selected else duration,
                "executionClass": "MICRO_MOTION" if selected else "STATIC_HOLD"}]
            if selected and duration > 48:
                beats.append({**deepcopy(beats[0]), "beatRef": "test-pkg2-static-tail", "beatOrder": 2,
                    "frameRangeStartInclusive": 48, "frameRangeEndExclusive": duration, "executionClass": "STATIC_HOLD"})
            shots.append({"shotOrder": index + 1, "shotFrameCount": duration,
                "cameraInstruction": {"framing": "MEDIUM_CLOSE_UP", "movement": "LOCKED"},
                "actionExecutionBeats": beats, "audioIntents": []})
        self.plan = self.boundary.create_execution_method_plan({**root_command,
            "productionRunRef": self.run["productionRunRef"],
            "consistencyValidationVersionRef": validation["consistencyValidationVersionRef"],
            "shots": shots, "idempotencyKey": "test-pkg2-method-plan"})
        self.requirement = next(r for r in self.plan["visualExecutionRequirements"] if r["executionClass"] == "MICRO_MOTION")
        self.scope = {k: self.plan[k] for k in c.SCOPE_FIELDS}
        self.evidence = method_service(self.boundary).evidence_repository
        self.review = method_service(self.boundary).candidate_review
        self.sqlite, self.manifest_v2 = True, True
        self.source_root = self.root / "sources"
        self.source_root.mkdir()
        self.content = png_bytes()
        self.content_digest = sha256(self.content).hexdigest()
        self.source = self.source_root / (self.content_digest + ".png")
        self.source.write_bytes(self.content)
        intake, qc, selection = self.selected()
        admission = self.boundary.admit_public_method_aware_input_image(self.admission_command(selection))
        self.asset = admission["assetVersion"]
        self.input_plan = self.boundary.create_method_aware_input_plan({**self.scope,
            "executionMethodPlanVersionRef": self.plan["executionMethodPlanVersionRef"],
            "assetBindings": [self.binding(self.asset)], "idempotencyKey": "test-pkg2-input-plan"})
        self.queue_path = self.root / "queue.sqlite3"
        self.queues = [SqliteMediaJobAdapter(self.queue_path) for _ in range(2)]
        self.coordinators = [MediaJobCoordinator(q, NoCallVideoAdapter(), artifact_root=self.root / "artifacts",
            clock=self.clock.now, ref_factory=lambda prefix: prefix + "-" + uuid4().hex) for q in self.queues]
        self.external = TestOnlyExternalOwners(self)
        self.originals = SyntheticOriginals()
        self.domain = ControlledStorageDomain(self.root, [self.root / "lifecycle.sqlite3", self.root / "runs.sqlite3",
            self.root / "runs.sqlite3.evidence.sqlite3", self.root / "runs.sqlite3.production-policy.sqlite3", self.queue_path])
        case.addCleanup(self.domain.close)
        self.dispatch = compose_generation_dispatch(lifecycle=self.assembly,
            root_service=self.boundary._EpisodeProductionPublicBoundary__service,
            method_media=method_service(self.boundary), input_assets=self.boundary._EpisodeProductionPublicBoundary__method_aware_input_assets,
            policy_service=self.boundary._EpisodeProductionPublicBoundary__production_policy,
            queue_coordinators=self.coordinators, storage_domain=self.domain, workspace_ref=self.scope["workspaceRef"],
            technical_target_id="test-pkg2-single-anchor", clock=self.clock, approval_reader=RejectingApprovalReader(),
            prerequisite_reader=SimpleNamespace(prepare=self.external.prepare_prerequisites, read_current=self.external.current_prerequisites),
            material_reader=SimpleNamespace(prepare=self.external.prepare_materials, read_current=self.external.current_materials),
            backend_reader=SimpleNamespace(read_current=self.external.backend), runtime_reader=SimpleNamespace(read_current=self.external.runtime),
            cost_reader=SimpleNamespace(read_current=self.external.cost), issuer_service_ref="test-cpu-v5-issuer")

    def prepare_command(self):
        method = next(m for m in self.input_plan["methodInputPlans"] if m["executionClass"] == "MICRO_MOTION")
        return {"workspaceRef": self.scope["workspaceRef"], "productionRunRef": self.scope["productionRunRef"],
            "methodAwareInputPlanVersionRef": self.input_plan["methodAwareInputPlanVersionRef"],
            "creativeShotVersionRef": method["creativeShotVersionRef"], "beatRef": method["beatRef"],
            "inputAssetVersionRef": self.asset["assetVersionRef"], "backendRef": "test-backend",
            "executionConfigRef": "test-config", "costBasisRef": "test-cost",
            "limits": deepcopy(self.external.template["plan"]["limits"])}

    def prepare(self):
        # Domain method keeps unexpected implementation errors visible in tests.
        return self.dispatch.boundary._preparation.prepare(self.prepare_command())

    def approve_package(self, package):
        approval = approval_for(package)
        self.external.approval_original = {"TEST_ONLY": True, "authorityRef": "test-owner",
            "actorRef": "test-human-lead", "scope": deepcopy(self.scope),
            "approvedPlanDigest": c.digest(package["plan"]), "decision": "EXACT_SUBJECT_GENERATION_EXECUTION"}
        approval["approvalEvidenceDigest"] = c.digest(self.external.approval_original)
        approval = c.sealed(approval, "authorityDecisionDigest")
        self.originals.register(approval)
        bundle = {"schemaVersion": c.APPROVAL_SCHEMA, "authorityRef": "test-owner",
            "approvals": [{"planPackage": deepcopy(package), "approval": approval}]}
        path = self.root / "test-generation-approval.json"
        path.write_bytes(c.canonical(bundle))
        reader = PinnedApprovalReader(path, sha256(path.read_bytes()).hexdigest(), original=self.originals)
        self.dispatch.selections["approval"].select_port(reader)
        self.approval = approval
        return approval

    def issue(self):
        prepared = self.prepare()
        command = self.approved_issue_command(prepared)
        result = self.dispatch.boundary.issue(command)
        return result

    def approved_issue_command(self, prepared):
        package = prepared["planPackage"]
        self.approve_package(package)
        command = {k: v for k, v in self.prepare_command().items() if k not in {"executionConfigRef", "costBasisRef", "limits"}}
        command.update(expectedSubjectDigest=prepared["subjectDigest"], expectedApprovedPlanDigest=prepared["approvedPlanDigest"],
            authorityDecisionRef=self.approval["authorityDecisionRef"], idempotencyKey="test-pkg2-grant", snapshotTokens=prepared["snapshotTokens"])
        self.issue_command = deepcopy(command)
        return command

    def route(self, grant, key="test-route-one", routing=None):
        return (routing or self.dispatch.routing).route_for_grant(self.scope["workspaceRef"],
            self.scope["productionRunRef"], grant["generationDispatchGrantRef"], idempotency_key=key)

    def jobs(self):
        return self.queues[0].list(self.scope["workspaceRef"], self.scope["productionRunRef"])


def advance_native_m6(seed, workspace_ref):
    assembly = seed["assembly"]
    project = seed["project"]
    series = seed["series"]
    context = {
        "workspaceRef": workspace_ref,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
    }
    workspace = assembly.series_intelligence.get_workspace(
        workspace_ref, project["projectRef"], series["seriesRef"]
    )

    def operation(name):
        return {
            **context,
            "operationRef": name,
            "idempotencyKey": name,
        }

    bible_root = workspace["seriesBible"]
    bible_version = workspace["seriesBibleVersions"][-1]
    bible_content = deepcopy(bible_version["content"])
    bible_content["worldRules"][0]["statement"] += "；校验规则已更新"
    new_bible = assembly.series_intelligence.create_bible_version(
        {
            **operation("m7-bible-v2-create"),
            "seriesBibleRef": bible_root["seriesBibleRef"],
            "expectedRevision": bible_root["revision"],
            "candidate": True,
            "content": bible_content,
        }
    )
    new_bible = assembly.series_intelligence.confirm_bible_version(
        {
            **operation("m7-bible-v2-confirm"),
            "seriesBibleRef": new_bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": new_bible["version"]["seriesBibleVersionRef"],
            "expectedRevision": new_bible["root"]["revision"],
            "approvalRef": "approval-generic-human",
        }
    )
    character_root = workspace["characterContinuity"]
    character_content = deepcopy(
        workspace["characterContinuityVersions"][-1]["content"]
    )
    new_characters = assembly.series_intelligence.create_character_version(
        {
            **operation("m7-characters-v2-create"),
            "characterContinuityRef": character_root["characterContinuityRef"],
            "expectedRevision": character_root["revision"],
            "candidate": True,
            "seriesBibleRef": new_bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": new_bible["version"]["seriesBibleVersionRef"],
            "content": character_content,
        }
    )
    new_characters = assembly.series_intelligence.confirm_character_version(
        {
            **operation("m7-characters-v2-confirm"),
            "characterContinuityRef": new_characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": new_characters["version"]["characterContinuityVersionRef"],
            "expectedRevision": new_characters["root"]["revision"],
            "approvalRef": "approval-generic-human",
        }
    )
    return assembly.series_intelligence.activate_baseline(
        {
            **operation("m7-baseline-v2-activate"),
            "seriesBibleRef": new_bible["root"]["seriesBibleRef"],
            "seriesBibleVersionRef": new_bible["version"]["seriesBibleVersionRef"],
            "characterContinuityRef": new_characters["root"]["characterContinuityRef"],
            "characterContinuityVersionRef": new_characters["version"]["characterContinuityVersionRef"],
            "expectedActivationRevision": workspace["activeBaseline"]["activationRevision"],
            "approvalRef": "approval-generic-human",
        }
    )
