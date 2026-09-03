# M12 A100 Build-Host Preflight — 2026-09-03

Status: `CURRENT / FAIL-CLOSED / ENVIRONMENT_HOLD`

Owner: `Project Lead / Repository Governance Owner / M12 Domain Owner`

Task: `ACS-RESUME-BRANCH-CONSOLIDATION-AND-M12-A100-PREFLIGHT`

## 1. Conclusion

The authorized single A100 host start completed a no-install, no-GPU build-host
preflight. The preflight did not pass, so it creates no M12-C3 or M12-C4 execution
authority.

```text
M12_A100_BUILD_HOST_PREFLIGHT=FAIL
M12_A100_BUILD_HOST_PREFLIGHT_EVIDENCE_SHA256=b9945e6a6618572e583a983799967ccd9e3a9b12a8e86fd9032a924fce22fb00
M12_G0_3_STATE=ENVIRONMENT_HOLD
M12_C3_READY_TO_REQUEST_AUTHORIZATION=false
M12_C3_READY_TO_START=false
M12_C3_AUTHORIZED=false
M12_C4_AUTHORIZED=false
```

The exact preflight blockers were:

```text
BUILD_HOST_PREFLIGHT_PRIMARY_BLOCKER=INSUFFICIENT_PERSISTENT_DISK
BUILD_HOST_PREFLIGHT_BLOCKERS=INSUFFICIENT_PERSISTENT_DISK,APPROVED_DOWNLOAD_ORIGIN_UNAVAILABLE,CORE_PREFLIGHT_CHECKOUT_MISMATCH
```

The persistent volume had `62,970,826,752` bytes available against the required
`107,374,182,400` bytes. The point-in-time TLS/HEAD allowlist audit could not validate
`github.com`, `huggingface.co` or `cdn-lfs.huggingface.co`, and the anonymous clean
Core clone did not complete; therefore no host-checkout SHA/tree claim was accepted.

## 2. Branch consolidation checkpoint

The manifest-bound branch cleanup completed before host preflight. Its input manifest
had SHA-256
`6700db2ea6a49a7126cb69014e1dbe251a82a9aea46ffe3f219659d232b739ac`,
contained 17 records, and passed its schema, count, evidence-coverage and disposition
checks. Four Core branches and only `main` in Frontend remain; no open pull request or
unresolved audited branch remained. Core main, Frontend main, the immutable M13 tag
and the Frontend Core behavior pin were unchanged. Temporary GitHub device
authentication was logged out and its CLI configuration removed.

```text
BRANCH_CONSOLIDATION=PASS
UNRESOLVED_BRANCHES=0
UNMERGED_UNIQUE_PATCH_BRANCHES_DELETED=0
UNARCHIVED_UNIQUE_EVIDENCE_DELETED=0
GH_AUTH_LOGOUT=PASS
```

## 3. Passing preflight facts

- The host architecture was `x86_64`; one `NVIDIA A100-PCIE-40GB` was inventoried
  read-only, with no GPU compute process.
- All five approved persistent roots were present, writable, non-symlink directories
  with ordinary-user writes disabled and no unregistered runtime contents.
- The persistence sentinel was synchronized and reopened with matching bytes, and
  prior-session persistent evidence was found.
- `UNSHARE_NETNS` passed as an available offline isolation mode.
- Existing Core worktrees, ComfyUI checkout and Python environment, system Python
  inventory, model-file inventory, GPU-process inventory and listening ports were
  unchanged.
- Port 8188 was closed; ComfyUI, FFmpeg and M12 runtime process counts were zero.

```text
PERSISTENT_ROOT_PRESENT=true
PERSISTENT_ROOT_WRITABLE=true
PERSISTENT_ROOT_NOT_SYMLINK=true
DISK_PREFLIGHT=FAIL
OFFLINE_ISOLATION_MODE=UNSHARE_NETNS
OFFLINE_ISOLATION_CAPABILITY=PASS
APPROVED_NETWORK_ORIGINS_REACHABLE=false
ENVIRONMENT_UNCHANGED=true

MODEL_DOWNLOAD_BYTES=0
WHEEL_DOWNLOAD_BYTES=0
ENGINE_ARCHIVE_DOWNLOAD_BYTES=0
RUNTIME_INSTALL_COUNT=0
GPU_OR_PROVIDER_CALLS=0
COMFYUI_START_COUNT=0
PROMPT_POST_COUNT=0
```

## 4. Frozen M12 facts

The current Core contracts still pin the Kokoro and CosyVoice3 engine commits and
model-bundle digests, preserve the implemented acyclic
SourceRecording–Consent–VoiceLock–VoiceProfile lineage, and keep the M9-to-M12 bridge
bounded and fail-closed. Python, PyTorch, Torchaudio and CUDA wheel variants remain
unfrozen; dependency locks are unfrozen and wheelhouses are not created. Exact license
evidence remains open and blocks commercial production. These are C3/Rights work, not
facts supplied by this failed host preflight.

## 5. Stop boundary and next task

The separate preimplementation blocker confirmed by the resumed authorization remains
the K2 public cutover. This checkpoint does not start that work.

```text
M12_RUNTIME_G0=NOT_COMPLETE
M12_C3_PREIMPLEMENTATION_BLOCKER=K2_METHOD_AWARE_PUBLIC_CUTOVER_PENDING
A100_FUTURE_START_AUTHORIZED=false
A100_GPU_EXECUTION_AUTHORIZED=false
PORT_8188_FINAL=CLOSED
GPU_COMPUTE_PROCESS_FINAL=EMPTY
SAFE_TO_SHUTDOWN_A100=YES

NEXT_TASK=ACS-K2-METHOD-AWARE-PUBLIC-CUTOVER-AND-LEGACY-G4-G5-WRITE-FREEZE
```

The evidence digest identifies the secret-free host-local evidence set. That evidence
is technical evidence only: it is not a model, wheelhouse, runtime manifest, Asset
Admission, canonical production fact or publication authority.
