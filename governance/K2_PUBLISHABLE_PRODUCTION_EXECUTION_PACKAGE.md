# K2 Publishable Production Execution Package

- Status: `AUTHORIZED / AUTO-SEQUENTIAL / FAIL-CLOSED`
- Date: `2026-08-17`
- Architecture decision: `ADR-0009`
- Contract: `K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT.md`

## 1. Fixed target

Extend the existing K2 Golden Episode into one rights-cleared publishable audiovisual
master. P0 retains the current 30-second, four-shot, two-character target so live
quality and lineage can be compared with G0→G7 evidence. Any later expansion must be
a new versioned production-policy fact; it cannot silently change the target.

## 2. Execution order

| Gate | Work | Exit evidence |
| --- | --- | --- |
| P0 | target, rights, production and provider-policy contracts; capability probe | immutable policy facts, validation and fail-closed tests |
| P1 | rights-cleared provider/GPU experiments via V4 | real attempts/artifacts, provenance, cost, latency and runtime facts |
| P2 | durable DB/job state, object store, secrets, observability and recovery | restart/isolation/idempotency/failure-injection tests |
| P3 | K2 M7 narrative closure, M8 Shot Graph and M9 requirements | exact current refs and complete requirement coverage |
| P4 | M10 still/reference generation and selection | validated selected image AssetVersions |
| P5 | M11 shot video generation and selection | validated selected video AssetVersions |
| P6 | M12 voice, dialogue, ambience, effects and music | validated selected audio AssetVersions/stems |
| P7 | M13 timeline, composition and preview | deterministic verified A/V preview |
| P8 | M14 QC, local regeneration and decisions | machine report plus separate exact-version human decisions |
| P9 | M15 master/export and release eligibility | immutable master and truthful eligibility result |
| A/B/C | contracts, integration, security, browser workflow and evidence audit | same-tree pass with no secret or lineage leak |
| P10 | M16 runs at 1, 3, 10 and 30 | per-size quality, cost, throughput and recovery evidence |

No checkpoint may be skipped, combined by claim, or satisfied by old local evidence.

## 3. Hard transition rules

- P0→P1 requires valid rights-cleared inputs, accepted provider usage terms, an
  approved endpoint/credential source and an explicit cost ceiling. All of these are
  resolved by external authority ports; caller-supplied claims cannot satisfy P0.
- P1→P2 requires at least one real image, video and audio attempt or a documented
  blocked media type; a blocked type prevents downstream publication.
- P2→P3 requires durable recovery and isolation evidence.
- P3→P4 requires a current Shot Graph and complete requirements.
- P4→P7 requires selected, immutable, validated assets; candidates alone do not pass.
- P7→P8 requires a verified playable preview.
- P8→P9 requires separate human decision facts; machine QC cannot supply them.
- P9→P10 requires publication eligibility and Gate A/B/C over the same tree and exact
  master lineage.
- Every P10 size must pass before the next size begins.

## 4. Stop conditions

Stop automatic progression and record the blocker when:

- source/reference rights or provider-processing consent are absent or ambiguous;
- endpoint, credential, GPU, budget, region or usage terms are unavailable;
- an action requires destructive migration, secret exposure or unapproved retention;
- a provider output fails probe, policy, safety, moderation, identity or rights checks;
- lineage is missing, stale, foreign-workspace, duplicated or reconstructed by name;
- required human approval or publication authority is not supplied;
- browser, security, integration, recovery or remote-verification gates fail;
- the change would introduce a direct Frontend/Application→provider/V4/V3 dependency.

The implementation may continue on independent safe prerequisites, but the blocked
gate remains blocked and no downstream production claim is allowed.

## 5. Evidence and git closeout

Each checkpoint records tests, artifact digests, provider/runtime facts where
applicable, local commit, fetched remote commit/tree, ahead/behind and clean worktree.
No force push, rewritten evidence, credential fixture, untracked acceptance artifact
or automatic `FEATURE ACCEPTED` statement is permitted.

## 6. Explicit non-scope

- a second frontend or provider-specific production UI;
- direct provider/worker/GPU calls outside V4;
- automatic generation of rights or human approval records;
- 100-run M16 scale;
- M17 release automation, M18 feedback learning or M19 SaaS hardening;
- deployment to a real publication destination without separate destination authority.
