"""Server-configured exact job worker. No scanning, retry or provider fallback."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
from uuid import uuid4

from .backend_registry import (BackendRegistry, BackendUnavailableError,
    BackendValidationError, UnavailableBackendResolver, strict_load)
from .method_aware_execution import ContentAddressedSourceImages
from .media_jobs import MediaJobCoordinator, SqliteMediaJobAdapter


class WorkerTerminated(Exception):
    code = "WORKER_TERMINATED_NO_RETRY"


class UnavailableMethodAdapter:
    adapter_identity = "v4.method-aware-unavailable.v1"
    provenance = "UNAVAILABLE"

    def generate(self, request, candidate_path):
        raise BackendUnavailableError("method-aware backend is unavailable")


def create_method_aware_coordinator_from_environment(
    repository, artifact_root, *, environ=None, ref_factory=None, clock=None,
):
    """Bind the existing shared repository; this factory never opens a queue DB."""
    values = os.environ if environ is None else environ
    manifest_path = values.get("CREATOR_METHOD_AWARE_BACKEND_REGISTRY", "")
    adapter = UnavailableMethodAdapter()
    registry = UnavailableBackendResolver()
    source = None
    if manifest_path:
        registry = BackendRegistry.from_file(manifest_path,
            values.get("CREATOR_METHOD_AWARE_BACKEND_REGISTRY_SHA256", ""))
        binding = registry.resolve("MICRO_MOTION", "SINGLE_ANCHOR_I2V",
            ["ACTION_READY_ANCHOR"], {"mediaType": "video/mp4"})
        from .comfyui import (ComfyUIWan22Config, ComfyUIWan22ImageToVideoAdapter,
                             COMFYUI_IMAGE_TO_VIDEO_ADAPTER_ID)
        if binding["adapterIdentity"] != COMFYUI_IMAGE_TO_VIDEO_ADAPTER_ID:
            raise BackendUnavailableError("configured adapter has no production factory")
        profile = registry.profile(binding)
        models = {item["role"]: item for item in profile["modelFiles"]}
        credential = binding["credentialSourceRef"]
        if not credential.startswith("env:") or not values.get(credential[4:]):
            raise BackendValidationError("server credential source is unavailable")
        try:
            cost = values["METHOD_AWARE_COMFYUI_COST_MINOR_PER_ATTEMPT"]
            if not cost.isascii() or not cost.isdecimal():
                raise ValueError("cost")
            config = ComfyUIWan22Config(
                base_url=values["METHOD_AWARE_COMFYUI_BASE_URL"],
                provider_id=binding["providerId"], model_id=binding["modelId"],
                region=binding["region"], endpoint_class=binding["endpointClass"],
                unet_name=models["UNET"]["name"], unet_sha256=models["UNET"]["sha256"],
                clip_name=models["TEXT_ENCODER"]["name"], clip_sha256=models["TEXT_ENCODER"]["sha256"],
                vae_name=models["VAE"]["name"], vae_sha256=models["VAE"]["sha256"],
                runtime_attestation_ref=binding["runtimeAttestationRef"],
                runtime_attestation_digest=binding["runtimeAttestationDigest"],
                cost_currency=binding["costCurrency"], cost_minor_per_attempt=int(cost),
                bearer_token=values[credential[4:]],
            )
            source = ContentAddressedSourceImages(values["CREATOR_METHOD_AWARE_SOURCE_ROOT"])
            attestation = strict_load(Path(values["METHOD_AWARE_COMFYUI_RUNTIME_ATTESTATION"]).read_bytes())
            adapter = ComfyUIWan22ImageToVideoAdapter(config, source_images=source,
                input_root=values["METHOD_AWARE_COMFYUI_INPUT_ROOT"], backend_registry=registry,
                runtime_attestation=attestation, model_root=values["METHOD_AWARE_COMFYUI_MODEL_ROOT"])
        except (KeyError, OSError, ValueError) as exc:
            raise BackendValidationError("method-aware worker configuration is incomplete or invalid") from exc
    elif any(key.startswith(("CREATOR_METHOD_AWARE_", "METHOD_AWARE_COMFYUI_")) and value
             for key, value in values.items()):
        raise BackendValidationError("method-aware backend registry is missing")
    return MediaJobCoordinator(repository, adapter, artifact_root,
        backend_resolver=registry, source_images=source, max_attempts=1,
        ref_factory=ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}"),
        clock=clock or (lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")))


def main(argv=None, *, environ=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("run-one")
    for name in ("job-ref", "workspace-ref", "production-run-ref", "worker-ref",
                 "queue-db", "artifact-root", "backend-registry-manifest", "backend-registry-sha256"):
        one.add_argument("--" + name, required=True)
    one.add_argument("--max-attempts", type=int, choices=(1,), required=True)
    args = parser.parse_args(argv)
    values = dict(os.environ if environ is None else environ)
    values.update(CREATOR_METHOD_AWARE_BACKEND_REGISTRY=args.backend_registry_manifest,
                  CREATOR_METHOD_AWARE_BACKEND_REGISTRY_SHA256=args.backend_registry_sha256)
    old_handler = signal.getsignal(signal.SIGTERM)

    def terminate(signum, frame):
        raise WorkerTerminated("worker terminated; automatic retry is forbidden")

    signal.signal(signal.SIGTERM, terminate)
    try:
        if not Path(args.queue_db).is_file():
            raise BackendValidationError("existing shared queue is unavailable")
        repository = SqliteMediaJobAdapter(args.queue_db, initialize_if_missing=False)
        coordinator = create_method_aware_coordinator_from_environment(
            repository, args.artifact_root, environ=values)
        job = coordinator.run_one(args.workspace_ref, args.production_run_ref, args.job_ref, args.worker_ref)
        print(json.dumps({"jobRef": job["jobRef"], "state": job["state"],
                          "attemptCount": len(job["attempts"])}, sort_keys=True))
        return {"SUCCEEDED": 0, "FAILED": 1, "CANCELLED": 3}.get(job["state"], 2)
    except Exception as exc:
        # Never print credentials, endpoints, local paths or raw provider errors.
        print(json.dumps({"state": "REJECTED", "code": getattr(exc, "code", "WORKER_REJECTED")}))
        return 2
    finally:
        signal.signal(signal.SIGTERM, old_handler)


if __name__ == "__main__":
    raise SystemExit(main())
