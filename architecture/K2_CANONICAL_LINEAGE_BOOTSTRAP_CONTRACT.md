# K2 Canonical Lineage Bootstrap Contract

> Historical/closed as of 2026-08-25: this contract is K2-001-only evidence. Its
> original authorization text below is not current and must not initialize K2-002.

> Status: `NORMATIVE FOR ACS-K2-CANONICAL-BOOTSTRAP-G0 → G1`
>
> Scope: one new K2-001 canonical root lineage after the prior durable instance was
> not found

## 1. Authority and truth boundary

The Project Lead authorization permits creation of one new durable root lineage. It
does not recover the missing lineage and does not supply downstream M6, identity,
rights, provider, budget, approval or publication authority.

The checked-in bootstrap specification is an exact, reviewable input. Before apply,
the Operator Application must validate its schema, closed field sets, canonical
SHA-256, target duration, scene count, shot budget, human-confirmation flags and
fail-closed exit state. Validation alone performs no write.

## 2. Accepted dependency path

```text
trusted K2 Bootstrap Operator Application
→ accepted V5 public boundaries
→ lifecycle-integrity coordinator
→ V5-owned SQLite adapters
```

The bootstrap may not import `tests.*`, call V4, V3, Compute or providers, expose a
new browser/HTTP mutation, or execute SQL outside V5-owned migration/adapters.

## 3. Authoritative root graph

The single permitted graph is:

```text
WorkspaceRef (operator specification)
→ ContentProfileRef (operator specification)
→ Series
→ confirmed CreativePlan
→ Project bound to Series
→ Episode bound to CreativePlan
→ confirmed SeriesPlanVersion v2
   └── exact EpisodePlanItemBinding
→ confirmed ScriptVersion
→ EpisodeProductionRun(ROOTS_READY)
```

Every generated ref must be read from the V5 response that created it. The bootstrap
must never manufacture a ref from a title, character name, scene number, document key
or test convention.

## 4. Input contract

The bootstrap specification must contain only:

- schema/package identifiers and the explicit Project Lead authorization state;
- new opaque `workspaceRef` and `contentProfileRef` values;
- Series, Project and Episode creation payloads;
- one confirmed creative-plan source payload;
- one Series Plan candidate with one EpisodePlanItem;
- one confirmed two-scene ScriptVersion;
- `shotsPerScene=[2,2]` and a stable bootstrap idempotency key;
- the required terminal declarations:
  `ROOTS_READY / M6 NOT_CREATED / P1 NOT_PASSED /
  publicationAllowed=false`.

It must not contain provider credentials, API tokens, external audio, rights grants,
M6 approval claims, identity acceptance, live result refs or publication authority.

## 5. Filesystem and atomicity rules

The operator receives an explicit absolute canonical directory. It must:

1. reject `/`, a home directory, `/tmp`, a symlink target, an existing path or a path
   whose parent is not writable;
2. create a private staging directory next to the target so final rename stays on one
   filesystem;
3. create the lifecycle database plus the Episode Production root, evidence,
   production-policy and provider-experiment databases only inside staging; their
   relative filenames must match the existing Creator environment composition;
4. apply mode `0600` to files and `0700` to directories;
5. remove staging on any failure while leaving the absent canonical target absent;
6. restart both V5 assemblies from their database files and verify exact refs/digests;
7. run the existing read-only scanner against staging and require exactly one current
   production run;
8. write a secret-free receipt and SHA-256 inventory, fsync files/directories, then
   atomically rename staging with no-replace semantics to the canonical target;
9. reject every later apply when the canonical target already exists.

No update-in-place, overwrite, merge, partial repair or automatic retry is accepted.
The five database filenames are fixed as
`creator-workspace.sqlite3`, `episode-production.sqlite3`,
`episode-production.sqlite3.evidence.sqlite3`,
`episode-production.sqlite3.production-policy.sqlite3` and
`episode-production.sqlite3.provider-experiments.sqlite3`.

## 6. Receipt contract

The receipt is canonical JSON and contains:

- receipt schema version and bootstrap package/specification digest;
- repository commit supplied by the operator or resolved from the checkout;
- relative database filenames and their pre-receipt SHA-256 values;
- workspace/content profile and generated Project/Series/Episode refs/versions;
- confirmed CreativePlan, SeriesPlanVersion and ScriptVersion refs/versions/digests;
- EpisodeProductionRun ref/version, upstream digest, payload digest and state;
- the fixed blocker projection for M6, Identity Lock, P1 and publication.

It contains no bearer token, credential source secret, creative payload, absolute
path, hostname or provider endpoint.

The separate Public API verification receipt must bind the bootstrap-receipt digest,
specification/payload digests and repository commit to seven authenticated GET
projections: Series, Project, Episode, Series Plan workspace, Script workspace,
EpisodeProductionRun detail and EpisodeProductionRun list. The raw bearer value may
only enter through an environment variable; it must not be accepted as a command-line
argument, printed, serialized or forwarded through redirects. The API origin must be
loopback, the list must contain exactly one run, and every stable ref, version,
upstream/payload digest and fail-closed exit state must match the bootstrap receipt.
The verification receipt is stored outside the immutable canonical directory.

## 7. Verification and stop

The checkpoint passes technically only when:

- dry-run creates no path;
- missing acknowledgement and any invalid spec create no path;
- apply publishes exactly one canonical directory;
- a second apply refuses without modifying it;
- restart returns the exact same refs and digests;
- the read-only scanner reports exactly one production run;
- seven authenticated Creator Public API reads match the receipt and produce a
  secret-free verification receipt;
- targeted tests, complete Core regression, architecture/secret guards, Markdown,
  links, compile and `git diff --check` pass.

The next action is M6/Identity authority preparation. No provider dispatch is allowed
from the bootstrap checkpoint.
