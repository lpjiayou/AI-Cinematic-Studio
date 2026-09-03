# M12 A100 Build-Host Reflight — 2026-09-03

Status: `CURRENT / FAIL-CLOSED / ARCHITECTURE_AND_INFRASTRUCTURE_HOLD`

Owner: `Project Lead / Infrastructure Owner / Architecture Owner / M12 Domain Owner`

Task: `ACS-M12-A100-REFLIGHT-FAILURE-CLOSEOUT-AND-BUILD-HOST-DECISION`

## 1. Conclusion

The expanded persistent disk passed the exact byte gate, but the complete build-host
reflight failed. The failure creates no M12-C3 or M12-C4 authority and does not amend
either Accepted ADR involved in the build-host conflict.

```text
M12_A100_BUILD_HOST_REFLIGHT=FAIL
M12_A100_BUILD_HOST_REFLIGHT_EVIDENCE_SHA256=93c1c96dc3d852581857d1f213d158f03063cc6da47379dc7a24774be8dea1ce
M12_G0_3_STATE=ARCHITECTURE_AND_INFRASTRUCTURE_HOLD
M12_C3_READY_TO_REQUEST_AUTHORIZATION=false
M12_C3_READY_TO_START=false
M12_C3_AUTHORIZED=false
M12_C4_AUTHORIZED=false
```

The primary blockers are host capabilities. The checkout state is derived from the
network failure; it is not a mismatched checkout:

```text
PRIMARY_BLOCKERS=OFFLINE_ISOLATION_CAPABILITY_UNAVAILABLE,APPROVED_DOWNLOAD_ORIGINS_UNREACHABLE
DERIVED_BLOCKER=CORE_PREFLIGHT_CHECKOUT_UNVERIFIED_DUE_TO_NETWORK
CORE_PREFLIGHT_CHECKOUT_MISMATCH=false
```

## 2. Disk and process evidence

The user-expanded persistent volume had `169,596,186,624` bytes available against the
required `107,374,182,400` bytes. No reclaim or further expansion was performed.

```text
DISK_PREFLIGHT=PASS
PERSISTENT_FREE_BYTES=169596186624
REQUIRED_FREE_BYTES=107374182400
SAFE_RECLAIM_DELETED_BYTES=0
PERSISTENT_VOLUME_EXPANSION_REQUIRED=false

PORT_8188_FINAL=CLOSED
COMFYUI_PROCESS_FINAL=0
FFMPEG_PROCESS_FINAL=0
M12_RUNTIME_PROCESS_FINAL=0
GPU_COMPUTE_PROCESS_FINAL=EMPTY
ACTIVE_GIT_PROCESS_FINAL=0
```

`CUDA_VISIBLE_DEVICES` remained empty. No model, wheel or engine archive was
downloaded; no runtime was installed; and no GPU, Provider, ComfyUI or prompt action
occurred.

## 3. Infrastructure failure facts

The requested `UNSHARE_NETNS` probe returned `Operation not permitted`, so this host
cannot prove the required offline boundary with the accepted mechanism. The approved
origin audit also failed closed: GitHub web/API/codeload, PyPI index and the PyTorch
download origin passed, while GitHub raw and the Hugging Face web/LFS origins failed
their required transport/TLS/HTTP checks. The `files.pythonhosted.org` probe did not
produce an accepted HTTP result under the strict probe rule.

```text
OFFLINE_ISOLATION_MODE=UNSHARE_NETNS
OFFLINE_ISOLATION_CAPABILITY=FAIL
APPROVED_NETWORK_ORIGINS_REACHABLE=false
NETWORK_REMEDIATION_APPLIED=NONE
```

The exact anonymous Core clone began but did not complete its transfer. It was stopped
without leaving a target path or active Git process. Therefore the only accurate
checkout projection is:

```text
CORE_PREFLIGHT_CHECKOUT_HEAD=UNVERIFIED
CORE_PREFLIGHT_CHECKOUT_TREE=UNVERIFIED
CORE_PREFLIGHT_WORKTREE_CLEAN=UNVERIFIED
CHECKOUT_ATTEMPT=INCOMPLETE_TRANSFER
CHECKOUT_PARTIAL_PATH_PRESENT=false
```

## 4. A100 shutdown

After the final zero-process checks, the authorized root control channel sent the
immediate host shutdown request. The code-server channel then entered its disconnected
reconnect state. No restart is authorized.

```text
A100_STOP_REQUEST=PASS
A100_CONTROL_CHANNEL_FINAL=DISCONNECTED
A100_FUTURE_START_AUTHORIZED=false
A100_GPU_EXECUTION_AUTHORIZED=false
```

## 5. Accepted architecture conflict

Two Accepted ADRs make incompatible current build-host demands for M12-C3:

- [`ADR-0015`](../../governance/ADR-0015-m12-isolated-audio-runtime-and-acyclic-voice-clone-lineage.md)
  requires dependency locks and hashed wheelhouses to be built on a persistent,
  Linux x86_64, **non-A100 CPU build host** and makes A100 a closed-input consumer.
- [`ADR-0019`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md)
  records `A100_CODE_SERVER_BUILD_HOST` as the future M12-C3/C4 target and allows a
  later authorization for A100 CPU-only build work.

```text
ARCHITECTURE_AUTHORITY_CONFLICT=true
ARCHITECTURE_CONFLICT=ADR-0015_NON_A100_CPU_BUILD_HOST_VS_ADR-0019_A100_CODE_SERVER_BUILD_HOST
```

This checkpoint reports the conflict only. It does not select a build-host topology,
rewrite either Decision, or create an Accepted successor ADR. The architecture-change
process must resolve the conflict before M12-C3 can be requested or started.

## 6. Hold boundary

```text
M12_RUNTIME_G0=NOT_COMPLETE
M12_G0_3_STATE=ARCHITECTURE_AND_INFRASTRUCTURE_HOLD
M12_C3_READY_TO_REQUEST_AUTHORIZATION=false
M12_C3_READY_TO_START=false
M12_C3_AUTHORIZED=false
M12_C4_AUTHORIZED=false
A100_FUTURE_START_AUTHORIZED=false

NEXT_TASK=ACS-M12-BUILD-HOST-ARCHITECTURE-CORRECTION
```

That next task may prepare and obtain approval for a successor ADR. This status record
does not grant that decision or implementation authority.
