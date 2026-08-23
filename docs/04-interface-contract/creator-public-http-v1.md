# Creator Public HTTP/API v1

Status: `XR1 FROZEN / AUTH-W1 SECURITY AMENDMENT / K2 P0-P1 + M10 IMAGE-PLAN BOUNDED EXTENSION`

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
| M3 | `/script-workspaces`, `/script-versions/*` | Script Studio Application/public boundary |
| M4 | `/projects`, `/project-contexts` | Project Context public boundary |
| M5 | `/series-planning-workspaces`, `/series-plan-*` | Series Planning + Series Director boundaries |
| M6 | `/series-intelligence-workspaces`, `/series-intelligence/*` | accepted Series Intelligence public boundary |
| M7–M8 | `/episode-production-runs/{runRef}/shot-graph` | bounded K2 V5 Shot Graph service |
| M9 | `/episode-production-runs/{runRef}/assets` | bounded K2 V5 Asset Pipeline service |
| M10 | `/episode-production-runs/{runRef}/real-media-revision`, `/production-readiness` | bounded K2 V5 image-first revision planner; live execution separately gated |
| M11 | `/episode-production-runs/{runRef}/provider-experiments`, `/media` | bounded K2 V5 experiment/media services over V4 |
| M12 | `/episode-production-runs/{runRef}/production-readiness`, `/media` | bounded K2 V5 media service; live audio remains blocked |
| M13–M14 | `/episode-production-runs/{runRef}/preview`, `/finalize` | bounded K2 V5 delivery service over V4/V3 |
| M15 | `/episode-production-runs/{runRef}/delivery`, preview/export content | bounded K2 V5 delivery authority |
| M16–M19 | `/capabilities` status only | not open at the current gate |

## Envelopes and transport

- Success: `{ "ok": true, ... }`.
- Failure: `{ "ok": false, "error": { "code": string, "message": string } }`.
- Commands require `Content-Type: application/json`.
- Request bodies are limited to 512000 bytes.
- Responses use UTF-8 JSON and `Cache-Control: no-store`.
- Core references and version references returned by successful commands are opaque.
- Provider diagnostics, credentials, repository types and raw exceptions are forbidden.

## Candidate and confirmation semantics

Generation routes return candidates. A candidate becomes a Core fact only through its
specific confirmation route. The Experience Adapter must preserve
`confirmationRequired` and must never infer confirmation from a successful generation
response. The M1 candidate response also carries the Core-issued opaque
`sourcePlanRef` and `sourcePlanVersion`; browser code must return those exact values on
confirmation and must not mint or infer a source-plan reference.

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

## Capability states

- `available`: accepted and exposed through public v1.
- `local_evidence_only`: the bounded Core surface exists but cannot make a
  publishable or external-provider claim.
- `authority_required`: accepted Core surface exists but the configured external
  authority is unavailable.
- `not_open`: implementation is not authorized or not present.
- `disconnected`: an Experience Adapter runtime state; Core itself never reports this
  as a capability implementation state.

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
- public query strings and command bodies must not contain `workspaceRef`;
- Core injects the authenticated workspace before calling accepted boundaries;
- browser code calls only the same-origin Frontend Adapter and never receives the Core
  token or origin;
- Core remains a no-CORS server API;
- non-loopback listeners expose no `/creator/internal/*` compatibility routes.

Authentication failure is `401 / authentication_required`. Attempted client workspace
selection is `400 / client_workspace_scope_forbidden`. Existing application-level
`403` errors, including `authority_unavailable`, keep their accepted meaning.
