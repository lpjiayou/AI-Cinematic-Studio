# ADR-0007 — Creator Public API Authentication and Workspace Isolation

## Metadata

| Field | Value |
| --- | --- |
| ADR ID | `ADR-0007` |
| Status | `ACCEPTED FOR BOUNDED AUTH-W1` |
| Decision date | `2026-08-17` |
| Project Lead / Architecture Owner | `蔺鹏` |
| Decision authority | Project Lead directed the G0 gap audit and authorized automatic completion of the reviewed contract and its bounded implementation |
| Git revision base | `b7cfe40e3ff35514ef9a0b8bca8c91c2ff010d74` — remote-verified XR1 Creator Public API baseline |
| Frontend revision base | `95dc3f6b20ed679db6bc3da55906be94f6963630` — remote fluid-layout baseline; tree-equivalent local duplicate `0420b64caf7cab6e83b045cf8ea018e603609159` is not a code conflict |
| Authorized implementation | `ACS-AUTH-W1-G1 → G2 → G3 → GATE C → REMOTE VERIFY` only |
| Normative contract | [`CREATOR_PUBLIC_API_AUTHENTICATION_AND_WORKSPACE_ISOLATION_CONTRACT.md`](../architecture/CREATOR_PUBLIC_API_AUTHENTICATION_AND_WORKSPACE_ISOLATION_CONTRACT.md) |
| Related risk | `R-CORE-SEC-003` |
| Supersedes | None |

## Context

XR1 established the accepted runtime chain:

```text
Browser
→ same-origin Commercial Frontend
→ server-only Frontend Experience Adapter
→ Creator Public HTTP/API v1
→ Creator Application → V5 → V4 → V3
```

The remote-verified Core baseline exposes 27 declared `/creator/api/v1/*` endpoint
constants and retains `/creator/internal/*` routes for loopback compatibility. The
same handler currently has no caller authentication. It reads `workspaceRef` directly
from query parameters or JSON command bodies. Therefore a process that can reach the
Core port can select another workspace merely by changing request data.

The Frontend baseline already removes browser-supplied workspace/profile claims and
injects server configuration. That is a useful browser boundary, but it does not prove
the identity of the Frontend process to Core and cannot protect Core from a different
network client. The Core server also binds only to hard-coded `127.0.0.1:8765`; simply
making this address configurable without authentication would turn the latent scope
defect into a remotely reachable one.

The submitted draft correctly identified missing authentication, client-selected
workspace scope and loopback-only composition. Its proposed CORS requirement and
browser token language were rejected during G0 review because they conflict with the
accepted same-origin dependency chain. Browser JavaScript must never call Core or
receive the Core bearer credential. Core therefore remains a server-to-server API and
does not add CORS.

This decision is boundary hardening for the already accepted M1–M6 public surfaces.
It is not M19 RBAC, organization management or production multi-tenancy. It does not
open M7–M19, install M6 external authorities, prove provider/GPU readiness, or turn
local SQLite into a production persistence claim.

## Decision

### 1. Authenticate every public API request except liveness

Every request under `/creator/api/v1/*`, including `/capabilities`, requires an
`Authorization: Bearer <token>` header. `/health` is the only unauthenticated route and
returns liveness only. It must not expose capability, workspace, provider, persistence
or credential information.

Missing, malformed, disabled or unknown credentials return a stable HTTP `401` error
and `WWW-Authenticate: Bearer`. Authentication occurs before public route dispatch, so
an unauthenticated request cannot use route behavior to enumerate the public surface.

### 2. Derive workspace scope from the authenticated principal

Each configured credential maps to exactly one non-empty `workspaceRef`. Core injects
that value into the accepted Application/V5 command or query. Public requests are
forbidden from supplying `workspaceRef` in a query string or JSON body; attempting to
do so returns HTTP `400 / client_workspace_scope_forbidden`.

The Frontend Experience Adapter must therefore stop sending `workspaceRef`. It keeps
the bearer token and Core origin server-only. `contentProfileRef` remains a server-side
Frontend configuration value for the two accepted creation commands that require it;
it is not treated as the authentication principal in this bounded wave.

Application-level authorization errors retain their existing semantics. In particular,
M6 external-authority absence remains `403 / authority_unavailable`. This wave does
not invent a new reachable `403` credential mismatch case; future resource policy may
use `403` only under a separately accepted contract.

### 3. Store only token digests in Core configuration

Core loads a versioned JSON credential registry from a server-only file named by
`CREATOR_PUBLIC_API_TOKEN_CONFIG`. The registry stores credential metadata,
`workspaceRef`, and a lowercase SHA-256 token digest; it never stores or returns the
raw bearer token. Token comparison is constant-time. Test tokens are generated at
runtime and no real credential or digest fixture is committed.

Frontend receives the corresponding raw token only through server environment variable
`CREATOR_CORE_TOKEN`. No `NEXT_PUBLIC_*` form is allowed. Logs, errors, request
projections, browser bundles and Gate C output must not contain the token.

### 4. Make bind configuration explicit and fail closed

`CREATOR_PUBLIC_API_HOST` and `CREATOR_PUBLIC_API_PORT` replace the hard-coded bind,
defaulting to `127.0.0.1:8765`. Startup fails before listening when the credential
registry is missing or invalid. A non-loopback bind additionally disables all
`/creator/internal/*` compatibility routes; only authenticated public v1 and `/health`
remain reachable.

Loopback test and compatibility servers may explicitly enable internal routes. Public
v1 never becomes anonymous in that mode. `create_server` must fail public requests
closed when no authenticator was provided.

### 5. Preserve the same-origin, no-CORS topology

Core does not emit `Access-Control-Allow-*` headers and does not implement a browser
preflight policy. Browser code continues to call only `/api/creator/*` on the Frontend
origin. Any future direct-browser or third-party client topology requires a separate
gateway/security decision and is outside AUTH-W1.

## Exact authorized wave

### G0 — contract and governance freeze

- accept this ADR and the normative contract;
- update the public HTTP contract and current milestone;
- register `R-CORE-SEC-003`;
- commit, push and remote-verify G0 before implementation.

### G1 — Core authentication and scope boundary

- add the versioned credential registry and bearer authenticator;
- protect all public v1 routes and add liveness-only `/health`;
- reject client `workspaceRef` and inject the principal workspace;
- preserve stable sanitized envelopes and existing domain/authority semantics;
- add focused unit, contract and integration tests.

### G2 — deployable server composition boundary

- add validated host, port and credential-config environment composition;
- refuse startup on missing/invalid security configuration;
- disable internal compatibility routes for non-loopback listeners;
- keep CORS absent and verify the public-only surface.

### G3 — Frontend server-only credential migration

- add required server-only `CREATOR_CORE_TOKEN` configuration;
- attach the bearer header only in the Experience Adapter;
- remove all Frontend-to-Core `workspaceRef` injection;
- preserve distinct 401 authentication and 403 application-authority product states;
- update integration documentation, tests and Gate C.

### Gate C and remote verification

- run the complete Core and Frontend suites and production build;
- run two real processes with runtime-generated credentials;
- prove browser scope claims cannot affect Core workspace selection;
- prove missing/invalid tokens fail closed and M6 retains its separate authority state;
- scan tracked diffs and built browser assets for credential exposure;
- push without force and prove local/remote SHA equality and clean worktrees.

## Alternatives

### A. Keep loopback-only operation without authentication

- Benefit: no migration.
- Cost: does not permit a controlled remote Frontend deployment and leaves Core scope
  selected by arbitrary request data.
- Decision: rejected.

### B. Let the browser call Core directly with CORS and a token

- Benefit: one fewer server hop.
- Cost: exposes a reusable credential and Core origin to browser code, violates the
  accepted same-origin Experience Adapter boundary, and expands the attack surface.
- Decision: rejected.

### C. Trust an `X-Workspace-Ref` header from the Frontend

- Benefit: small code change.
- Cost: moves the same unauthenticated caller-controlled scope from body/query to a
  header and establishes no identity.
- Decision: rejected.

### D. Add a bounded server-to-server bearer principal mapped to one workspace

- Benefit: smallest fail-closed change that authenticates the caller and removes
  client-selected tenancy while preserving the accepted layers.
- Cost: requires credential distribution, rotation and coordinated Core/Frontend
  deployment.
- Decision: accepted.

### E. Implement complete M19 identity, organizations and RBAC now

- Benefit: broader long-term authorization features.
- Cost: M19 is not open; this would invent domain, persistence and policy outside the
  accepted milestone.
- Decision: rejected for AUTH-W1.

## Consequences

### Positive

- a reachable Core public API can identify the Frontend service before dispatch;
- workspace isolation no longer depends on caller-supplied data;
- non-loopback listening cannot silently expose historical internal routes;
- the browser remains free of Core origins and credentials;
- authentication failures and M6 authority failures remain independently diagnosable.

### Cost and residual risk

- operators must provision matching Core digest and Frontend raw-token configuration;
- static bearer credentials require a future rotation procedure and secret manager for
  production deployment;
- denial of a leaked token requires registry replacement and process reload;
- this does not provide user identity, organization RBAC, quotas or audit billing;
- production persistence, provider, media and M7–M19 gates remain unchanged.

`R-CORE-SEC-003` tracks the current unauthenticated/public-scope risk through Gate C.
AUTH-W1 may move it to monitoring after remote-verified evidence, but may not claim all
commercial security risks are closed.

## Migration and rollback

1. Publish and remote-verify G0.
2. Implement G1/G2 on the G0 branch without changing domain schemas or accepted M1–M6
   behavior.
3. Implement G3 from the exact remote Frontend fluid-layout baseline.
4. Deploy Core and Frontend configuration atomically for Gate C; the old Frontend is
   expected to receive `400` after Core stops accepting workspace claims.
5. Validate complete suites, two-process behavior and secret non-disclosure.
6. Publish both branches without force and remote-verify them.

Before deployment, rollback is a normal revert or branch abandonment. After a paired
deployment, rollback must restore both Core and Frontend revisions together; rolling
back only one side is forbidden because their workspace-scope contracts intentionally
change in lockstep. No persistent data migration is part of this decision.

## Non-goals

This ADR does not authorize:

- direct browser access to Core, CORS or browser-held bearer credentials;
- OAuth/OIDC, users, sessions, organizations, roles, permissions or billing;
- M6 external authority implementation or any M7–M19 capability;
- new domain facts, database schema changes or production persistence claims;
- provider credentials, GPU execution, render workers or production deployment;
- final feature acceptance or a `Production Ready` declaration.

## Approval record

| Role | Owner | Decision | Date | Notes |
| --- | --- | --- | --- | --- |
| Project Lead | `蔺鹏` | `APPROVED` | `2026-08-17` | Directed G0 gap closure and automatic completion after reviewed correction |
| Architecture Owner | `蔺鹏` | `APPROVED` | `2026-08-17` | Existing Creator Application/V5 dependency direction remains unchanged |
| Interface/security implementation review | Codex factual audit | `PASS FOR BOUNDED DESIGN` | `2026-08-17` | Corrected endpoint count, CORS topology, browser-token handling, workspace authority and M19 overclaim |

## Change history

| Date | Change | Authority |
| --- | --- | --- |
| `2026-08-17` | Replaced the submitted draft with a fact-checked server-to-server authentication and workspace-isolation decision | Project Lead / Architecture Owner `蔺鹏` |
