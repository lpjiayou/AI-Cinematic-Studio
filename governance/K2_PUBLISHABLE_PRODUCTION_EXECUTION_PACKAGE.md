# K2 Publishable Production Execution Package

- Status: `AUTHORIZED / AUTO-SEQUENTIAL / FAIL-CLOSED`
- Date: `2026-08-17`
- Architecture decisions: `ADR-0009 + ADR-0010`
- Contract: `K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT.md`

## 1. Fixed target

Extend the existing K2 Golden Episode into one rights-cleared publishable audiovisual
master. P0 retains the current 30-second, four-shot, two-character target so live
quality and lineage can be compared with G0→G7 evidence. Any later expansion must be
a new versioned production-policy fact; it cannot silently change the target.

The `2026-08-21` read-only location audit did not find a durable instance of that
lineage on the current compute host or inside its archives. The phrase "existing K2"
therefore names the accepted logical target, not a currently recovered database.
The Project Lead explicitly authorized a new canonical bootstrap on `2026-08-21`.
ADR-0010 now governs that bounded prerequisite. It creates only a new durable
`ROOTS_READY` root and must not be represented as recovery of the missing lineage or
as satisfaction of M6, Identity Lock, P0→P1 or publication gates.

## 2. Execution order

| Gate | Work | Exit evidence |
| --- | --- | --- |
| K2 root G0 | freeze the missing-lineage decision and bounded replacement contract | ADR-0010 and contract remote-verified with no production write |
| K2 root G1 | validate and atomically establish exactly one new canonical root | private receipt/inventory, restart match, one read-only-scanned `ROOTS_READY` run and authenticated API match |
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

### K2 root G1 closeout — 2026-08-21

K2 root G1 is complete on the formal host. Implementation commit
`57ce3d0bf3e5772f57cea7a8a79726237ef366ba` was remote-verified before apply. The
operator produced exactly one durable run at `ROOTS_READY`; five SQLite databases
passed quick checks and inventory verification; the independent read-only scan found
one production database and one production run; the authenticated loopback Public API
returned exact matches for seven resources.

Bootstrap receipt SHA-256 is
`94fad69a2fdffe50e599c08fdc0e7c94aa3a381a30d1515b126a1f8b88076234`; API
verification receipt SHA-256 is
`d4c2a52d1c141ed5f0b8b24a13a985e47e38b3b78eac27eb5d59b452c18ca8a6`.
This closes only the missing-lineage prerequisite. M6 Authority, Identity Lock and
all P0→P1 authority facts remain absent.

No checkpoint may be skipped, combined by claim, or satisfied by old local evidence.
K2 root G1 is a prerequisite for the current P0→P1 work; it supplies none of P0's
external authority facts.

## 3. Hard transition rules

- P0→P1 requires valid rights-cleared inputs, accepted provider usage terms, an
  approved endpoint/credential source, an explicit cost ceiling and—when required—an
  exact authority-approved runtime-attestation ref/digest. All of these are resolved
  by external authority ports; caller-supplied claims cannot satisfy P0.
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
