"""Fail-closed ComfyUI/Wan2.2 video adapter for the existing V4 media job.

The adapter owns provider transport and workflow details.  It receives a V5-issued
live generation request carrying opaque policy/rights references, and returns only a
candidate plus safe execution evidence to ``MediaJobCoordinator``.  It never creates
an AssetVersion, approval or publication fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import socket
import time
from typing import Any, Callable, Mapping
from urllib import error, parse, request as urllib_request

from .media_jobs import (
    MediaAdapterResult,
    MediaAdapterUnavailableError,
    MediaJobError,
)


COMFYUI_ADAPTER_ID = "v4.comfyui-wan22-ti2v.v1"
COMFYUI_CAPABILITY = "comfyui-wan22-ti2v-v1"
COMFYUI_RUNTIME_ATTESTATION_SCHEMA = "v4.comfyui-runtime-attestation.v1"
REQUIRED_NODES = (
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "ModelSamplingSD3",
    "CLIPTextEncode",
    "Wan22ImageToVideoLatent",
    "KSampler",
    "VAEDecode",
    "CreateVideo",
    "SaveVideo",
)


class ComfyUIConfigurationError(MediaAdapterUnavailableError):
    code = "worker_unavailable"


class ComfyUIProviderUnavailableError(MediaAdapterUnavailableError):
    code = "provider_unavailable"


class ComfyUIProviderTimeoutError(MediaAdapterUnavailableError):
    code = "provider_timeout"


class ComfyUIProviderResponseError(MediaJobError):
    code = "provider_invalid_response"


class ComfyUIProviderExecutionError(MediaJobError):
    code = "provider_execution_failed"


class _NoRedirectHandler(urllib_request.HTTPRedirectHandler):
    """Keep worker credentials on the one authority-approved endpoint origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def _sha256(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ComfyUIConfigurationError(f"{field} is invalid")
    return value


def _text(value: str, field: str, *, maximum: int = 500) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise ComfyUIConfigurationError(f"{field} is invalid")
    return value


def _canonical_digest(value: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _normalized_base_url(value: str) -> str:
    parsed = parse.urlsplit(value)
    host = (parsed.hostname or "").lower()
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (parsed.scheme == "http" and not loopback)
    ):
        raise ComfyUIConfigurationError("ComfyUI endpoint is not an approved URL class")
    return value.rstrip("/")


@dataclass(frozen=True, slots=True)
class ComfyUIWan22Config:
    base_url: str
    provider_id: str
    model_id: str
    region: str
    endpoint_class: str
    unet_name: str
    unet_sha256: str
    clip_name: str
    clip_sha256: str
    vae_name: str
    vae_sha256: str
    runtime_attestation_ref: str
    runtime_attestation_digest: str
    cost_currency: str
    cost_minor_per_attempt: int
    request_timeout_seconds: float = 30.0
    execution_timeout_seconds: float = 1800.0
    poll_interval_seconds: float = 1.0
    max_download_bytes: int = 2_000_000_000
    bearer_token: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _normalized_base_url(self.base_url))
        for field in (
            "provider_id", "model_id", "region", "endpoint_class", "unet_name",
            "clip_name", "vae_name", "runtime_attestation_ref",
        ):
            _text(getattr(self, field), field, maximum=300)
        for field in (
            "unet_sha256", "clip_sha256", "vae_sha256",
            "runtime_attestation_digest",
        ):
            _sha256(getattr(self, field), field)
        for field in ("unet_name", "clip_name", "vae_name"):
            model_name = PurePosixPath(getattr(self, field))
            if model_name.is_absolute() or ".." in model_name.parts:
                raise ComfyUIConfigurationError(f"{field} is not a safe model name")
        if (
            self.cost_currency != self.cost_currency.upper()
            or len(self.cost_currency) != 3
            or not self.cost_currency.isalpha()
            or isinstance(self.cost_minor_per_attempt, bool)
            or not isinstance(self.cost_minor_per_attempt, int)
            or self.cost_minor_per_attempt < 0
            or self.request_timeout_seconds <= 0
            or self.execution_timeout_seconds <= 0
            or self.poll_interval_seconds <= 0
            or self.max_download_bytes < 1
            or (self.bearer_token is not None and not self.bearer_token.strip())
        ):
            raise ComfyUIConfigurationError("ComfyUI execution configuration is invalid")


class ComfyUIHttpClient:
    """Bounded HTTP transport; raw endpoints and credentials never enter errors."""

    def __init__(self, config: ComfyUIWan22Config) -> None:
        self.config = config
        self._opener = urllib_request.build_opener(_NoRedirectHandler())

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "ACS-V4/1"}
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.config.bearer_token is not None:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"
        return headers

    def _open(self, provider_request: urllib_request.Request, timeout: float):
        try:
            return self._opener.open(provider_request, timeout=timeout)
        except (TimeoutError, socket.timeout) as exc:
            raise ComfyUIProviderTimeoutError("ComfyUI request timed out") from exc
        except error.HTTPError as exc:
            if exc.code in {408, 504}:
                raise ComfyUIProviderTimeoutError("ComfyUI request timed out") from exc
            raise ComfyUIProviderUnavailableError(
                "ComfyUI request failed"
            ) from exc
        except error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ComfyUIProviderTimeoutError("ComfyUI request timed out") from exc
            raise ComfyUIProviderUnavailableError("ComfyUI is unavailable") from exc

    def json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        maximum_bytes: int = 8_000_000,
    ) -> Mapping[str, Any]:
        body = None
        if payload is not None:
            body = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        provider_request = urllib_request.Request(
            f"{self.config.base_url}{path}",
            data=body,
            method=method,
            headers=self._headers(json_body=payload is not None),
        )
        with self._open(provider_request, self.config.request_timeout_seconds) as response:
            raw = response.read(maximum_bytes + 1)
        if len(raw) > maximum_bytes:
            raise ComfyUIProviderResponseError("ComfyUI JSON response exceeded limit")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComfyUIProviderResponseError("ComfyUI returned invalid JSON") from exc
        if not isinstance(value, Mapping):
            raise ComfyUIProviderResponseError("ComfyUI JSON response is not an object")
        return value

    def download(self, file_info: Mapping[str, str], destination: Path) -> None:
        query = parse.urlencode(
            {
                "filename": file_info["filename"],
                "subfolder": file_info["subfolder"],
                "type": file_info["type"],
            }
        )
        provider_request = urllib_request.Request(
            f"{self.config.base_url}/view?{query}",
            method="GET",
            headers=self._headers(),
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            with self._open(
                provider_request, self.config.request_timeout_seconds
            ) as response, destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.config.max_download_bytes:
                        raise ComfyUIProviderResponseError(
                            "ComfyUI artifact exceeded limit"
                        )
                    output.write(chunk)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        if total == 0:
            destination.unlink(missing_ok=True)
            raise ComfyUIProviderResponseError("ComfyUI artifact was empty")


def _node_options(
    object_info: Mapping[str, Any], node: str, field: str
) -> tuple[str, ...]:
    try:
        definition = object_info[node]["input"]["required"][field]
    except (KeyError, TypeError, IndexError):
        return ()
    if not isinstance(definition, list) or not definition:
        return ()
    direct = definition[0]
    if isinstance(direct, list) and all(isinstance(item, str) for item in direct):
        return tuple(direct)
    if (
        direct == "COMBO"
        and len(definition) > 1
        and isinstance(definition[1], Mapping)
        and isinstance(definition[1].get("options"), list)
        and all(isinstance(item, str) for item in definition[1]["options"])
    ):
        return tuple(definition[1]["options"])
    return ()


def _node_fields(
    object_info: Mapping[str, Any], node: str, section: str
) -> set[str]:
    try:
        raw = object_info[node]["input"][section]
    except (KeyError, TypeError):
        return set()
    return set(raw) if isinstance(raw, Mapping) else set()


def _safe_output_file(value: Mapping[str, Any]) -> dict[str, str] | None:
    filename = value.get("filename")
    subfolder = value.get("subfolder", "")
    output_type = value.get("type")
    if (
        not isinstance(filename, str)
        or not filename.lower().endswith(".mp4")
        or PurePosixPath(filename).name != filename
        or not isinstance(subfolder, str)
        or PurePosixPath(subfolder).is_absolute()
        or ".." in PurePosixPath(subfolder).parts
        or output_type != "output"
    ):
        return None
    return {"filename": filename, "subfolder": subfolder, "type": output_type}


def _find_video_output(value: Any) -> dict[str, str] | None:
    if isinstance(value, Mapping):
        candidate = _safe_output_file(value)
        if candidate is not None:
            return candidate
        for nested in value.values():
            found = _find_video_output(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_video_output(nested)
            if found is not None:
                return found
    return None


class ComfyUIWan22VideoAdapter:
    adapter_identity = COMFYUI_ADAPTER_ID
    provenance = "LIVE_PROVIDER"

    def __init__(
        self,
        config: ComfyUIWan22Config,
        *,
        client: ComfyUIHttpClient | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.client = client or ComfyUIHttpClient(config)
        self._monotonic = monotonic
        self._sleep = sleep

    def probe_capability(self) -> dict[str, Any]:
        stats = self.client.json("GET", "/system_stats")
        object_info = self.client.json("GET", "/object_info")
        missing_nodes = [node for node in REQUIRED_NODES if node not in object_info]
        if missing_nodes:
            raise ComfyUIConfigurationError("ComfyUI required nodes are unavailable")
        required_fields = {
            "UNETLoader": {"unet_name", "weight_dtype"},
            "CLIPLoader": {"clip_name", "type"},
            "VAELoader": {"vae_name"},
            "ModelSamplingSD3": {"model", "shift"},
            "CLIPTextEncode": {"text", "clip"},
            "Wan22ImageToVideoLatent": {
                "vae", "width", "height", "length", "batch_size",
            },
            "KSampler": {
                "model", "seed", "steps", "cfg", "sampler_name",
                "scheduler", "positive", "negative", "latent_image", "denoise",
            },
            "VAEDecode": {"samples", "vae"},
            "CreateVideo": {"images", "fps"},
            "SaveVideo": {"video", "filename_prefix", "format", "codec"},
        }
        if any(
            not fields.issubset(_node_fields(object_info, node, "required"))
            for node, fields in required_fields.items()
        ):
            raise ComfyUIConfigurationError(
                "ComfyUI node contract is incompatible with the Wan2.2 workflow"
            )
        if (
            "device" not in _node_fields(object_info, "CLIPLoader", "optional")
            or "bit_depth" not in _node_fields(object_info, "CreateVideo", "optional")
            or "default" not in _node_options(
                object_info, "UNETLoader", "weight_dtype"
            )
            or "wan" not in _node_options(object_info, "CLIPLoader", "type")
            or "uni_pc" not in _node_options(
                object_info, "KSampler", "sampler_name"
            )
            or "simple" not in _node_options(
                object_info, "KSampler", "scheduler"
            )
            or "mp4" not in _node_options(object_info, "SaveVideo", "format")
            or "h264" not in _node_options(object_info, "SaveVideo", "codec")
        ):
            raise ComfyUIConfigurationError(
                "ComfyUI workflow options are incompatible with the approved profile"
            )
        if self.config.unet_name not in _node_options(
            object_info, "UNETLoader", "unet_name"
        ):
            raise ComfyUIConfigurationError("configured Wan2.2 UNET is not recognized")
        if self.config.clip_name not in _node_options(
            object_info, "CLIPLoader", "clip_name"
        ):
            raise ComfyUIConfigurationError("configured text encoder is not recognized")
        if self.config.vae_name not in _node_options(
            object_info, "VAELoader", "vae_name"
        ):
            raise ComfyUIConfigurationError("configured Wan2.2 VAE is not recognized")
        devices = stats.get("devices")
        if not isinstance(devices, list):
            raise ComfyUIProviderResponseError("ComfyUI device facts are unavailable")
        cuda_devices = [
            item for item in devices
            if isinstance(item, Mapping)
            and item.get("type") == "cuda"
            and isinstance(item.get("name"), str)
            and item["name"]
        ]
        if len(cuda_devices) != 1:
            raise ComfyUIConfigurationError("exactly one approved CUDA device is required")
        device = cuda_devices[0]
        system = stats.get("system")
        if not isinstance(system, Mapping):
            raise ComfyUIProviderResponseError("ComfyUI system facts are unavailable")
        facts = {
            "providerId": self.config.provider_id,
            "modelId": self.config.model_id,
            "region": self.config.region,
            "endpointClass": self.config.endpoint_class,
            "comfyuiVersion": str(system.get("comfyui_version", "")),
            "pythonVersion": str(system.get("python_version", "")),
            "pytorchVersion": str(system.get("pytorch_version", "")),
            "deviceName": device["name"],
            "deviceType": "cuda",
            "vramTotalBytes": int(device.get("vram_total", 0)),
            "requiredNodes": list(REQUIRED_NODES),
            "modelFiles": [
                {"role": "UNET", "name": self.config.unet_name, "sha256": self.config.unet_sha256},
                {"role": "TEXT_ENCODER", "name": self.config.clip_name, "sha256": self.config.clip_sha256},
                {"role": "VAE", "name": self.config.vae_name, "sha256": self.config.vae_sha256},
            ],
            "runtimeAttestationRef": self.config.runtime_attestation_ref,
            "runtimeAttestationDigest": self.config.runtime_attestation_digest,
            "objectInfoDigest": _canonical_digest(dict(object_info)),
        }
        if facts["vramTotalBytes"] <= 0:
            raise ComfyUIConfigurationError("CUDA VRAM facts are invalid")
        return facts

    def build_workflow(self, generation_request: Mapping[str, Any]) -> dict[str, Any]:
        parameters = generation_request["parameters"]
        prefix_digest = sha256(
            str(generation_request["generationRequestRef"]).encode("utf-8")
        ).hexdigest()[:24]
        return {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": self.config.unet_name, "weight_dtype": "default"},
            },
            "2": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": self.config.clip_name, "type": "wan", "device": "default"},
            },
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": self.config.vae_name}},
            "4": {
                "class_type": "ModelSamplingSD3",
                "inputs": {"model": ["1", 0], "shift": parameters["modelShift"]},
            },
            "5": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": parameters["prompt"], "clip": ["2", 0]},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": parameters["negativePrompt"], "clip": ["2", 0]},
            },
            "7": {
                "class_type": "Wan22ImageToVideoLatent",
                "inputs": {
                    "vae": ["3", 0],
                    "width": parameters["width"],
                    "height": parameters["height"],
                    "length": parameters["durationFrames"],
                    "batch_size": 1,
                },
            },
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["4", 0],
                    "seed": parameters["seed"],
                    "steps": parameters["steps"],
                    "cfg": parameters["cfg"],
                    "sampler_name": parameters["samplerName"],
                    "scheduler": parameters["scheduler"],
                    "positive": ["5", 0],
                    "negative": ["6", 0],
                    "latent_image": ["7", 0],
                    "denoise": 1.0,
                },
            },
            "9": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["8", 0], "vae": ["3", 0]},
            },
            "10": {
                "class_type": "CreateVideo",
                "inputs": {"images": ["9", 0], "fps": parameters["frameRate"], "bit_depth": 8},
            },
            "11": {
                "class_type": "SaveVideo",
                "inputs": {
                    "video": ["10", 0],
                    "filename_prefix": f"acs-k2/{prefix_digest}",
                    "format": "mp4",
                    "codec": "h264",
                },
            },
        }

    @staticmethod
    def _prompt_ref(payload: Mapping[str, Any]) -> str:
        value = payload.get("prompt_id")
        if not isinstance(value, str) or not value or len(value) > 200:
            raise ComfyUIProviderResponseError("ComfyUI prompt reference is invalid")
        return value

    def _wait_for_output(
        self,
        prompt_ref: str,
        started: float,
        timeout_seconds: float,
        expected_prefix: str,
    ) -> dict[str, str]:
        while True:
            if self._monotonic() - started > timeout_seconds:
                raise ComfyUIProviderTimeoutError("ComfyUI execution timed out")
            history = self.client.json(
                "GET", f"/history/{parse.quote(prompt_ref, safe='')}"
            )
            entry = history.get(prompt_ref)
            if entry is not None and not isinstance(entry, Mapping):
                raise ComfyUIProviderResponseError("ComfyUI history entry is invalid")
            if isinstance(entry, Mapping):
                outputs = entry.get("outputs")
                save_video = outputs.get("11") if isinstance(outputs, Mapping) else None
                output = _find_video_output(save_video)
                if (
                    output is not None
                    and output["subfolder"] == "acs-k2"
                    and output["filename"].startswith(f"{expected_prefix}_")
                ):
                    return output
                status = entry.get("status")
                if isinstance(status, Mapping) and status.get("completed") is True:
                    raise ComfyUIProviderExecutionError(
                        "ComfyUI completed without a usable video"
                    )
                if isinstance(status, Mapping):
                    messages = status.get("messages")
                    if isinstance(messages, list) and any(
                        isinstance(item, list)
                        and item
                        and item[0] in {"execution_error", "execution_interrupted"}
                        for item in messages
                    ):
                        raise ComfyUIProviderExecutionError("ComfyUI execution failed")
            self._sleep(self.config.poll_interval_seconds)

    def generate(
        self, generation_request: Mapping[str, Any], candidate_path: Path
    ) -> MediaAdapterResult:
        provider = generation_request.get("providerSelection")
        if (
            generation_request.get("requestedProvenance") != "LIVE_PROVIDER"
            or generation_request.get("adapterCapability") != COMFYUI_CAPABILITY
            or not isinstance(provider, Mapping)
            or any(
                provider.get(field) != getattr(self.config, config_field)
                for field, config_field in (
                    ("providerId", "provider_id"),
                    ("modelId", "model_id"),
                    ("region", "region"),
                    ("endpointClass", "endpoint_class"),
                )
            )
            or provider.get("costCurrency") != self.config.cost_currency
            or provider.get("runtimeAttestationRef")
            != self.config.runtime_attestation_ref
            or provider.get("runtimeAttestationDigest")
            != self.config.runtime_attestation_digest
            or self.config.cost_minor_per_attempt
            > provider.get("maxCostMinor", -1)
        ):
            raise ComfyUIConfigurationError(
                "live request does not match the configured provider capability"
            )
        runtime_facts = self.probe_capability()
        workflow = self.build_workflow(generation_request)
        output_prefix = workflow["11"]["inputs"]["filename_prefix"].split("/")[-1]
        started = self._monotonic()
        submitted = self.client.json(
            "POST",
            "/prompt",
            payload={
                "prompt": workflow,
                "client_id": f"acs-v4-{sha256(str(generation_request['generationRequestRef']).encode()).hexdigest()[:24]}",
            },
        )
        prompt_ref = self._prompt_ref(submitted)
        file_info = self._wait_for_output(
            prompt_ref,
            started,
            min(
                self.config.execution_timeout_seconds,
                float(provider["timeoutSeconds"]),
            ),
            output_prefix,
        )
        self.client.download(file_info, candidate_path)
        latency_ms = max(0, round((self._monotonic() - started) * 1000))
        execution = {
            "providerId": self.config.provider_id,
            "modelId": self.config.model_id,
            "region": self.config.region,
            "endpointClass": self.config.endpoint_class,
            "providerRequestRef": prompt_ref,
            "latencyMs": latency_ms,
            "costCurrency": self.config.cost_currency,
            "costMinor": self.config.cost_minor_per_attempt,
            "seed": generation_request["parameters"]["seed"],
            "executionDevice": runtime_facts["deviceName"],
            "gpuUsed": True,
            "runtimeFacts": runtime_facts,
            "runtimeFactsDigest": _canonical_digest(runtime_facts),
        }
        return MediaAdapterResult(candidate_path, execution)


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_comfyui_runtime_attestation(
    config: ComfyUIWan22Config,
    model_root: Path | str,
    *,
    observed_at: str,
    client: ComfyUIHttpClient | None = None,
) -> dict[str, Any]:
    """Create a safe runtime snapshot with locally verified model digests.

    This is technical evidence only.  It does not grant provider, rights, budget,
    credential or publication authority.  Run it on the compute host so the three
    configured digests are calculated from the files that ComfyUI actually loads.
    """

    try:
        timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ComfyUIConfigurationError("observed_at is invalid") from exc
    if timestamp.tzinfo is None:
        raise ComfyUIConfigurationError("observed_at must include a timezone")
    root = Path(model_root).resolve()
    if not root.is_dir():
        raise ComfyUIConfigurationError("ComfyUI model root is unavailable")
    files = (
        ("UNET", "diffusion_models", config.unet_name, config.unet_sha256),
        ("TEXT_ENCODER", "text_encoders", config.clip_name, config.clip_sha256),
        ("VAE", "vae", config.vae_name, config.vae_sha256),
    )
    verified_files: list[dict[str, str]] = []
    for role, directory, name, expected_digest in files:
        path = (root / directory / Path(*PurePosixPath(name).parts)).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ComfyUIConfigurationError(
                "configured model path escapes the model root"
            ) from exc
        try:
            observed_digest = _file_sha256(path) if path.is_file() else None
        except OSError as exc:
            raise ComfyUIConfigurationError(
                f"configured {role} file could not be verified"
            ) from exc
        if observed_digest != expected_digest:
            raise ComfyUIConfigurationError(
                f"configured {role} file digest does not match"
            )
        verified_files.append(
            {"role": role, "name": name, "sha256": expected_digest}
        )

    facts = ComfyUIWan22VideoAdapter(config, client=client).probe_capability()
    facts.pop("runtimeAttestationRef", None)
    facts.pop("runtimeAttestationDigest", None)
    facts["modelFiles"] = verified_files
    facts["modelDigestVerification"] = "LOCAL_FILE_SHA256_VERIFIED"
    facts_digest = _canonical_digest(facts)
    attestation: dict[str, Any] = {
        "schemaVersion": COMFYUI_RUNTIME_ATTESTATION_SCHEMA,
        "attestationRef": config.runtime_attestation_ref,
        "observedAt": observed_at,
        "factsDigest": facts_digest,
        "facts": facts,
        "authorityState": "TECHNICAL_EVIDENCE_ONLY",
        "publicationAllowed": False,
    }
    attestation["payloadDigest"] = _canonical_digest(attestation)
    return attestation


def create_comfyui_wan22_adapter_from_environment(
    environ: Mapping[str, str] | None = None,
) -> ComfyUIWan22VideoAdapter:
    """Build an operator-controlled adapter; never selected automatically by Core."""

    values = os.environ if environ is None else environ
    required = {
        "COMFYUI_BASE_URL": "base_url",
        "COMFYUI_PROVIDER_ID": "provider_id",
        "COMFYUI_MODEL_ID": "model_id",
        "COMFYUI_REGION": "region",
        "COMFYUI_ENDPOINT_CLASS": "endpoint_class",
        "COMFYUI_UNET_NAME": "unet_name",
        "COMFYUI_UNET_SHA256": "unet_sha256",
        "COMFYUI_CLIP_NAME": "clip_name",
        "COMFYUI_CLIP_SHA256": "clip_sha256",
        "COMFYUI_VAE_NAME": "vae_name",
        "COMFYUI_VAE_SHA256": "vae_sha256",
        "COMFYUI_RUNTIME_ATTESTATION_REF": "runtime_attestation_ref",
        "COMFYUI_RUNTIME_ATTESTATION_DIGEST": "runtime_attestation_digest",
        "COMFYUI_COST_CURRENCY": "cost_currency",
        "COMFYUI_COST_MINOR_PER_ATTEMPT": "cost_minor_per_attempt",
    }
    missing = [name for name in required if not str(values.get(name, "")).strip()]
    if missing:
        raise ComfyUIConfigurationError("ComfyUI worker configuration is incomplete")
    kwargs: dict[str, Any] = {
        target: str(values[source]).strip() for source, target in required.items()
    }
    try:
        kwargs["cost_minor_per_attempt"] = int(kwargs["cost_minor_per_attempt"])
    except ValueError as exc:
        raise ComfyUIConfigurationError("ComfyUI cost configuration is invalid") from exc
    token = str(values.get("COMFYUI_BEARER_TOKEN", "")).strip()
    kwargs["bearer_token"] = token or None
    return ComfyUIWan22VideoAdapter(ComfyUIWan22Config(**kwargs))
