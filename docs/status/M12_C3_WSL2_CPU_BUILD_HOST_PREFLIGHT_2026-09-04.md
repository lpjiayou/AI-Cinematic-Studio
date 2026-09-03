# M12-C3 WSL2 CPU Build-Host Preflight — 2026-09-04

Status: `HISTORICAL_TECHNICAL_EVIDENCE / NOT_CURRENT_EXECUTION_AUTHORITY`

Owner: `Project Lead / Architecture Owner / Infrastructure Owner / M12 Domain Owner`

Task: `ACS-M12-C3-DEDICATED-LINUX-CPU-VM-SPECIFICATION`

## 1. Result

This checkpoint preserves the completed WSL2 candidate assessment supplied by the
authorized owners. It records a failed candidate preflight, not an ADR failure, an
M12-C3 execution failure or a Runtime G0 failure.

```text
WSL2_CPU_BUILD_HOST_PREFLIGHT=FAIL
WSL2_CANDIDATE_DISPOSITION=REJECTED_FOR_CURRENT_M12_C3_WAVE
BLOCK_REASON=WSL2_NETWORK_REMEDIATION_FAILED
NETWORK_REMEDIATION_ATTEMPT_COUNT=1
NETWORK_REMEDIATION_ATTEMPTS_EXHAUSTED=true
M12_CPU_BUILD_HOST_PREFLIGHT_EVIDENCE_SHA256=801e4e8cd44e5cf7dd2072c411808f624e9b2be214c8fb4b4faa8884469dd7ed
```

The repository intentionally does not contain the host-local raw evidence. The
digest above is the durable, redacted binding to that evidence.

## 2. Proven host facts

The candidate proved its local platform, persistent filesystem, restart persistence
and hard-offline isolation capabilities:

```text
WSL_DISTRIBUTION=Ubuntu
WSL_VERSION=2
HOST_OS=Ubuntu_26_04_LTS
HOST_ARCH=x86_64
DATA_FSTYPE=ext4
DATA_ON_WINDOWS_MOUNT=false
PERSISTENT_FREE_BYTES=1024270778368
PERSISTENCE_PHASE_1=PASS
WSL_RESTART_PERSISTENCE=PASS
OFFLINE_ISOLATION_MODE=UNSHARE_NETNS
HARD_OFFLINE_ISOLATION=PASS
WSL2_TECHNICAL_CAPABILITY_PARTIALLY_PROVEN=true
```

These partial results remain useful evidence. They do not offset or waive the
supply-chain network stability failure.

## 3. Failed supply-chain network condition

The approved base origins were initially reachable after the one authorized network
remediation. After the required persistence restart, DNS failed. The remediation
budget was exhausted and the preflight stopped before checkout or tag verification.

```text
INITIAL_NETWORK_AFTER_REMEDIATION=PASS
NETWORK_AFTER_PERSISTENCE_RESTART=FAIL_DNS
APPROVED_BASE_ORIGINS_REACHABLE=false
WSL2_SUPPLY_CHAIN_NETWORK_STABILITY_PROVEN=false
CORE_CHECKOUT=NOT_STARTED
M13_TAG_VERIFIED=NOT_STARTED
```

No checkout mismatch exists because no checkout was started. No M13 tag mismatch
exists because tag verification was not started.

## 4. Candidate disposition

```text
WSL2_NOT_SELECTED_FOR_CURRENT_C3=true
WSL2_PERMANENTLY_PROHIBITED=false
M12_C3_HOST_SELECTED=NONE
```

WSL2 is rejected only for the current M12-C3 wave. A future authorization may assess
a new WSL2 candidate from a fresh preflight; this record neither approves nor
permanently bans that host type.

## 5. Closed execution boundary

```text
MODEL_DOWNLOAD_BYTES=0
WHEEL_DOWNLOAD_BYTES=0
ENGINE_ARCHIVE_DOWNLOAD_BYTES=0
RUNTIME_INSTALL_COUNT=0
GPU_OR_PROVIDER_CALLS=0
A100_START_COUNT=0
A100_START_AUTHORIZED=false
M12_C3_AUTHORIZED=false
M12_C4_AUTHORIZED=false
M12_RUNTIME_G0_AUTHORIZED=false
```

The checkpoint contains no Windows username, IP address, proxy endpoint, token,
cookie, `.wslconfig` content, absolute workstation path, raw host log or prior local
Core checkout content.

## 6. Authority guard

```text
DOCUMENT_CLASS=HISTORICAL_EVIDENCE
CURRENT_STATE_CLAIMS_ALLOWED=false
HISTORICAL_DOCUMENT_GRANTS_AUTHORITY=false
HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true
```

Current host selection, readiness and next-task state are projected only by the
current status documents and the specification accepted under this task.
