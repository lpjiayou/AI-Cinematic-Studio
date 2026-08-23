# ADR-0006 — V5-Owned Text Generation Capability Boundary

## Metadata

| Field | Value |
| --- | --- |
| ADR ID | `ADR-0006` |
| Status | `ACCEPTED FOR BOUNDED G1` |
| Decision date | `2026-08-13` |
| Project Lead / Architecture Owner | `蔺鹏` |
| Decision authority | Project Lead explicitly selected `Application → V5 → V4` and directed the architecture violation to be repaired |
| Git revision base | `c524486c05c21b270a7dd75e89fae4312430736a` — remote-verified G3/P3-G0 candidate lineage, not Owner Accepted |
| Underlying accepted technical base | `8227c6c616140824fd70de920dc6fcf459bb734d` |
| Authorized implementation | `ACS-ARCH-R1-V5-TEXT-GENERATION-G1` only |
| Normative contract | [`V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md`](../architecture/V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md) |
| Related risks | `R-CORE-ARCH-001`, `R-CORE-GOV-002` |
| Supersedes | None |

## Context

The current Creator Application contains four active production files that directly
import the public V4 Platform package:

- `apps/creator_workspace_mvp/ai_director.py`;
- `apps/creator_workspace_mvp/script_studio.py`;
- `apps/creator_workspace_mvp/series_director.py`;
- `apps/creator_workspace_mvp/server.py`.

The three candidate-generation services construct V4 `TextMessage` and
`TextGenerationRequest` objects, call the V4 `TextProvider`, and translate V4 provider
exceptions. The Creator server also calls the V4 environment factory and owns an
unconfigured V4-compatible provider implementation.

This is a real production dependency, not dead code or a test-only path. It conflicts
with the accepted V2.3 adjacent-layer chain:

```text
Creator Application → V5 Core OS → V4 Platform
```

`architecture/dependency-map.md` expressly prohibits Application Layer from directly
depending on V4 Platform. The Application Layer overview also prohibits Application
from directly importing, calling, configuring or testing V4. No accepted ADR or
bounded exception authorizes the four direct production imports.

The V4 boundary itself is provider-neutral and public. The defect is therefore not a
direct DeepSeek private-adapter import. The defect is that Application bypasses V5,
inherits V4 DTO/error/execution-policy concerns, and prevents V5 from enforcing the
accepted adjacent-layer capability boundary.

An independent read-only interface and test review recorded the following facts:

- exactly four active Application production files import `services.v4_platform`;
- one accepted contract test positively requires the Series Director direct V4 import;
- related tests pass under the same dependency structure and therefore do not prove
  architecture compliance;
- no repository-wide guard currently rejects `apps → services.v4_platform`;
- the smallest behavior-preserving repair requires nine production/source files and
  eleven test files, frozen below and in the normative contract;
- V4 provider-adapter tests may continue to test V4 directly, but an Application test
  must use the V5-facing testing boundary.

The repository also contains Source-of-Truth assertions that `Full Core Audit Report
v1.2` was independently accepted, while the current repository and visible Git object
history do not provide a repository-resident or hash-addressed report artifact. That
provenance gap is recorded separately as `R-CORE-GOV-002`. It is non-blocking for this
bounded repair because G1 has its own direct code, interface, architecture and test
evidence. G1 must not claim to recover or close the independent audit provenance.

## Decision

Create one V5-owned, Application-facing Text Generation capability boundary. After
G1, the production dependency must be:

```text
Creator Application
→ V5 TextGenerationCapability
→ V5-to-V4 mapping boundary
→ V4 TextProvider
→ replaceable provider adapter
```

### V5-owned public contract

V5 owns the stable Application-facing concepts:

- `TextGenerationPurpose`;
- `TextGenerationMessage`;
- `TextGenerationCommand`;
- `TextGenerationCapability`;
- V5 Text Generation capability errors;
- the public environment and fail-closed composition factories.

The accepted purposes are exactly:

```text
AI_DIRECTOR_CANDIDATE
SCRIPT_CANDIDATE
SCRIPT_SCENE_REWRITE
SERIES_PLAN_CANDIDATE
```

Application supplies only a purpose and messages. It must not supply or import V4
`response_format`, `max_tokens`, `temperature`, `timeout_seconds`, provider type,
model, endpoint or adapter error types.

### V5-to-V4 mapping

The V5 public boundary maps V5 DTOs to the existing public V4 request and provider
port. Only the V5 Text Generation implementation may import V4 for this production
path. V5 maps all V4 errors into V5-owned safe errors without exposing credentials,
headers, raw provider output or provider-specific exception bodies.

The bounded policy profiles preserve the accepted runtime behavior:

| Purpose | Response format | Max tokens | Temperature | Timeout seconds |
| --- | --- | ---: | ---: | ---: |
| `AI_DIRECTOR_CANDIDATE` | `json_object` | `6000` | `0.4` | `35` |
| `SCRIPT_CANDIDATE` | `json_object` | `8000` | `0.35` | `45` |
| `SCRIPT_SCENE_REWRITE` | `json_object` | `3500` | `0.35` | `45` |
| `SERIES_PLAN_CANDIDATE` | `json_object` | `16000` | `0.3` | `90` |

These policies are owned by V5 and cannot be overridden by an Application command.

### Responsibility preserved

Application continues to own:

- use-case prompt construction;
- candidate schema parsing and local validation;
- the existing maximum-one-repair orchestration;
- mapping stable V5 capability errors to existing Application/product errors;
- existing HTTP response and safe diagnostic behavior.

V4 continues to own:

- the provider-neutral `TextProvider` port;
- the V4 request/message types used inside V4;
- provider configuration and adapter selection;
- DeepSeek and future provider adapters;
- transport and raw provider-response validation.

V5 must not copy, re-export, subclass or alias V4 DTOs and errors as a facade. The V5
types are an independent adjacent-layer contract and the V5 implementation performs an
explicit mapping.

The capability is stateless. It must not be added to `LifecycleAssembly`, coupled to
SQLite, or placed under an M6 domain package. Server composition creates one V5
capability instance and shares it with AI Director, Script Studio and Series Director.

## Exact G1 implementation allowlist

G1 may create or modify only the following production/source paths:

```text
services/v5_core_os/text_generation/__init__.py
services/v5_core_os/text_generation/contracts.py
services/v5_core_os/text_generation/errors.py
services/v5_core_os/text_generation/public.py
services/v5_core_os/text_generation/testing.py
apps/creator_workspace_mvp/ai_director.py
apps/creator_workspace_mvp/script_studio.py
apps/creator_workspace_mvp/series_director.py
apps/creator_workspace_mvp/server.py
```

G1 may create or modify only the following test paths:

```text
tests/unit/test_v5_text_generation_boundary.py
tests/unit/test_ai_director_phase1.py
tests/unit/test_script_studio_m3.py
tests/unit/test_series_planning_m5.py
tests/integration/test_ai_director_project_draft_flow.py
tests/integration/test_creator_project_context.py
tests/integration/test_creator_script_studio.py
tests/integration/test_creator_series_episode.py
tests/integration/test_creator_series_planning.py
tests/contract/test_creator_core_no_legacy_ui_contract.py
tests/contract/test_creator_series_planning_contract.py
```

No other production, test, governance, architecture or configuration path is part of
G1. An unexpected required path is a stop condition, not an implied expansion.

## Alternatives

### A. Keep the current direct Application-to-V4 imports

- Benefit: no short-term code change.
- Cost: preserves an explicit V2.3 violation across M1, M3, M5 and server composition.
- Decision: rejected.

### B. Re-export V4 classes from a V5 `__init__.py`

- Benefit: very small import-only diff.
- Cost: leaves V4 DTO, errors and policy as Application contracts and merely hides the
  same dependency behind a namespace facade.
- Decision: rejected.

### C. Move all prompts and candidate validation into V5

- Benefit: a larger central service could own complete generation use cases.
- Cost: changes established Application responsibilities and candidate contracts,
  expands M1/M3/M5 behavior and creates avoidable migration risk.
- Decision: rejected for this bounded repair.

### D. Introduce a V5-owned capability contract and explicit V5-to-V4 adapter

- Benefit: restores adjacent-layer direction, preserves V4 provider replaceability,
  centralizes execution policy and supports an enforceable static guard.
- Cost: requires a controlled DTO/error/test migration.
- Decision: accepted.

## Consequences

### Positive

- all Application production imports of V4 can become zero;
- V5 can own stable generation intent and execution profiles;
- V4 provider changes no longer propagate DTO and error types into Application;
- a static architecture test can prevent recurrence;
- existing provider adapters and environment keys remain reusable.

### Cost

- tests that currently inject V4 `FakeTextProvider` into Application services must use
  the V5 testing capability instead;
- the contradictory Series Planning contract assertion must be legitimately replaced
  with the accepted adjacent-layer assertion;
- V4-specific adapter tests remain separate from V5/Application tests.

### Risks

- behavioral drift while mapping profiles or safe errors: controlled by exact policy
  assertions and unchanged Application HTTP/regression tests;
- accidental facade implementation: controlled by AST/import checks and independent
  V5 DTO definitions;
- scope expansion into business behavior: controlled by the exact allowlist and stop
  conditions;
- architecture recurrence: tracked by `R-CORE-ARCH-001` and the all-`apps` static guard;
- unrelated audit-report provenance: tracked separately by `R-CORE-GOV-002`.

## Migration and rollback

1. G0 must be committed, pushed and remote-verified before G1 begins.
2. G1 branches from the remote-verified G0 SHA as
   `codex/acs-arch-r1-v5-text-generation-g1`.
3. Add the V5 contract, errors, boundary, factory and V5-only fake.
4. Migrate the three Application services without changing prompt, parsing, repair or
   candidate-validation semantics.
5. Migrate server composition to V5 factories and remove its V4-compatible local
   provider implementation.
6. Migrate the allowlisted tests and add the architecture/import guard.
7. Run targeted, relevant lifecycle and Full Core regression; run AST/import,
   `git diff --check` and secret checks.
8. Commit once, push, fetch and prove Local SHA equals Remote SHA, ahead/behind `0/0`
   and clean status.
9. Stop for Project Lead owner review. G1 may report only a complete candidate.

No data, schema or persistent state is migrated. Before G1 acceptance, rollback is a
normal revert of the isolated G1 commit or abandonment of the G1 branch while keeping
the remote-verified G0 checkpoint. Force push is forbidden. If rollback would require
any data operation, execution stops because that condition is outside this ADR.

## Non-goals

This ADR does not authorize:

- prompt redesign, schema change, repair-count change or candidate lifecycle change;
- V4 public-contract or provider-adapter redesign;
- a second provider stack, provider registry, router, queue, worker or retry engine;
- HTTP/Public API/DTO, Auth, RBAC or permission changes;
- persistence, SQLite, migration, PostgreSQL or formal port-8765 deployment;
- M6-P3, M7-M19, V3, Compute, GPU, ComfyUI or Frontend work;
- Full Core Audit Report v1.2 provenance closure;
- Production Ready or final feature acceptance.

## Approval record

| Role | Owner | Decision | Date | Notes |
| --- | --- | --- | --- | --- |
| Project Lead | `蔺鹏` | `APPROVED` | `2026-08-13` | Explicitly selected the V5-owned boundary and directed repair to begin |
| Architecture Owner | `蔺鹏` | `APPROVED` | `2026-08-13` | Accepted `Application → V5 → V4` for bounded G1 |
| Interface/Test specialist review | Independent read-only review | `PASS FOR BOUNDED DESIGN` | `2026-08-13` | Exact current imports, injection points, policy values and tests reviewed; no write authority exercised |

## Change history

| Date | Change | Authority |
| --- | --- | --- |
| `2026-08-13` | Accepted bounded V5 Text Generation boundary and G1 migration | Project Lead / Architecture Owner `蔺鹏` |
