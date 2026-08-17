# Creator Public HTTP/API v1

Status: `XR1 FROZEN / AUTH-W1 SECURITY AMENDMENT`

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
| M7–M19 | `/capabilities` status only | not authorized / not open |

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

## Capability states

- `available`: accepted and exposed through public v1.
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
