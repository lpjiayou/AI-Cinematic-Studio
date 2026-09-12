"""Offline explicit-input candidate builder. No network, subprocess or archive execution.

Run as a module. Output must be a NEW directory outside the repository. Original
bytes stay in their archives; generated objects are drafts, never authority bundles.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from services.v4_platform.backend_registry import canonical, digest
from services.v4_platform.comfyui_a14b_sources import (
    archive_bytes, strict_json, verify_hash_list, camera_candidate, historical_digest_map)
from services.v4_platform.generation_dispatch_a14b_exact import (
    EXACT_PROFILE_SCHEMA, EXACT_COMPILER_IDENTITY, EXACT_TEMPLATE_REF,
    encoding_profile, compile_exact_workflow, exact_readiness)
from services.v4_platform.generation_dispatch_a14b_profile import A14B_FINAL_OUTPUT, COMFYUI_COMMIT


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def build(task_raw, task_sha, recovered_raw, recovered_sha, tools):
    task = archive_bytes(task_raw, task_sha)
    verify_hash_list(task)
    manifest = strict_json(task["INPUT_MANIFEST.json"])
    recovered = archive_bytes(recovered_raw, recovered_sha)
    packs = {}
    for item in manifest["archives"]:
        raw = recovered[item["fileName"]]
        require(len(raw) == item["byteSize"], "original archive size changed")
        packs[item["role"]] = archive_bytes(raw, item["sha256"])
        verify_hash_list(packs[item["role"]])
    source, runtime = packs["SH09"], packs["RUNTIME"]
    # The recovered consolidated package must contain byte-identical runtime originals.
    for name, raw in runtime.items():
        require(packs["CONSOLIDATED"]["runtime/"+name] == raw, "consolidated/runtime original mismatch")
    original_raw = source["SPIKE0_SH09_WORKFLOW_CANDIDATE.json"]
    original = strict_json(original_raw)
    original_pins = manifest["originalWorkflow"]
    require(sha256(original_raw).hexdigest() == original_pins["fileSha256"]
        and digest(original) == original_pins["canonicalDigest"], "original graph mismatch")
    proposal = strict_json(task["candidate_only/SH09_LOCKED_PROMPT_PROPOSAL.json"])
    require(sha256(source["SH09_PROMPT_BINDING.json"]).hexdigest() == proposal["sourcePromptFileSha256"], "prompt source mismatch")
    candidate = camera_candidate(original, proposal["replacement"]["old"], proposal["replacement"]["new"])
    require(candidate == strict_json(task["candidate_only/DRAFT_SH09_LOCKED_WORKFLOW.json"])
        and digest(candidate) == proposal["proposedWorkflowCanonicalDigest"], "candidate camera delta mismatch")
    for actual, pin in ((original["20"]["inputs"]["text"],proposal["sourcePositivePromptUtf8Sha256"]),
            (candidate["20"]["inputs"]["text"],proposal["proposedPositivePromptUtf8Sha256"]),
            (candidate["21"]["inputs"]["text"],proposal["unchangedNegativePromptUtf8Sha256"])):
        require(sha256(actual.encode("utf-8")).hexdigest() == pin, "prompt UTF8 digest mismatch")
    image = source[manifest["input"]["logicalFileName"]]
    require(sha256(image).hexdigest() == manifest["input"]["sha256"] and len(image) == manifest["input"]["byteSize"], "input original mismatch")
    confirmations = source["OWNER_CONFIRMATIONS.json"]
    require(sha256(confirmations).hexdigest() == manifest["existingOwnerConfirmations"]["sha256"], "owner confirmation original mismatch")
    for name in ("OWNER_CONFIRMATIONS.json", "POSTPROCESS_PROFILE_SOURCE.json", "SH09_PROMPT_BINDING.json", "SPIKE0_SH09_WORKFLOW_CANDIDATE.json"):
        require(source[name] == task["private_source_metadata/"+name], "source metadata copy mismatch")
    mapping = historical_digest_map(runtime["GPU_RUNTIME_ATTESTATION.json"], runtime["DIGEST_PREIMAGES.json"],
        runtime["MODEL_MANIFEST.json"], manifest["models"])
    source_binding = strict_json(source["SPIKE0_SH09_EXECUTION_BINDING.json"])
    require(source_binding["payloadDigest"] == digest({k:v for k,v in source_binding.items() if k != "payloadDigest"}), "source binding seal changed")
    require(set(source_binding["modelBindingsBySha"]) == {m["sourceBindingRole"] for m in manifest["models"]}, "source model role set changed")
    for model in manifest["models"]:
        require(source_binding["modelBindingsBySha"][model["sourceBindingRole"]] == {"file":model["name"],"sha256":model["sha256"]}, "binding/runtime model mismatch")
    require(source_binding["modelSetDigest"] == mapping["sourceModelSetDigest"]
        and source_binding["launchConfigDigest"] == mapping["sourceLaunchDigest"]
        and source_binding["seed"] == manifest["parameters"]["seed"], "source binding preimages mismatch")
    nodes = strict_json(runtime["COMFYUI_AND_NODE_MANIFEST.json"])
    require(nodes["COMFYUI_VERSION"] == "0.35.0" and nodes["COMFYUI_COMMIT"] == COMFYUI_COMMIT, "version/commit source mismatch")
    mapping.update(sourceComfyuiVersion=nodes["COMFYUI_VERSION"], ownerConfirmationsFileSha256=sha256(confirmations).hexdigest(),
        instanceConfirmation="PRESERVED_FROM_ORIGINAL_NOT_CURRENTNESS", frameSelectionConfirmation="PRESERVED_0_TO_47_DROP_48")
    models = mapping["contractModelPreimage"]
    by_role = {m["role"]:m for m in models}
    pairs = []
    for index,(expert,lora) in enumerate((("HIGH_NOISE_EXPERT","HIGH_NOISE_LORA"),("LOW_NOISE_EXPERT","LOW_NOISE_LORA"))):
        pairs.append({"expertRole":expert,"expertSha256":by_role[expert]["sha256"],"loraRole":lora,
            "loraSha256":by_role[lora]["sha256"],"strengthModel":1.0,"modelShift":8.0,"startAtStep":index*2,
            "endAtStep":(index+1)*2,"addNoise":"enable" if index==0 else "disable",
            "returnWithLeftoverNoise":"enable" if index==0 else "disable"})
    profile = {"schemaVersion":EXACT_PROFILE_SCHEMA,"modelFiles":models,"parameters":{
        "compilerIdentity":EXACT_COMPILER_IDENTITY,"templateRef":EXACT_TEMPLATE_REF,"evidenceClass":"OFFLINE_SOURCE_CANDIDATE",
        "cameraDisposition":"PROPOSED_PENDING_OWNER_ACCEPTANCE","comfyuiCommit":COMFYUI_COMMIT,
        "positivePrompt":candidate["20"]["inputs"]["text"],"negativePrompt":candidate["21"]["inputs"]["text"],
        "seed":manifest["parameters"]["seed"],"steps":4,"cfg":1.0,"samplerName":"euler","scheduler":"simple",
        "modelPairs":pairs,"input":{"imageName":manifest["input"]["logicalFileName"],"contentDigest":manifest["input"]["sha256"]},
        "nativeOutput":{"nodeId":"41","mediaType":"image/png","frameCount":49,"width":704,"height":1280,
            "filenamePrefix":candidate["41"]["inputs"]["filename_prefix"]},"postprocess":encoding_profile(tools),
        "resourceRequirements":{"gpuCount":1,"minimumVramBytes":strict_json(runtime["GPU_RUNTIME_ATTESTATION.json"])["VRAM_TOTAL_BYTES"]["torchCudaVisibleTotal"],"deviceType":"cuda"}}}
    mapping["historicalVramObservations"] = strict_json(runtime["GPU_RUNTIME_ATTESTATION.json"])["VRAM_TOTAL_BYTES"]
    mapping["candidateResourcePolicy"] = "PIN_HISTORICAL_TORCH_CUDA_VISIBLE_TOTAL_NOT_BOARD_TOTAL_NOT_CURRENT_OBSERVATION"
    # These refs are compiler-only placeholders, explicitly not a V5 admitted Asset.
    compiler_source = {"assetRef":"offline-candidate-not-admitted","assetVersionRef":"offline-candidate-not-admitted-v1",
        "assetVersionDigest":manifest["input"]["payloadDigest"],"contentDigest":manifest["input"]["sha256"],
        "mediaType":"image/png","byteSize":len(image),"width":704,"height":1280}
    inputs = dict(generation_request_ref="offline-candidate-not-a-generation-request", source_asset=compiler_source,
        backend_profile=profile,output_constraints=A14B_FINAL_OUTPUT)
    require(canonical(compile_exact_workflow(**inputs)) == canonical(candidate), "fixed compiler did not reproduce candidate")
    historic_profile = deepcopy(profile)
    historic_profile["parameters"]["positivePrompt"] = original["20"]["inputs"]["text"]
    require(canonical(compile_exact_workflow(**{**inputs,"backend_profile":historic_profile})) == canonical(original), "fixed compiler did not reproduce original")
    outputs = {"OFFLINE_BINDING_MAP.json":{"schemaVersion":"acs.sh09.offline-binding-report.v1",
        "originalEvidenceAvailability":"RESOLVED","archives":manifest["archives"],"originalGraphFileSha256":sha256(original_raw).hexdigest(),
        "originalGraphDigest":digest(original),"candidateGraphDigest":digest(candidate),"changedPointers":["/20/inputs/text"],
        "fullCompilerComparison":"PASS_ORIGINAL_AND_CANDIDATE","modelSourceMapping":manifest["models"],
        "weightsLocallyVerified":False,"profileDigest":digest(profile),"encodingDigest":digest(profile["parameters"]["postprocess"]),
        "readiness":exact_readiness(profile),"ownerAcceptance":"PENDING","sourceInputsAreNotAdmittedAssets":True},
        "SOURCE_TO_CONTRACT_DIGEST_MAP.json":mapping,
        "OFFLINE_BINDING_CANDIDATE/BACKEND_PROFILE.json":profile,
        "OFFLINE_BINDING_CANDIDATE/DRAFT_WORKFLOW.json":candidate,
        "OFFLINE_BINDING_CANDIDATE/PROMPT_PROPOSAL.json":proposal,
        "OFFLINE_BINDING_CANDIDATE/COMPLETE_ENCODING_PROFILE.json":profile["parameters"]["postprocess"],
        "MISSING_LIVE_FACTS.json":{"liveCurrentness":"NOT_CHECKED","cameraPromptAcceptance":"PENDING",
            "exactBindingOwnerAcceptance":"PENDING","activeRuntimeProcess":"NOT_OBSERVED","weightBytes":"NOT_READ",
            "credentialBinding":"NOT_OBSERVED","cost":"UNKNOWN","device":"UNKNOWN","budgetApproval":"NOT_GRANTED",
            "executionConfiguration":"NOT_DEPLOYED","grant":"NOT_ISSUED","systemRuntimeBound":False,
            "promptSubmissionAuthorized":False,"spike0Executed":False,"readiness":"BLOCKED"}}
    return outputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("task-package","task-sha256","recovered-package","recovered-sha256","ffmpeg-sha256","ffprobe-sha256","output"):
        parser.add_argument("--"+name,required=True)
    args=parser.parse_args()
    output=Path(args.output).resolve()
    repository=Path(__file__).resolve().parents[1]
    require(not output.is_relative_to(repository) and not output.exists(), "output must be new and outside repository")
    result=build(Path(args.task_package).read_bytes(),args.task_sha256,Path(args.recovered_package).read_bytes(),args.recovered_sha256,
        {"ffmpegSha256":args.ffmpeg_sha256,"ffprobeSha256":args.ffprobe_sha256})
    output.mkdir(parents=True,exist_ok=False)
    for name,value in result.items():
        path=output/name; path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("x",encoding="utf-8",newline="\n") as stream:
            stream.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"result":"EXACT_OFFLINE_CANDIDATE_BUILT_NOT_APPROVED","output":str(output),"files":len(result)},sort_keys=True))


if __name__=="__main__":
    main()
