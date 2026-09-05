# Creator Public HTTP/API v1

Status: `XR1 FROZEN / AUTH-W1 / ADR-0013 CONTROL PLANE / ADR-0019 METHOD-AWARE CUTOVER / STRICT JSON AND NUMERIC INTEGRITY / M4 RECOVERABLE FOUNDATION / M5 SCOPE-BOUND RECEIPTS`

This contract is the only browser-facing Core HTTP surface for the separate Commercial
Frontend. Existing `/creator/internal/*` endpoints remain compatibility-only and must
not be called by the Frontend Experience Adapter.

## Dependency direction

```text
Commercial Frontend → Frontend Experience Adapter → /creator/api/v1
→ Creator Application → V5 public boundaries
```

## Resource map

| Capability | Public resource | Accepted Core owner |
| --- | --- | --- |
| M1 | `/ai-director/candidates`, `/creative-plans/confirm` | AI Director Application + Series/Episode boundary |
| M2 | `/series`, `/episodes` | Series/Episode public boundary |
| M3 | `/script-workspaces`, `/script-versions/*`, `/script-versions/reviewed-import`, `/script-versions/reviewed-import/accept` | Script Studio Application/public boundary |
| M4 | `/projects`, `/project-contexts`, `/project-foundations`, `/canonical-registrations`, `/canonical-registrations/preflight` | Project Context, cross-M2/M4 Creator Application foundation orchestration and V5 canonical registration boundary |
| M5 | `/series-planning-workspaces`, `/series-plan-*` | Series Planning + Series Director boundaries |
| M6 | `/series-intelligence-workspaces`, `/series-intelligence/*` | accepted Series Intelligence public boundary |
| M7–M9 | `/episode-production-runs/{runRef}/shot-graph`, `/execution-method-plan` | current M7 validation plus source-bound M8 action beats and server-derived M9 three-axis requirements |
| M10 | `/episode-production-runs/{runRef}/method-aware-input-plan`, `/dynamic-media-preflight`, `/real-media-revision`, `/real-image-candidates`, `/semantic-visual-qc`, `/media-selection`, `/real-image-admission`, `/real-image-successor-admission`, `/real-image-selection`, `/state-projection`, `/production-readiness` | current-plan input resolution over the one canonical AssetVersion stream, plus the existing typed media control plane |
| M11 | `/episode-production-runs/{runRef}/method-aware-video-route`, `/real-video-revision`, `/real-video-candidates`, `/semantic-visual-qc`, `/media-selection`, `/real-video-admission`, `/state-projection`, `/provider-experiments` | closed method routing; only Micro Motion can reserve the existing single-anchor queue, while Contact and Gait fail closed |
| M12 | `/episode-production-runs/{runRef}/explicit-audio-requirement-route`, `/production-readiness` | explicit M9 AudioRequirement routing; Runtime G0 remains incomplete |
| M13–M14 | `/episode-production-runs/{runRef}/render-candidates`, `/preview`, `/finalize` | bounded V5 RenderCandidate/delivery services over the accepted M13 base backend and V4/V3 execution boundaries |
| M15 | `/episode-production-runs/{runRef}/delivery`, preview/export content | bounded K2 V5 delivery authority |
| M16–M19 | `/capabilities` status only | not open at the current gate |

## Envelopes and transport

- Success: `{ "ok": true, ... }`.
- Failure: `{ "ok": false, "error": { "code": string, "message": string } }`.
- Commands require `Content-Type: application/json`.
- Request bodies are limited to 512000 bytes.
- Responses use UTF-8 JSON and `Cache-Control: no-store`.
- Request JSON uses the standard grammar only: `NaN`, `Infinity`, `-Infinity`,
  comments and trailing commas are invalid. Maximum nesting depth is 64 and each
  number token is limited to 128 characters.
- Integer command fields accept JSON integers only. Booleans, floats (including
  integral-valued floats), numeric strings and null are invalid and are never
  rounded or truncated.
- Public numeric fields must be finite. Every JSON response is serialized with
  `allow_nan=False`; a serialization violation returns a complete
  `500 / application_error` envelope before response headers are sent.
- Core references and version references returned by successful commands are opaque.
- Provider diagnostics, credentials, repository types and raw exceptions are forbidden.

## Recoverable Project foundation command

`POST /creator/api/v1/project-foundations` is the only recoverable composition
command for creating a Project foundation. Its closed
`creator.project-foundation-command.v1` body contains exactly `schemaVersion`,
`idempotencyKey`, `contentProfileRef`, `series`, `project` and `episode`.
Authentication supplies `workspaceRef`; clients cannot submit workspace or result
scope, refs, state, timestamps, digests, authority, approval, Provider, execution or
publication fields. Nested objects are closed, and all count/number fields follow the
strict integer rules above.

A `series` Project requires a Series. Standalone and brand-film Projects may omit a
Series, and Core never creates a hidden Series. An Episode requires the new Series
and an existing confirmed creative plan in the authenticated workspace; the command
does not confirm a plan or create a Script. Series and Project use the same trusted
content profile.

Before domain mutation, Core normalizes the command, computes canonical standard
JSON over `schemaVersion`, `contentProfileRef`, `series`, `project` and `episode`, and
persists a `PENDING` intent scoped by authenticated workspace plus idempotency key.
Workspace, key, refs, timestamps, retry metadata, headers and credentials are not
part of the request digest. Phase B revalidates that intent and creates the optional
Series, Project, relationship and optional Episode through their existing domain
services in one Lifecycle transaction. The final
`creator.project-foundation-result.v1` receipt and `COMPLETED` transition commit in
that same transaction; failure rolls back every domain write while retaining only
the Phase A intent for exact recovery.

The first successful command returns `201`. A matching `PENDING` recovery or exact
`COMPLETED` replay returns `200` with the original refs; the envelope reports
`recoveredFromPending` and `idempotentReplay`. Reusing a workspace/key with a changed
canonical request returns `409 / project_foundation_idempotency_conflict`. Temporary
store or Lifecycle unavailability returns `503 / project_foundation_unavailable`.
`GET /creator/api/v1/project-foundations/{foundationRef}` returns the exact validated
receipt only inside the authenticated workspace; unknown and foreign refs return
`404 / project_foundation_not_found` without disclosure.

The durable intent/receipt is application recovery metadata, not a canonical fact,
approval, Series/Project/Episode authority or publication authority. Those objects
remain owned by the existing V5 repositories. The legacy `/series`, `/projects` and
`/episodes` resources remain compatible and unchanged, but their multi-request
combination is not atomic or recoverable. Frontend cutover to the new command is a
separate task.

## Candidate and confirmation semantics

Generation routes return candidates. A candidate becomes a Core fact only through its
specific confirmation route. The Experience Adapter must preserve
`confirmationRequired` and must never infer confirmation from a successful generation
response. The M1 candidate response also carries the Core-issued opaque
`sourcePlanRef` and `sourcePlanVersion`; browser code must return those exact values on
confirmation and must not mint or infer a source-plan reference.

For M5, `POST /creator/api/v1/series-plan-candidates` requires an associated Series.
A standalone Project without a Series returns `409 / series_scope_required` before
any Provider call, receipt write or Series Plan write. A successful response includes
the server-owned opaque `candidateRef`, `candidateDigest`, `sourceContextDigest`,
`candidateReceiptSchemaVersion=creator.series-plan-candidate-receipt.v1` and
`candidateReceiptReplay` alongside the unchanged
`creator.series-plan.candidate.v1` candidate.

`POST /creator/api/v1/series-plans/confirm-candidate` accepts exactly `projectRef`, `seriesRef`,
`humanConfirmed` and `candidate`, plus an optional `candidateRef`. Authentication
supplies `workspaceRef`; clients cannot submit receipt scope, version, digest,
timestamp, raw receipt JSON or Provider facts. With `candidateRef`, Core performs an
exact authenticated-workspace lookup. Without it, compatibility is limited to one
exact durable receipt matching workspace, Project, Series, current trusted source
context and candidate digest. Cross-scope, stale, changed, unknown and unissued
candidates fail closed. Only the canonical candidate reloaded from the server receipt
reaches the existing V5 Series Planning confirmation boundary. The receipt is
application provenance, not a confirmed plan, approval, canonical fact or publication
authority; raw `creativeInput` is represented only by its SHA-256 digest.

## ADR-0019 method-aware production planning

The four closed resources are:

```text
execution-method-plan
method-aware-input-plan
method-aware-video-route
explicit-audio-requirement-route
```

Authentication supplies `workspaceRef`, and the resource path supplies
`productionRunRef`. All commands also carry `projectRef`, `seriesRef`, `episodeRef`
and `idempotencyKey`. The first command accepts the latest current
`consistencyValidationVersionRef` and a complete source-bound M8 Shot/ActionBeat
plan. An `executionClass` is valid only inside that original, source-span-validated
ActionExecutionBeat fact; it is never accepted as a top-level or downstream
override. Core maps every class to its one closed `executionMethod` and derives the
Visual, Audio and Postprocess requirements.

`method-aware-input-plan` accepts only reference-level asset bindings without an
asset digest or method claim. Core resolves the latest current ExecutionMethodPlan
and the exact canonical AssetVersion digest from the existing evidence journal.
`method-aware-video-route` accepts no plan, method, adapter or Provider selection;
Core resolves the latest current M10 plan and the immutable capability registry.
`explicit-audio-requirement-route` accepts one M9 `audioRequirementRef` and, only
when required, opaque `rightsBindingRef` and `voiceAssetVersionRef`. Core loads the
exact records and all digests server-side. `SILENCE` accepts neither ref and creates
no generation request.

No method-aware request may carry `executionMethod`, an execution-class override,
adapter capability/identity, Provider, local path, storage key, authority digest,
`publicationAllowed` or fallback policy. Public responses strip internal storage,
raw RightsBinding, voice snapshots and requested authority provenance. GET selects
the latest version by default and accepts an optional opaque `versionRef` query.

Legacy `/assets` and `/media` remain routable only for immutable history. POST is
an exact replay query: it succeeds only when the matching G4/G5 gate already exists
and its idempotency key and current input digests agree. It appends no facts and
performs no worker or artifact write. With no historic gate it returns respectively
`409 / legacy_asset_resolution_write_disabled` or
`409 / legacy_media_execution_write_disabled`. Historic v1 facts and GET readers
are unchanged; new runs cannot fall back to this path.

### Human-authored reviewed Script import

`POST /creator/api/v1/script-versions/reviewed-import` accepts exactly
`seriesRef`, `episodeRef`, `uploadedSourceByteDigest`,
`normalizedSourceDocumentDigest`, `reviewedDocumentDigest` and `content`.
Authentication injects `workspaceRef` and the authenticated service-credential ref;
clients cannot submit that ref or a first-version `scriptSceneRef`. The current auth
contract does not resolve a human user identity or RBAC role. Core generates scene refs
and a canonical Script-content digest.

The three document digests are authenticated-service-credential declarations only.
This route does not receive or re-hash the source documents and does not prove their
semantic binding to `content`. The result is an unconfirmed first ScriptVersion.
Generic confirmation of any reviewed-import lineage returns
`trusted_approval_required` until a trusted Owner approval resolver verifies the exact
subject. Existing generic generation/manual-edit paths do not carry reviewed-source
provenance. The internal unauthenticated alias remains forbidden.

### Trusted reviewed Script acceptance

`POST /creator/api/v1/script-versions/reviewed-import/accept` accepts exactly
`seriesRef`, `episodeRef`, `scriptRef`, `scriptVersionRef`, `idempotencyKey` and
`approvalRef`. Authentication injects `workspaceRef`. Client-supplied workspace,
actor, role, decision, authority, subject digest, document digest, publication or
confirmation fields are rejected.

The configured Script acceptance authority is external to request content. Core loads
one closed-world JSON authority bundle only when both
`CREATOR_SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_PATH` and
`CREATOR_SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_SHA256` are present. The path must be an
absolute non-symlink file and the separately configured SHA-256 must match its exact
bytes. Duplicate JSON keys, unknown fields, duplicate approval/decision refs, a
non-`PROJECT_LEAD` actor kind, a decision other than `ACCEPTED`, or any mismatch with
the persisted reviewed-import subject fails closed. With no configured authority the
route returns `trusted_approval_required`.

The verified subject binds the exact Workspace, Series, Episode, Script and
ScriptVersion together with the uploaded-source, normalized-document,
reviewed-document, canonical Script-content and import-provenance SHA-256 values
already stored on that first reviewed-import ScriptVersion. Core atomically appends
one immutable `v5.script-acceptance.v1` record and updates the Script's confirmed
version in the existing Lifecycle SQLite transaction. The additive
`script_acceptance@1` component lives in that same database; it does not change the
accepted global Lifecycle V2 marker and does not create another authority store.

An exact replay returns the original sealed record with `idempotentReplay=true` and
does not call the authority again. Reusing an idempotency key, approval ref or subject
with changed scope, lineage or evidence conflicts. Every acceptance remains
`publicationAllowed=false`; this route grants neither asset admission nor
Provider/GPU execution.

### Durable canonical registration

`POST /creator/api/v1/canonical-registrations/preflight` and
`POST /creator/api/v1/canonical-registrations` accept the same closed registration
package. Its top-level fields are exactly `registrationKey`, `idempotencyKey`,
`packageDigest`, `contentProfileRef`, `series`, `project`, `creativePlan`, `episode`,
`reviewedScript` and `acceptance`. Authentication injects `workspaceRef` and
`importedByRef`; client-supplied workspace or import actor fields are rejected. The
server must also be configured with a non-client
`CREATOR_CANONICAL_TARGET_REF`. An absent target fails closed with
`canonical_registration_unavailable`.

Preflight is deterministic and performs zero canonical writes. Core hashes the
server-held storage identity into a secret-free `canonicalTargetDigest`, so reusing a
target label on a different database cannot reproduce the same authority subject.
From that target binding, workspace, stable `registrationKey` and normalized request
digest, Core derives the exact planned Project,
Series, Episode, creative-plan, Script, ScriptVersion and Script-scene refs and returns
the exact `v5.script-acceptance-subject.v1` needed by the closed-world approval bundle.
It reports `canonicalMutationCount=0` and `publicationAllowed=false`. The operator can
therefore preflight, create and separately SHA-256-pin the exact authority bundle,
restart against the same explicit target, and then apply without accepting wildcard
or caller-authored authority.

Apply is available only on the shared Lifecycle SQLite assembly. One
`canonical-registration` lease and one `BEGIN IMMEDIATE` transaction create the
Series, Project/Series relationship, confirmed creative plan, EP01, first
`reviewed-import` ScriptVersion, exact trusted Script acceptance and immutable
`v5.canonical-registration.v1` receipt. Any failure before receipt commit rolls back every domain row.
The additive `canonical_registration@1` component and its foreign keys live in the
same Lifecycle V2 database; there is no project-specific database or second Project,
Script or acceptance owner.

The receipt binds the explicit target and physical-store digest, stable registration key, idempotency key,
package digest, normalized request digest, every root ref, exact accepted
ScriptVersion/acceptance digests and `publicationAllowed=false`. `packageDigest` is an
authenticated service-credential declaration that is sealed by the receipt; this
route does not receive or independently re-hash an external archive. Exact or
concurrent replay returns the original refs and receipt with
`idempotentReplay=true` and does not call the acceptance authority again. Reusing the
registration or idempotency key with changed target, package, scope, content,
approval or lineage returns `idempotency_conflict`. M5 binding, assets, ShotPlan,
Camera Contract, graph compilation and Provider/GPU authorization remain separate
later gates.

## K2 provider experiment semantics

`POST /episode-production-runs/{runRef}/provider-experiments` has two server-selected
modes. The client cannot choose the mode.

In the legacy commercial/publication mode it accepts exactly `idempotencyKey`,
`sourceGenerationRequestRef` and `providerCapabilityRef` after the authenticated
server injects workspace and run scope. It can execute only an existing M9 video
GenerationRequest against one exact current rights/policy bundle through V4.

For one exact server-configured K2 `INTERNAL_SELF_HOSTED` workspace/run it accepts
exactly `idempotencyKey` and `sourceGenerationRequestRef`. Provider/model/runtime facts
come from the validated V4 adapter configuration. Browser-supplied provider capability,
policy, rights, credential, usage, budget, attestation and publication fields are
rejected. The internal request and candidate contain no Rights Manifest, Provider
Policy or Budget Authority refs. A wrong workspace/run falls back to the unchanged
legacy fail-closed mode.

A successful response is deliberately an untrusted, unselected, non-admitted
candidate. It exposes safe provider/model/region, attempt, cost, latency, GPU/runtime,
digest and probe facts, but no credential source ref, internal path or storage key. It
does not create an AssetVersion, advance the K2 media gate, satisfy approval or allow
publication. `GET` returns only candidates whose stored artifact and digest can still
be independently verified; missing policy remains a fail-closed product error.
When GPU attestation is required, the immutable provider policy, V5 request, V4 worker
configuration and returned runtime facts must carry the same authority-approved
runtime-attestation ref and digest; a mismatch fails before provider submission or
candidate admission.

An internal candidate is `SELF_HOSTED_AI_GENERATED`, technically verified,
unselected, non-admitted and publication-disabled. One verified same-lineage internal
video candidate satisfies the bounded P1 state
`PASSED_INTERNAL_VIDEO_EXECUTION`; image/audio provider experiments and external
Rights/Provider/Budget authorities are not blockers for that internal P1 checkpoint.
This does not create an AssetVersion, Master, export, approval or publication fact.

## K2-002 dynamic image preflight semantics

`POST /episode-production-runs/{runRef}/dynamic-media-preflight` accepts an empty
body. Authentication injects `workspaceRef`, and the path injects
`productionRunRef`; client-supplied graph, identity, workspace, run, provider,
rights, budget or execution authority is rejected.

The operation reads one current `ShotPlanDraft` and IdentityLock and returns only
deterministic image request previews. It appends no gate or record, allocates no
GenerationRequest/Candidate/AssetVersion ref, invokes no V4 adapter and performs no
media write. Every plan/request level remains
`executionAuthorizationState=PREFLIGHT_ONLY_NOT_AUTHORIZED`,
`dispatchAllowed=false`, `candidateAdmissionAllowed=false` and
`publicationAllowed=false`. M11/video and audio preflight are not implemented.

For a v2 run, the historical `/shot-graph` route is transport compatibility only:
`POST` prepares a discriminated `shotPlanDraft` response and `GET` reads that draft.
It does not compile or return an `ExecutableShotGraph`, append `G3_SHOT_GRAPH`, create
`StoryboardVersion`/`CreativeShotVersion` facts, or advance beyond
`SCRIPT_VALIDATED`. The draft contains only the source package's
`editorialShotSize`; camera lens, angle and movement remain absent and
`cameraContractState=NOT_READY`.

The draft is a local structural representation with unverified ShotPlan and camera
authority. All legacy G4–G6, provider-experiment, M10/M11 candidate/review/
admission mutation routes reject that run with `execution_not_authorized`. A future
canonical M10 append or Provider/GPU dispatch requires a separate accepted contract,
all listed authorities and explicit Project Lead authorization.

## K2 M10 image-plan semantics

`POST /episode-production-runs/{runRef}/real-media-revision` accepts exactly
`idempotencyKey`. Workspace and run scope are injected from authentication and the
path. Provider/model/runtime, identity, prompt, file path, approval and publication
fields are rejected.

The operation is available only after the same run has a current passed G6 machine-QC
fact. It creates exactly four provider-neutral shot-image GenerationRequests from the
current four CreativeShotVersions. Every request binds both current K2 identity visual
references by ref, version ref and content digest and contains no internal path.

A successful response advances only to `REAL_IMAGE_PLAN_READY`. It explicitly reports
live capability verification pending, execution authorization not granted by the
plan, candidate selection not started, AssetVersion admission not started and
`publicationAllowed=false`. It does not invoke ComfyUI. `GET` returns the immutable
plan projection.

Live M10 execution requires a separate server-derived multi-reference image adapter
and fresh runtime capability evidence. The service must fail closed rather than use a
text-only fallback. Candidate execution, exact human selection and immutable image
admission are later bounded operations.

## K2 typed media control plane

ADR-0013 keeps one closed, digest-bound chain for both image and video revisions:

```text
GenerationRequest
→ V4 candidate and immutable receipt
→ V5 Candidate
→ V5 TechnicalValidation
→ V5 SemanticVisualQCDecision
→ V5 HumanSelectionDecision resolved through ApprovalAuthority
→ V5 AssetAdmission + immutable AssetVersion
```

Technical verification, semantic visual QC, human selection and admission are
separate facts. A successful V4 job or a visual-QC `PASS` does not select or admit an
asset. `FAIL`, missing, stale or superseded QC cannot authorize selection. All routes
below are rooted at
`/creator/api/v1/episode-production-runs/{runRef}`; authentication injects
`workspaceRef`, and the path injects `productionRunRef`.

| Method | Subresource | Closed public input and behavior |
| --- | --- | --- |
| `POST` | `/real-image-candidates` | accepts only `idempotencyKey`; V4 privately resolves and rehashes the exact M10 handoff, then V5 appends `Candidate` and `TechnicalValidation` records |
| `POST` | `/real-video-candidates` | accepts only `idempotencyKey`; V4 privately revalidates the complete four-slot M11 input, while an initial handoff appends all four typed candidates and a successor appends only changed-slot Candidate/TechnicalValidation pairs and reports unchanged slots in `reusedCandidates` |
| `POST` | `/semantic-visual-qc` | accepts an exact `TechnicalValidation` ref/version/digest, `visualQcRef`/version, the fixed review profile, evidence, checks, `PASS\|FAIL` and explicit supersession; Core injects the authenticated reviewer and seals all candidate/source digests |
| `POST` | `/media-selection` | records only a non-admitting exact human `REJECTED` decision; it accepts the QC ref/version/digest, selection ref/version, `approvalRef` and decision, while actor/authority/subject fields are server-resolved and forbidden in the request |
| `POST` | `/real-image-admission` | atomically records four authority-verified `SELECTED` decisions, admissions and image AssetVersions for the current exact four-shot manifest |
| `POST` | `/real-image-successor-admission` | atomically records one authority-verified image successor for one exact shot without rewinding `productionState` or activating a complete replacement manifest |
| `POST` | `/real-video-admission` | initial admission requires four exact selections and advances once to `REAL_VIDEO_READY`; a post-ready successor accepts the exact one-to-four changed-slot set, reuses unchanged current chains and atomically activates one complete four-slot manifest without another gate transition |
| `GET` | `/state-projection` | returns one V5 `evidenceRevisionToken`, orthogonal `rootState`, `productionState`, independently observed V4-only `runtimeState`, canonical `visualQcState`, `activeRevision` and per-candidate lifecycle; compatibility field `state` remains exactly `productionState` |
| `GET` | any typed media subresource above | returns the sanitized real-media revision/projection; no internal path, storage locator, credential, raw provider payload or authority evidence body is exposed |

The public caller cannot select an evidence `recordKind`, submit an internal path,
producer/runtime claim, `actorRef`, `subjectDigest` or authority claim. An initial
append returns `201`; an exact idempotent replay returns `200`; the same operation key
with changed canonical content conflicts. `AssetAdmission` and `AssetVersion` are
always emitted together by V5, never by a generic record endpoint.

### M11 initial and successor admission

Every `/real-video-admission` selection uses the same six closed fields:
`visualQcRef`, `visualQcVersion`, `visualQcDigest`, `selectionRef`,
`selectionVersion` and `approvalRef`. Initial admission requires four distinct
current slots and is the only call that advances
`REAL_VIDEO_PLAN_READY → REAL_VIDEO_READY`.

After readiness, the command contains one to four selections and must equal the
exact changed-slot set. The response still exposes a complete four-slot activation:
new slots append HumanSelectionDecision/AssetAdmission/AssetVersion chains; unchanged
slots reuse the current chains. The v2 activation reports `newAdmissionCount` and
`reusedAdmissionCount`, and each slot is `NEW_ADMISSION` or `REUSED_CURRENT`. It
directly supersedes the prior activation, performs no state transition and remains
exactly replayable only with the same closed batch.

The real-media bundle and state projection consume the same atomic V5 evidence
snapshot. If a current source image, request or candidate byte lineage changes, the
prior activation projects `videoLineageState.state=STALE_BLOCKED` and
`activeRevision.activationState=STALE`; canonical `videoAssetAdmissions` and
`videoAssetVersions` are empty until a complete four-slot activation becomes
current. `activeVideoAdmission` preserves the immutable historical activation for
audit. V4 `runtimeState` is observed separately and is not covered by
`evidenceRevisionToken`.

Canonical HumanSelection responses retain opaque `approvalRef`, actor/authority
refs, the authority-decision ref/digest/time and `subjectDigest` as sealed lineage
pins required for fail-closed client validation. These scalars are not the raw
authority evidence body. The external bundle, its `approvals` array and nested
subject object, raw bytes, credentials and operator configuration location are never
public DTO fields.

### BREAKING migration: `real-image-selection`

`POST /episode-production-runs/{runRef}/real-image-selection` is retained only as a
route alias for the unified, ApprovalAuthority-backed M10 admission operation. Its
current command body is identical to `/real-image-admission`:

```text
idempotencyKey = opaque-operation-key
selections = exactly four distinct items, each containing only:
  visualQcRef
  visualQcVersion
  visualQcDigest          # 64 lowercase hexadecimal characters
  selectionRef
  selectionVersion
  approvalRef
```

The `selections` array contains exactly four distinct current image decisions. The
former shape based directly on
`generationRequestRef + candidateRef + candidateContentDigest` is not translated and
now fails closed with `400 / invalid_request`; it cannot prove applicable canonical
QC or digest-pinned approval authority. Clients must first append candidates and
technical validation, append applicable semantic visual QC, then submit the exact QC
and `approvalRef` pins shown above. Client `actorRef`, reviewer, subject digest and
authority fields are forbidden; V5 resolves and records those facts from the
server-held ApprovalAuthority result.

`GET /real-image-selection` remains a backward-compatible read alias for the
sanitized real-media revision. The route name is preserved, but the unsafe historical
write schema is not. New clients should use `/real-image-admission`; existing clients
must migrate their write payload before deploying against this contract.

## Capability states

- `available`: accepted and exposed through public v1.
- `local_evidence_only`: the bounded Core surface exists but cannot make a
  publishable or external-provider claim.
- `authority_required`: accepted Core surface exists but the configured external
  authority is unavailable.
- `production_policy_required`: the bounded surface exists, but live commercial or
  publishing execution remains blocked until the current rights/provider production
  policy is present. The exact server-held K2 `INTERNAL_SELF_HOSTED` exception does
  not globally convert this capability to `available` or weaken publication policy.
- `not_open`: implementation is not authorized or not present.
- `disconnected`: an Experience Adapter runtime state; Core itself never reports this
  as a capability implementation state.

The v1 projection keeps this state enum unchanged. M12 remains
`production_policy_required` and lists the explicit M9 AudioRequirement plus
`M12_runtime_g0_not_complete`; it does not use generic M11 completion as a hard
dependency. M13 remains `local_evidence_only`, publishes the existing
`episode-production-runs/render-candidates` resource, and separately lists base
backend presence (`M13_base_backend_present`), incomplete product surface
(`M13_product_surface_incomplete`) and unauthorized Extension G0
(`M13_extension_g0_not_authorized`). None of those facts means M12 or M13 is
production-ready.

The M9→M12 bridge is an accepted V5 application boundary, not a new browser mutation
route in this contract. Its public DTO strips storage locators, and the capability
projection does not expose its evidence journal or add a second audio authority.

## Compatibility

The public v1 handler delegates to the same accepted Application/V5 methods as the
historical internal handler. It may normalize route names and stable envelopes, but it
may not add domain facts, weaken scope checks, bypass lifecycle leases or translate an
error into success.

## Authentication and workspace scope

The security amendment in
[`ADR-0007`](../../governance/ADR-0007-creator-public-api-authentication-and-workspace-isolation.md)
and its
[`normative contract`](../../architecture/CREATOR_PUBLIC_API_AUTHENTICATION_AND_WORKSPACE_ISOLATION_CONTRACT.md)
applies to the complete public v1 prefix:

- every `/creator/api/v1/*` request requires a server-to-server bearer credential;
- `/health` is the only unauthenticated liveness route;
- the authenticated credential selects exactly one `workspaceRef`;
- public query strings and command bodies must not contain `workspaceRef`, including
  empty, repeated or percent-encoded occurrences on `POST` routes;
- Core injects the authenticated workspace before calling accepted boundaries;
- browser code calls only the same-origin Frontend Adapter and never receives the Core
  token or origin;
- Core remains a no-CORS server API;
- non-loopback listeners expose no `/creator/internal/*` compatibility routes.

Authentication failure is `401 / authentication_required`. Attempted client workspace
selection is `400 / client_workspace_scope_forbidden`. Existing application-level
`403` errors, including `authority_unavailable`, keep their accepted meaning.
