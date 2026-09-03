# M12-C3 Dedicated Linux CPU Build-Host Specification

Status: `CURRENT_ARCHITECTURE_SPECIFICATION / NOT_A_PURCHASE_AUTHORIZATION`

Owner: `Project Lead / Architecture Owner / Infrastructure Owner / Repository Governance Owner / M12 Domain Owner`

Task: `ACS-M12-C3-DEDICATED-LINUX-CPU-VM-SPECIFICATION`

## 1. Authority and scope

This specification implements the physical host-selection boundary established by
[`ADR-0015`](../governance/ADR-0015-m12-isolated-audio-runtime-and-acyclic-voice-clone-lineage.md)
and
[`ADR-0020`](../governance/ADR-0020-m12-cpu-build-host-and-a100-offline-consumer.md).
It does not supersede or amend either Accepted ADR. It defines vendor-neutral minimum
requirements and the future preflight contract; it neither selects nor purchases a
provider, region, image or instance.

The repository taxonomy has no standalone primary class named
`ARCHITECTURE_SPECIFICATION`. Under the single-class governance rule this document is
registered as a current status projection, with its architecture-specification
characteristic recorded separately:

```text
REGISTRY_DOCUMENT_CLASS=CURRENT_STATUS
DOCUMENT_CHARACTERISTIC=ARCHITECTURE_SPECIFICATION
DOCUMENT_STATUS=CURRENT_ARCHITECTURE_SPECIFICATION
STATUS=CURRENT
CURRENT_STATE_CLAIMS_ALLOWED=true
NOT_A_PURCHASE_AUTHORIZATION=true
```

The host role is frozen as:

```text
HOST_CLASS=DEDICATED_LINUX_CPU_VM
PURPOSE=M12_C3_SUPPLY_CHAIN_CLOSURE_ONLY
GPU_REQUIRED=false
GPU_DEVICE_ALLOWED=false
A100_ALLOWED=false
```

The host must not perform C4 A100 installation, Runtime G0 GPU validation, production
API serving, ComfyUI, long-running model inference, live Audio generation, Asset
Admission or publication.

## 2. CPU, memory and persistent storage

The minimum architecture requirements are:

```text
HOST_ARCH=x86_64
HOST_OS_CLASS=SUPPORTED_LTS_LINUX
MIN_VCPU=8
MIN_MEMORY_BYTES=34359738368
PERSISTENT_BLOCK_STORAGE_REQUIRED=true
MIN_VOLUME_BYTES=268435456000
MIN_FREE_BYTES_BEFORE_C3=107374182400
ALLOWED_FILESYSTEMS=ext4,xfs
WINDOWS_MOUNT_ALLOWED=false
EPHEMERAL_ROOT_AS_AUTHORITY_ALLOWED=false
```

`MIN_VOLUME_BYTES` is the 250 GiB procurement target. ADR-0020's hard gate remains
at least 100 GiB of exactly measured free space before C3. The operating system,
logs, container layers and caches must not consume that gate. Models, wheelhouses,
manifests and evidence must reside on persistent block storage and remain after the
compute instance stops.

The following values are preferences, not additional hard gates:

```text
PREFERRED_VCPU=8
PREFERRED_MEMORY_GIB=32
PREFERRED_VOLUME_GIB=250
OPTIONAL_HIGH_HEADROOM_VOLUME_GIB=500
OPTIONAL_HIGH_HEADROOM_VOLUME_IS_REQUIRED=false
```

## 3. Host image and tool capability

```text
ROOT_OR_CONTROLLED_SUDO=true
GIT_AVAILABLE=true
CURL_AVAILABLE=true
OPENSSL_AVAILABLE=true
SHA256SUM_AVAILABLE=true
TAR_AVAILABLE=true
CONTAINER_ENGINE_AVAILABLE=true
PREFERRED_HOST_IMAGE=UBUNTU_24_04_LTS_X86_64
```

The selected provider image must pass the real preflight. This task does not freeze
Python, PyTorch, Torchaudio, CUDA wheel variants, a resolver or a lock format. The
host Python is not authority for either runtime; Kokoro and CosyVoice3 continue to
require separate reproducible environments.

## 4. Two mutually exclusive network stages

### 4.1 `FETCH_AND_HASH`

```text
FETCH_AND_HASH_NETWORK_BOUNDARY=APPROVED_EGRESS_ALLOWLIST
NETWORK_MODE=APPROVED_EGRESS_ALLOWLIST
OUTBOUND_TCP_443_ONLY=true
INBOUND_PUBLIC_SERVICE_ALLOWED=false
TLS_VERIFICATION_REQUIRED=true
```

The closed base-origin set is:

```text
github.com
api.github.com
raw.githubusercontent.com
codeload.github.com
pypi.org
files.pythonhosted.org
download.pytorch.org
huggingface.co
```

Hugging Face, LFS, Xet, CAS and redirect hosts are not pre-authorized as an open set.
Before C3 begins, an exact-revision metadata-only redirect audit must identify each
required redirect host and add it to a closed allowlist.

The following are forbidden:

```text
0.0.0.0/0_UNRESTRICTED_EGRESS
curl_-k
TLS_VERIFY_FALSE
UNAPPROVED_MIRROR
TRANSPARENT_THIRD_PARTY_PROXY
```

### 4.2 `OFFLINE_VERIFY`

```text
OFFLINE_VERIFY_BOUNDARY=HARD_OFFLINE
NETWORK_MODE=HARD_OFFLINE
```

The stage must prove at least one of:

```text
DOCKER_NETWORK_NONE
PODMAN_NETWORK_NONE
PLATFORM_EGRESS_DENY
```

`UNSHARE_NETNS` may be evaluated, but a dedicated VM should prefer container
`network=none` or a platform-level egress deny. `PIP_NO_INDEX`, `HF_HUB_OFFLINE` and
`TRANSFORMERS_OFFLINE` do not independently prove hard isolation.

`FETCH_AND_HASH` and `OFFLINE_VERIFY` must never be active concurrently.

## 5. Inbound and management boundary

```text
PUBLIC_APPLICATION_PORTS_ALLOWED=false
COMFYUI_PORT_8188_ALLOWED=false
PUBLIC_HTTP_SERVICE_ALLOWED=false
PUBLIC_CODE_SERVER_ALLOWED=false
PUBLIC_JUPYTER_ALLOWED=false
PUBLIC_INBOUND_SERVICES_ALLOWED=false
```

Exactly one of the following controlled management patterns must be selected and
evidenced during provider preflight:

```text
PROVIDER_SESSION_MANAGER
VPN_OR_PRIVATE_NETWORK
SOURCE_IP_RESTRICTED_SSH
```

The following patterns are prohibited:

```text
SSH_FROM_0_0_0_0_0
PASSWORD_ONLY_SSH
PUBLIC_JUPYTER
PUBLIC_CODE_SERVER
PUBLIC_COMFYUI
```

The repository must not record a public IP, login username, private key, token or
other credential.

## 6. Persistence and lifecycle

```text
STOP_COMPUTE_KEEP_PERSISTENT_DISK=true
RESTART_PERSISTENCE=true
SNAPSHOT_OR_SECOND_COPY=true
HOURLY_OR_SHORT_LIVED_BILLING_PREFERRED=true
STOP_START_PERSISTENCE_REQUIRED=true
```

The provider preflight must execute this cloud lifecycle sequence:

```text
write sentinel
→ sync
→ stop VM
→ start VM
→ verify sentinel SHA-256
```

An operating-system reboot does not substitute for provider-level stop/start. After
C3 completes, compute may stop, but the persistent disk, both bundles, wheelhouses,
dependency locks, SBOMs, license evidence and execution evidence must remain through
C4 and Runtime G0.

## 7. Closed artifacts and the second durable copy

The host must be able to produce two independent `M12ClosedRuntimeBundle.v1`
artifacts:

```text
KOKORO_FIXED_VOICE
COSYVOICE3_ZERO_SHOT
```

Their persistent root is:

```text
/data/k2-runtime-artifacts/m12/g0
```

A second durable copy outside the CPU Build Host is mandatory:

```text
SECOND_ARTIFACT_COPY_REQUIRED=true
```

Future candidates may evaluate:

```text
CONTROLLED_OBJECT_STORAGE
PROVIDER_PERSISTENT_SNAPSHOT
BYTE_PRESERVING_SECURE_COPY
PLATFORM_FILE_TRANSFER
```

ChatGPT attachments, Git repositories, temporary download links and unverified
shared directories cannot be model-bundle authority.

## 8. C3-to-C4 transfer precondition

```text
C3_TO_C4_TRANSFER_REQUIRED=BYTE_PRESERVING_DIGEST_VERIFIED_TRANSFER
C3_TO_C4_TRANSFER=BYTE_PRESERVING_DIGEST_VERIFIED_TRANSFER
```

The dedicated VM may pass its host preflight before a transfer mechanism is proven,
but until the mechanism passes the sentinel test:

```text
M12_C3_READY_TO_REQUEST_AUTHORIZATION=false
```

The future transfer preflight must use only a small random sentinel file:

```text
CPU_VM
→ selected transfer mechanism
→ A100 persistent volume
→ recompute SHA-256
→ byte identical
```

It must not transfer a model, wheel, source recording or credential.

## 9. Vendor comparison schema

The provider-selection task must compare candidates using every field below. This
specification contains no provider row, live price, inferred price or billing change.

```text
providerCandidate
region
hostImage
cpuArchitecture
vCpu
memoryGiB
persistentDiskGiB
filesystem
estimatedHourlyComputeCost
estimatedMonthlyDiskCost
allowlistedEgressSupported
platformEgressDenySupported
dockerOrPodmanSupported
stopStartPersistenceSupported
snapshotSupported
sessionManagerOrRestrictedSshSupported
objectStorageOrTransferSupported
a100TransferPathCandidate
dataResidency
billingAccountRequired
preflightState
rejectionReasons[]
```

Prices must come from current authoritative provider sources in the separately
authorized selection task; absence of verified price evidence is not permission to
guess.

## 10. Dedicated VM preflight contract

The selected physical candidate must prove:

```text
HOST_ARCH=x86_64
HOST_OS=LINUX
GPU_DEVICE_COUNT=0
PERSISTENT_FILESYSTEM=ext4_OR_xfs
PERSISTENT_FREE_BYTES>=107374182400
STOP_START_PERSISTENCE=PASS
APPROVED_ORIGIN_ALLOWLIST=PASS
HARD_OFFLINE_ISOLATION=PASS
CORE_CHECKOUT=PASS
CORE_CHECKOUT_HEAD=3eaaeabf79fdb85581a15069ff6fe5f330445416
CORE_CHECKOUT_TREE=088e485d1fedf3973a55545c86d194112a670024
M13_TAG_OBJECT=b2d086b622bdb5456f6af325e458aa3771e43e80
M13_TAG_TARGET=a455c8e76427d53d75bb7f15259b9875d9768914
SECRET_FREE_EVIDENCE=PASS
ENVIRONMENT_UNCHANGED=PASS
```

The commit and tree above bind this specification checkpoint. If remote `main`
advances before the physical preflight, the selection task must audit the intervening
commits and use that then-current, conflict-free `main`; it must not permanently pin
the older checkout.

## 11. Current hold and non-authorizations

```text
M12_C3_HOST_SELECTED=NONE
M12_G0_3_STATE=DEDICATED_CPU_VM_SELECTION_HOLD
M12_C3_READY_TO_REQUEST_AUTHORIZATION=false
M12_C3_READY_TO_START=false
M12_C3_AUTHORIZED=false
M12_C4_AUTHORIZED=false
M12_RUNTIME_G0_AUTHORIZED=false
A100_START_AUTHORIZED=false
A100_FUTURE_START_AUTHORIZED=false
CLOUD_VM_PURCHASE_AUTHORIZED=false
CLOUD_ACCOUNT_MUTATION_AUTHORIZED=false
BILLING_CHANGE_AUTHORIZED=false
MODEL_DOWNLOAD_ALLOWED=false
WHEEL_DOWNLOAD_ALLOWED=false
ENGINE_ARCHIVE_DOWNLOAD_ALLOWED=false
RUNTIME_INSTALL_ALLOWED=false
```

The only next legal task is
`ACS-M12-C3-DEDICATED-LINUX-CPU-VM-PROVIDER-SELECTION-AND-PREFLIGHT`, and it requires
separate authorization. This specification does not authorize provider selection,
account changes, VM creation, preflight execution, C3, C4, A100 or Runtime G0.
