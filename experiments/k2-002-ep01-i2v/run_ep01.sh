#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
ASSET_PACKAGE="${ASSET_PACKAGE:-/data/coding/final-assets-v1.2.zip}"
MODEL_ROOT="${MODEL_ROOT:-/data/coding/apps/ComfyUI/models}"
COMFYUI_ROOT="${COMFYUI_ROOT:-/data/coding/apps/ComfyUI}"
COMFYUI_BASE_URL="${COMFYUI_BASE_URL:-http://127.0.0.1:8188}"
EVIDENCE_ROOT="${EVIDENCE_ROOT:-/data/k2-technical-evidence/k2-002-ep01-i2v-v1}"

usage() {
  printf '%s\n' \
    "Usage:" \
    "  run_ep01.sh preflight" \
    "  run_ep01.sh shot EP01_SH06" \
    "  run_ep01.sh batch" \
    "" \
    "Execution requires:" \
    "  export K2_EP01_I2V_ACK=TECHNICAL_EVIDENCE_ONLY"
}

require_execution_ack() {
  if [[ "${K2_EP01_I2V_ACK:-}" != "TECHNICAL_EVIDENCE_ONLY" ]]; then
    printf '%s\n' \
      "ERROR: set K2_EP01_I2V_ACK=TECHNICAL_EVIDENCE_ONLY before execution" >&2
    exit 2
  fi
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

mode="$1"
shift

case "$mode" in
  preflight)
    if [[ $# -ne 0 ]]; then
      usage >&2
      exit 2
    fi
    exec "$PYTHON_BIN" "$SCRIPT_DIR/ingest_ep01.py" \
      --validate-only \
      --asset-package "$ASSET_PACKAGE" \
      --model-root "$MODEL_ROOT"
    ;;
  shot)
    if [[ $# -ne 1 ]]; then
      usage >&2
      exit 2
    fi
    require_execution_ack
    exec "$PYTHON_BIN" "$SCRIPT_DIR/ingest_ep01.py" \
      --execute \
      --asset-package "$ASSET_PACKAGE" \
      --model-root "$MODEL_ROOT" \
      --comfyui-root "$COMFYUI_ROOT" \
      --base-url "$COMFYUI_BASE_URL" \
      --evidence-root "$EVIDENCE_ROOT" \
      --shot-id "$1"
    ;;
  batch)
    if [[ $# -ne 0 ]]; then
      usage >&2
      exit 2
    fi
    require_execution_ack
    exec "$PYTHON_BIN" "$SCRIPT_DIR/ingest_ep01.py" \
      --execute \
      --asset-package "$ASSET_PACKAGE" \
      --model-root "$MODEL_ROOT" \
      --comfyui-root "$COMFYUI_ROOT" \
      --base-url "$COMFYUI_BASE_URL" \
      --evidence-root "$EVIDENCE_ROOT" \
      --skip-existing
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
