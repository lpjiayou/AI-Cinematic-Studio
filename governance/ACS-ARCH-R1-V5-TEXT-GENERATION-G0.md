# ACS-ARCH-R1 V5 Text Generation G0 Governance Authorization

> Status: `GOVERNANCE / ARCHITECTURE CHECKPOINT CANDIDATE`
>
> Decision date: `2026-08-13`
>
> Decision owner: Project Lead / Architecture Owner `蔺鹏`
>
> Execution wave: `G0 → G1 AUTO-SEQUENTIAL ONLY`
>
> Git revision base: `c524486c05c21b270a7dd75e89fae4312430736a` — remote-verified
> G3/P3-G0 candidate lineage, not Owner Accepted
>
> Underlying accepted technical base: `8227c6c616140824fd70de920dc6fcf459bb734d`

## 1. Project Lead decision

After review of the confirmed Application-to-V4 dependency violation, Project Lead
and Architecture Owner `蔺鹏` explicitly selected this remedy and directed repair to
begin:

```text
建立 V5-owned Text Generation capability boundary，
迁移为 Application → V5 → V4。
```

This decision:

- accepts [`ADR-0006`](ADR-0006-v5-text-generation-capability-boundary.md) for the
  bounded G1 implementation;
- accepts the normative
  [`V5 Text Generation Capability Contract`](../architecture/V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md);
- authorizes this governance-only G0 checkpoint;
- authorizes automatic transition from a remote-verified G0 SHA into exactly one
  bounded G1 implementation checkpoint;
- does not authorize any milestone or work package after G1.

The authorization is a repair of the existing V2.3 dependency direction. It does not
change the accepted high-level chain or create an architecture exception.

## 2. Confirmed finding and independent read-only review

The review confirmed four active production dependencies:

| Application source | Current V4 dependency |
| --- | --- |
| `apps/creator_workspace_mvp/ai_director.py` | V4 messages, request, provider and errors |
| `apps/creator_workspace_mvp/script_studio.py` | V4 messages, request, provider and errors |
| `apps/creator_workspace_mvp/series_director.py` | V4 messages, request, provider and errors |
| `apps/creator_workspace_mvp/server.py` | V4 environment factory, provider contract and configuration error |

The independent interface/test review also confirmed:

- these are active runtime paths;
- the V4 dependency is its public provider-neutral port, not a direct private DeepSeek
  adapter dependency;
- one contract test currently freezes the invalid Series Director direct import;
- related functional tests pass but do not establish layer compliance;
- no formal waiver or exception exists;
- a behavior-preserving V5 boundary can be implemented within the exact G1 allowlist.

The read-only review made no file change and exercised no implementation authority.
Its verified findings and design constraints are incorporated into ADR-0006 and the
normative contract so G1 does not depend on an untracked external interpretation.

## 3. G0 scope

G0 records the accepted decision, normative contract, current risks, exact execution
authority and synchronized Source-of-Truth state. It contains no production or test
implementation.

### Exact G0 file allowlist — eleven paths

```text
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
architecture/module-responsibility-matrix.md
architecture/V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md
governance/ARCHITECTURE_CHANGE_PROCESS.md
governance/ADR-0006-v5-text-generation-capability-boundary.md
governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G0.md
governance/RISK_REGISTER.md
```

Any changed path outside this list blocks G0 completion. Production, tests, SQLite,
migrations, HTTP handlers, Frontend product/source/IA/visual behavior and provider
implementation diffs must be zero in G0. The UI Master change is restricted to its
explicit current-governance synchronization block and revision note; it does not
authorize or alter Frontend implementation or product design.

## 4. Accepted boundary

The only accepted target dependency is:

```text
Creator Application
→ V5 TextGenerationCapability
→ V5-to-V4 mapping boundary
→ V4 TextProvider
→ replaceable provider adapter
```

V5 owns:

- the Application-facing generation purpose;
- V5 message and command DTOs;
- the V5 capability port;
- stable safe errors;
- closed purpose-to-policy profiles;
- environment/fail-closed composition;
- explicit V5-to-V4 DTO and error mapping.

Application retains prompts, candidate validation and its current bounded repair
orchestration. V4 retains provider execution, factory and adapters. G1 cannot move
business-domain facts, prompts, HTTP contracts or V4 provider ownership into V5.

## 5. Exact G1 authority

G1 task ID:

```text
ACS-ARCH-R1-V5-TEXT-GENERATION-G1
```

G1 branch:

```text
codex/acs-arch-r1-v5-text-generation-g1
```

G1 must branch from the fetched, remote-verified G0 SHA. It may create or modify only
the following nine production/source paths:

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

G1 may create or modify only the following eleven test paths:

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

G1 cannot modify G0 governance/architecture files. A later owner-acceptance or
closeout checkpoint may update status and risk evidence only after G1 has stopped.

## 6. Bounded AUTO-SEQUENTIAL rule

The automatic wave contains exactly one transition:

```text
ACS-ARCH-R1-V5-TEXT-GENERATION-G0
→ ACS-ARCH-R1-V5-TEXT-GENERATION-G1
→ STOP
```

G0 may auto-transition to G1 only when all of these are true:

1. exactly the eleven G0 files changed;
2. production and test diff is zero;
3. ADR-0006 and the normative contract are consistent with all synchronized
   Source-of-Truth files;
4. Markdown structure and local links pass;
5. secret scan and `git diff --check` pass;
6. the G0 commit is pushed;
7. fetch confirms Local SHA equals Remote SHA;
8. ahead/behind is `0/0` and worktree is clean;
9. no Source-of-Truth, authorization, security or Git conflict remains.

No further conversational approval is required for that one bounded transition. The
standing automatic authority does not waive any gate or extend beyond G1.

## 7. G1 implementation and acceptance gates

G1 must preserve all existing prompt, schema, error-product, HTTP, persistence and
domain behavior while changing the dependency direction. Completion requires:

- the exact 9+11 implementation/test allowlist;
- `apps/**/*.py` imports of `services.v4_platform` equal `0`;
- only the V5-to-V4 implementation module imports V4 inside the new V5 package;
- V5 DTOs/errors are independently owned, not aliases or re-exports of V4;
- all four exact execution profiles pass unit tests;
- V4 configuration/timeout/unavailable errors map to safe V5 errors;
- Application services use the V5 fake in their tests;
- V4-specific adapter tests remain passing and separated from Application injection;
- targeted M1/M3/M5 tests pass;
- relevant lifecycle regression passes;
- Full Core regression passes without exclusions;
- Python AST/import guard, secret scan and `git diff --check` pass;
- one G1 commit is pushed and remote-verified;
- Local SHA equals Remote SHA, ahead/behind `0/0`, worktree clean.

No formal browser/live/provider call is required because public HTTP behavior does not
change, the provider adapter does not change and credentials are not an input to G1.
Existing HTTP integration tests remain mandatory.

G1 may report only:

```text
ACS-ARCH-R1-V5-TEXT-GENERATION-G1 COMPLETE CANDIDATE
READY FOR PROJECT LEAD OWNER REVIEW
```

It may not claim final acceptance.

## 8. Stop conditions

Stop immediately if any of these occurs:

- a file outside the G1 allowlist is required or changed;
- implementation needs a prompt, candidate schema, HTTP/Public API or error-product
  contract change;
- implementation needs SQLite, migration, PostgreSQL, formal database or persistent
  state work;
- V4 public request, factory, adapter or DeepSeek behavior must change;
- a second provider stack, router, queue, worker, retry engine or new dependency is
  required;
- an accepted test would need deletion, skip or weakening;
- secrets, credentials, raw provider content or unsafe exception text could escape;
- the G0 base is not remote-verified or Git history diverges;
- Source-of-Truth files conflict;
- M6-P3, M7+, V3, Compute, GPU, Frontend or deployment work becomes necessary;
- any mandatory test or remote verification gate fails.

After G1 commit and remote verification:

```text
STOP — OWNER REVIEW REQUIRED
```

Do not begin a closeout, M6-P3, another architecture remediation or any later
milestone automatically.

## 9. Rollback

G0 is an independent governance checkpoint and remains preserved even if G1 is
abandoned. G1 introduces no data or schema migration. Before owner acceptance, its
rollback is:

1. stop the runtime if a local test process is active;
2. normally revert the isolated G1 commit or abandon the G1 branch;
3. retain the remote-verified G0 branch and SHA;
4. rerun the prior accepted regression if a revert commit is created;
5. push and remote-verify the rollback commit when a remote G1 commit was already
   published.

Force push, history rewrite, destructive reset and data deletion are not authorized.

## 10. Non-goals and preserved exclusions

This execution wave does not authorize:

- M6-P3-B1, M6-P3-G1 or any other M6-P3 implementation;
- M7-M19 implementation;
- formal port-8765 database access or deployment;
- SQLite schema/migration or PostgreSQL;
- Creator HTTP/Public API/DTO, Auth, RBAC or Permission changes;
- Frontend or cross-repository UI work;
- V4 redesign, Provider Registry, Router, Queue, Worker or retry orchestration;
- V3 Render, Compute, GPU or ComfyUI work;
- content-safety, rights, quota or tenant-policy expansion;
- recovery or closure of the Full Core Audit Report v1.2 provenance gap;
- Production Ready or final feature acceptance.

## 11. Risk disposition

`R-CORE-ARCH-001` is `缓解中 / MITIGATING`. It may move to monitoring only after G1
proves zero Application-to-V4 production imports, passes all regression and becomes
remote-verified. It may be closed only through a later governance update with owner
acceptance evidence.

`R-CORE-GOV-002` is `开放 / OPEN / NON-BLOCKING`. The repository currently has an
acceptance assertion for Full Core Audit Report v1.2 but no repository-resident or
hash-addressed artifact that can be independently reproduced. This does not block G1
because G1 uses direct targeted and Full Core evidence. G1 cannot close, relabel or
silently treat that provenance risk as resolved.

## 12. G0 completion report requirements

The G0 report must include:

- branch, base SHA, commit SHA and remote SHA;
- exact eleven-file changed scope;
- production/test/SQLite/migration/Frontend product-source/IA diff equal to zero;
- Markdown/local-link, secret and `git diff --check` results;
- Local equals Remote, ahead/behind and worktree status;
- next task exactly `ACS-ARCH-R1-V5-TEXT-GENERATION-G1`;
- explicit statement that G1 is not yet owner accepted.

## 13. Approval record

| Role | Owner | Decision | Date | Scope |
| --- | --- | --- | --- | --- |
| Project Lead | `蔺鹏` | `APPROVED` | `2026-08-13` | G0 and bounded automatic G0→G1 execution |
| Architecture Owner | `蔺鹏` | `APPROVED` | `2026-08-13` | V5-owned adjacent-layer boundary in ADR-0006 |
| Independent interface/test review | Read-only specialist review | `PASS FOR G0 DESIGN` | `2026-08-13` | Exact imports, interfaces, profiles, tests and minimum allowlist |

## 14. Candidate state

```text
ADR-0006
ACCEPTED FOR BOUNDED G1

V5 TEXT GENERATION CAPABILITY CONTRACT
ACCEPTED FOR BOUNDED G1

ACS-ARCH-R1-V5-TEXT-GENERATION-G0
GOVERNANCE / ARCHITECTURE CHECKPOINT CANDIDATE

ACS-ARCH-R1-V5-TEXT-GENERATION-G1
AUTHORIZED AFTER G0 REMOTE VERIFICATION / NOT YET OWNER ACCEPTED

G1+
NOT AUTHORIZED
```
