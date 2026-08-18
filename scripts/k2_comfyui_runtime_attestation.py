#!/usr/bin/env python3
"""Emit a secret-free ComfyUI/Wan2.2 runtime attestation.

Run this on the GPU host.  It verifies the three configured model files by content,
probes the live ComfyUI node/device contract, and writes only safe technical facts.
The resulting record is not a rights, provider-policy, budget or publication grant.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.v4_platform import (
    ComfyUIWan22Config,
    MediaJobError,
    build_comfyui_runtime_attestation,
)


def _value(
    parser: argparse.ArgumentParser,
    supplied: str | None,
    environment_name: str,
) -> str:
    value = supplied or os.environ.get(environment_name, "")
    if not value.strip():
        parser.error(
            f"--{environment_name.lower().replace('_', '-')} or "
            f"{environment_name} is required"
        )
    return value.strip()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify one ComfyUI/Wan2.2 compute runtime without granting production "
            "authority or exposing credentials."
        )
    )
    parser.add_argument("--base-url")
    parser.add_argument("--provider-id")
    parser.add_argument("--model-id")
    parser.add_argument("--region")
    parser.add_argument("--endpoint-class")
    parser.add_argument("--unet-name")
    parser.add_argument("--unet-sha256")
    parser.add_argument("--clip-name")
    parser.add_argument("--clip-sha256")
    parser.add_argument("--vae-name")
    parser.add_argument("--vae-sha256")
    parser.add_argument("--attestation-ref")
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    for attribute, environment_name in (
        ("base_url", "COMFYUI_BASE_URL"),
        ("provider_id", "COMFYUI_PROVIDER_ID"),
        ("model_id", "COMFYUI_MODEL_ID"),
        ("region", "COMFYUI_REGION"),
        ("endpoint_class", "COMFYUI_ENDPOINT_CLASS"),
        ("unet_name", "COMFYUI_UNET_NAME"),
        ("unet_sha256", "COMFYUI_UNET_SHA256"),
        ("clip_name", "COMFYUI_CLIP_NAME"),
        ("clip_sha256", "COMFYUI_CLIP_SHA256"),
        ("vae_name", "COMFYUI_VAE_NAME"),
        ("vae_sha256", "COMFYUI_VAE_SHA256"),
        ("attestation_ref", "COMFYUI_RUNTIME_ATTESTATION_REF"),
    ):
        setattr(args, attribute, _value(parser, getattr(args, attribute), environment_name))
    return args


def main() -> int:
    args = _arguments()
    try:
        config = ComfyUIWan22Config(
            base_url=args.base_url,
            provider_id=args.provider_id,
            model_id=args.model_id,
            region=args.region,
            endpoint_class=args.endpoint_class,
            unet_name=args.unet_name,
            unet_sha256=args.unet_sha256,
            clip_name=args.clip_name,
            clip_sha256=args.clip_sha256,
            vae_name=args.vae_name,
            vae_sha256=args.vae_sha256,
            runtime_attestation_ref=args.attestation_ref,
            runtime_attestation_digest="0" * 64,
            cost_currency="USD",
            cost_minor_per_attempt=0,
            bearer_token=os.environ.get("COMFYUI_BEARER_TOKEN") or None,
        )
        attestation = build_comfyui_runtime_attestation(
            config,
            args.model_root,
            observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
    except MediaJobError as exc:
        print(f"runtime attestation failed: {exc}", file=sys.stderr)
        return 2
    serialized = json.dumps(
        attestation, ensure_ascii=False, sort_keys=True, indent=2
    ) + "\n"
    if args.output:
        destination = Path(args.output).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(destination)
    else:
        sys.stdout.write(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
