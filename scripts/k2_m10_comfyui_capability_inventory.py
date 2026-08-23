#!/usr/bin/env python3
"""Create a secret-free, read-only M10 ComfyUI capability inventory.

Node-name discovery is evidence, not approval of a workflow.  This utility never
reports a live multi-reference capability as PASS; an accepted adapter contract and
an executed artifact are still required.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping


DISCOVERY_TOKENS = (
    "ipadapter",
    "instantid",
    "pulid",
    "faceid",
    "reference",
    "redux",
    "controlnet",
)


def _canonical_digest(value: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _fields(definition: Any, section: str) -> list[str]:
    if not isinstance(definition, Mapping):
        return []
    inputs = definition.get("input")
    raw = inputs.get(section) if isinstance(inputs, Mapping) else None
    return sorted(raw) if isinstance(raw, Mapping) else []


def analyze_inventory(
    object_info: Mapping[str, Any], system_stats: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(object_info, Mapping) or not object_info:
        raise ValueError("object_info must be a non-empty object")
    if not isinstance(system_stats, Mapping):
        raise ValueError("system_stats must be an object")
    candidates = []
    for node_name in sorted(object_info):
        if not isinstance(node_name, str):
            raise ValueError("object_info node names must be strings")
        definition = object_info[node_name]
        required = _fields(definition, "required")
        optional = _fields(definition, "optional")
        searchable = " ".join([node_name, *required, *optional]).lower()
        matched = sorted({token for token in DISCOVERY_TOKENS if token in searchable})
        image_fields = sorted(
            field
            for field in required + optional
            if "image" in field.lower() or "reference" in field.lower()
        )
        if matched or len(image_fields) >= 2:
            candidates.append(
                {
                    "node": node_name,
                    "matchedTokens": matched,
                    "requiredFields": required,
                    "optionalFields": optional,
                    "imageLikeFields": image_fields,
                }
            )
    devices = system_stats.get("devices")
    cuda_devices = [
        {
            "name": item.get("name"),
            "vramTotalBytes": item.get("vram_total"),
        }
        for item in devices
        if isinstance(devices, list)
        and isinstance(item, Mapping)
        and item.get("type") == "cuda"
    ] if isinstance(devices, list) else []
    wan = object_info.get("Wan22ImageToVideoLatent")
    wan_fields = set(_fields(wan, "required") + _fields(wan, "optional"))
    if len(cuda_devices) != 1:
        state = "BLOCKED_RUNTIME_NOT_EXACTLY_ONE_CUDA"
    elif "LoadImage" not in object_info:
        state = "BLOCKED_LOAD_IMAGE_NODE_MISSING"
    elif not candidates:
        state = "BLOCKED_MULTI_REFERENCE_NODES_NOT_DISCOVERED"
    else:
        state = "UNPROVEN_CANDIDATE_NODES_DISCOVERED"
    report = {
        "schemaVersion": "k2.m10-comfyui-capability-inventory.v1",
        "decisionState": state,
        "multiReferenceCapabilityPassed": False,
        "reason": (
            "Node inventory alone cannot approve an identity-conditioning workflow."
        ),
        "cudaDevices": cuda_devices,
        "loadImagePresent": "LoadImage" in object_info,
        "wanImageToVideoPresent": wan is not None,
        "wanStartImageInputPresent": "start_image" in wan_fields,
        "candidateNodes": candidates,
        "objectInfoDigest": _canonical_digest(dict(object_info)),
        "systemStatsDigest": _canonical_digest(dict(system_stats)),
        "publicationAllowed": False,
    }
    report["payloadDigest"] = _canonical_digest(report)
    return report


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path.name} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--object-info", required=True, type=Path)
    parser.add_argument("--system-stats", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = analyze_inventory(
        _load(args.object_info), _load(args.system_stats)
    )
    if args.output.exists():
        raise SystemExit("output already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        args.output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2, sort_keys=True)
        target.write("\n")
    print(f"K2_M10_CAPABILITY_INVENTORY={report['decisionState']}")
    print("MULTI_REFERENCE_CAPABILITY_PASSED=false")
    print(f"INVENTORY={args.output.resolve()}")
    print(f"INVENTORY_SHA256={sha256(args.output.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

