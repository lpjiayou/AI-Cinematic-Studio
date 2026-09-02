# AI Cinematic Studio — Codex Agent Rules

> Status: LONG-TERM AGENT CONSTITUTION
>
> Scope: repository-wide implementation, governance and automation rules
>
> Current task authority and gates are projected by
> [CURRENT_MILESTONE.md](CURRENT_MILESTONE.md). The previous 1,909-line constitution
> is preserved byte-for-byte as
> [historical evidence](docs/archive/AGENTS_HISTORICAL_EXECUTION_RECORDS_THROUGH_2026-09-03.md);
> it is not current execution authority.

## 1. Role and authority

Codex implements the Project Lead's approved roadmap. It must not independently
change product direction, the Production Spine, architecture layers, domain
ownership, accepted contracts, UI information architecture or accepted Git
baselines.

Only the Project Lead may issue final feature acceptance, rebaseline the roadmap,
authorize a destructive migration or open an execution wave. Codex may report a
technical checkpoint or acceptance candidate, but never final `FEATURE ACCEPTED`.

An explicit Project Lead task authorization defines the bounded execution scope. It
does not silently amend an Accepted ADR or another higher-order architecture source.

## 2. Source-of-Truth hierarchy and startup

Before acting, discover and read every applicable source in this order:

1. applicable `AGENTS.override.md`;
2. nearest nested `AGENTS.md`;
3. repository-root `AGENTS.md`;
4. Accepted ADRs and mandatory governance contracts;
5. `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`;
6. `AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md` for UI, UX or Frontend scope;
7. `CURRENT_MILESTONE.md` for current scope, gates, blockers and next-task state;
8. remote-verified implementation and test evidence;
9. superseded or archived evidence, as history only.

At session start:

- clone or enter a clean checkout and run `git fetch --prune`;
- read the applicable sources;
- verify `origin/main` commit and tree, the current branch, HEAD and worktree;
- verify relevant immutable tags and open conflicting pull requests;
- audit new main-line commits before continuing from a moved baseline;
- never treat `docs/archive/**`, immutable history, a PR description or a task
  receipt as current authority.

If applicable sources genuinely conflict, stop and report the exact conflict. Do not
guess which source should win.

## 3. Product and Production Spine

AI Cinematic Studio is a Project-first production system, not a collection of
isolated AI tools. Formal production begins at:

```text
Workspace → Content Profile → Project
```

For series work, Project, Series and Episode are distinct identities. Never infer
`episodeRef == projectRef` or collapse them by title, number or display name.

The long-term Production Spine is:

```text
Workspace
→ Content Profile
→ Project
→ AI Director
→ Series
→ Series Planning
→ Series Bible / Character Intelligence
→ Episode
→ Episode CreativePlan
→ Story Projection
→ Script / ScriptVersion
→ M6ConsumerBinding
→ Consistency Validation
→ Storyboard
→ Creative Shot / ActionExecutionBeat
→ Visual / Audio / Postprocess Requirements
→ Method-aware Asset / Conditioning Plan
→ Video + Audio Production
→ Timeline
→ V3 Composition / Render
→ Preview / QC / Approval
→ Episode Master
→ Series Release & Management
→ Performance Data
→ AI Director / Content Profile Feedback
```

Every formal capability must identify its authoritative upstream, stable input,
structured output, direct downstream consumer, Ref/Version lineage and traceability.
Missing any one means integration is not complete.

Prove one real Episode vertically before scaling to 3, 10, 30 or 100. Do not build
batch infrastructure before the single-Episode chain is proven.

## 4. Single authority and layer ownership

The dependency direction is:

```text
Creator Application → V5 Core OS → V4 Platform → V3 Render Core → Compute → Foundation
```

- V5 owns authoritative production facts and the public, provider-neutral capability
  boundary.
- V4 owns provider, generation, queue, worker and compute execution; it does not own
  production facts.
- V3 owns deterministic composition and render execution; it does not redefine V5
  Shot, Timeline, identity or approval authority.
- Compute owns no business state.
- Providers produce replaceable candidates and never control lifecycle, approval,
  rights or publication.
- The separate Frontend repository owns the one customer-facing Creator UI and may
  consume only the Creator Public HTTP/API.

Do not create a second Script, M6, Identity, Shot, Asset, Timeline, Approval or media
authority. Do not create a second provider stack, queue, database, sidecar store,
registry or fact source when an accepted owner already exists.

Application code must not execute SQL or access private adapters directly. Browser
code must not access persistence, providers, V5 private interfaces, workers, GPUs or
ComfyUI.

## 5. Ref, version, lineage and currentness

Authoritative integration uses stable Refs and immutable versions, never copied text,
duplicated JSON, titles, names, episode numbers, UI labels or route strings.

When traceability is required, edits and AI rewrites create new immutable versions;
historical versions are not overwritten. Confirmation points to an immutable version.

Every downstream fact records the exact upstream Ref, version and digest that produced
it. Validation is current only for the exact input versions it validated. Any
authoritative input drift makes the old validation `STALE`; stale evidence cannot
authorize downstream readiness.

AI output is a candidate. Schema validation is not human confirmation, technical PASS
is not rights approval, consistency PASS is not publication approval, machine QC is
not human Approval, and a RenderCandidate is not an EpisodeMaster or ExportArtifact.

## 6. Persistence and lifecycle safety

Repository and service boundaries must remain portable to future production
persistence. Local SQLite is a development durable adapter, not the production
database.

Where applicable, persistence must prove transactions, rollback, restart roundtrip,
idempotency, concurrency, integrity and repository-contract parity. Reuse the accepted
persistence boundary. A new table, database or authority requires explicit scope.

Deletion must preserve downstream lineage. A UI removal is not authoritative deletion.
Objects with protected versions, assets, masters or releases must be blocked,
archived, retired or processed under an accepted lifecycle policy.

## 7. Scope and execution authorization

Implement only the current bounded task. Do not start a future milestone because it
looks useful. `AUTO-SEQUENTIAL` applies only when `CURRENT_MILESTONE.md` and the
Project Lead authorization name the exact wave and order.

An automatic transition requires the prior checkpoint's implementation, integration,
architecture, persistence/browser gates where applicable, tests, secret scan, Git
publication, remote verification and clean worktree to pass. Any unlisted next
milestone remains unauthorized.

## 8. Testing

Never delete, skip, weaken or reinterpret tests to obtain PASS.

Local execution follows changed-file scope:

- affected module only: run focused unit/contract/integration tests;
- documentation-only diff: run Markdown, documentation-link, registry, current-state
  and supersession validators only;
- shared lifecycle, production policy, cross-layer contract or migration diff: run the
  relevant contract and integration subsets;
- complete suites are CI's responsibility unless the task explicitly authorizes one
  local full run.

Real browser claims require a real browser over a real HTTP runtime. `file://`,
jsdom-only, static parsing, fabricated screenshots or reused evidence cannot satisfy a
browser gate.

## 9. PR, CI and documentation fast path

Protected changes use a pull request and the repository's authorized merge method.
Do not force push or overwrite a moved main line. Required context names are exactly:

```text
Markdown
Documentation Links
Unit Tests
Contract Tests
Integration Tests
```

Do not rename them or add a new required context without explicit governance
authorization.

The docs-only fast path applies only when every changed path is in the closed
documentation allowlist and no protected, dependency, workflow, script, test,
runtime, schema or unknown path is present. It must still execute all five required
jobs as real governance checks, while reporting:

```text
CI_SCOPE=DOCS_ONLY
FULL_SUITE_EXECUTED=false
FFMPEG_INSTALL_EXECUTED=false
```

Any mixed, protected, unknown, empty, invalid-mode or classifier/workflow change is
`FULL_SUITE`. Classification failure is fail-closed.

### CI Waiting

- For one PR head tree, start exactly one CI wait.
- Complete the wait inside one blocking tool call.
- Do not use multiple Agent turns of “query → sleep → query”.
- Emit no intermediate state while waiting.
- Do not report “4/5”, “still running” or “continue waiting”.
- Do not use a cloud browser to inspect CI.
- Do not install `gh` merely to wait for CI.
- Do not retrigger the same tree.
- Count only:
  - `Markdown`
  - `Documentation Links`
  - `Unit Tests`
  - `Contract Tests`
  - `Integration Tests`
- Ignore unrelated suites and zero-check-run empty suites.
- For duplicate check-run names on the current commit, use only the item with the
  greatest check-run ID.
- Fail fast when any required check fails, is cancelled, is timed out or is otherwise
  terminal without success.
- Maximum blocking time is 10 minutes for `DOCS_ONLY` and 60 minutes for
  `FULL_SUITE`.
- Return exactly one terminal result: `PASS`, `FAIL`, `TIMEOUT` or
  `API_ERROR`.
- A failed tree must not be rerun. Correct the cause and create a new tree first.
- When CI passes and squash merge is authorized, continue in the same Agent turn:
  wait → merge → branch cleanup → fetch main → commit/tree verification → one final
  report.

The standard-library REST waiter and exact result semantics live in
[CI_WAITING_RUNBOOK.md](docs/governance/CI_WAITING_RUNBOOK.md). Do not copy its full
implementation into this file.

## 10. Frontend/Core pin

Frontend pins an immutable, tested Core behavior commit/tree or annotated behavior
tag. Move the pin only for behavior or public-contract changes that Gate C consumes.
Documentation, comments, formatting, tests, CI or governance changes do not move it.

When a pin moves, update its controlled variables in one authorized Frontend PR,
verify the commit resolves to the declared tree and run the real cross-repository
gates. Pin compatibility does not prove every product surface exists.

## 11. Technical evidence and production authority

Gate applicability follows the state an output claims.

`TECHNICAL_EVIDENCE_ONLY / publicationAllowed=false` work that creates no
AssetVersion, Admission, Master or Export and advances no canonical state is not
blocked by production Rights/Provider/Budget bundles, canonical registration, M5
binding, asset admission, ShotPlan freeze or production graph gates.

An output intended for canonical use or publication must follow the full accepted
authority, rights, lineage, admission, QC, Approval, Master/Export and publication
chain. Historical K2 evidence never authorizes a new live mutation.

## 12. GPU, Provider, Admission and Publication boundaries

GPU use, Provider calls, model installation, A100 start, ComfyUI start, `/prompt`
submission, asset admission, live canonical mutation, Master/Export creation and
publication each require explicit current authorization. None may be inferred from a
repository implementation, technical PASS, runtime protocol, capability projection,
future task name or historical evidence.

Never expose or commit credentials, API keys, Authorization headers, private keys,
secret-bearing logs or raw provider responses containing sensitive data.

## 13. Durable GitHub continuation

GitHub remote state is the durable handoff source across sessions. Never rely on an
old sandbox path, local process, stash, uncommitted file, unpushed commit, shell
variable or conversation cache for recovery.

Before continuing remotely:

- clone or fetch with prune;
- verify main commit/tree, applicable tag object/target and open PRs;
- require a clean worktree;
- audit any main-line advance for scope conflict;
- continue from latest unrelated main changes, but stop on concurrent scope conflict.

Publish non-destructively. Never force push unless the Project Lead explicitly
authorizes it. With normal Git credentials, verify local commit SHA equals the remote
branch SHA. If an authorized repository connector reconstructs a commit and cannot
preserve local author metadata, the remote commit is canonical: verify exact parent,
tree, message and zero content diff, then record the remote SHA.

After merge, delete the task branch when the available repository interface permits
safe deletion, fetch main, verify the merge commit/tree and require a clean worktree.

## 14. Stop conditions and final report

Stop and report the exact blocker when:

- accepted sources conflict;
- main moved into the same scope;
- a new authoritative owner or persistence source is required;
- a contract, layer direction or Production Spine would be violated;
- required credentials or rights decisions are missing;
- a destructive migration or data-loss risk is ambiguous;
- a required test or CI check fails;
- the task would require an unauthorized runtime, GPU, Provider or milestone.

Final reports state the task, branch/base, implementation, upstream/input/output/
downstream lineage, test and CI results, commit/PR/merge/tree, local/remote equality,
worktree status, remaining gaps and next authorized task. Never upgrade repository
evidence into product, production or publication completion.
