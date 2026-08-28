#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
sha256sum -c K2-002-EP01-A100-SHUTDOWN-ARCHIVE-20260828.tar.zst.sha256
tar --zstd -xf K2-002-EP01-A100-SHUTDOWN-ARCHIVE-20260828.tar.zst
