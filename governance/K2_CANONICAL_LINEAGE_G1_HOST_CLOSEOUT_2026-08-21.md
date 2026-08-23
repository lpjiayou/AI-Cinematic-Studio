# K2 Canonical Lineage G1 Formal Host Closeout

> Status: `COMPLETE / HOST-VERIFIED / NOT FEATURE ACCEPTANCE`
>
> Evidence time: `2026-08-21T15:24:43Z`
>
> Scope: one newly bootstrapped K2-001 canonical lineage; this is not recovery of
> the missing historical lineage.

## 1. Fixed implementation

- branch: `feature/k2-publishable-production`;
- PR: `#9`;
- implementation commit:
  `57ce3d0bf3e5772f57cea7a8a79726237ef366ba`;
- implementation tree:
  `a3eece796fafcaeead8b525cbe039a69782602c3`;
- Repository Validation: run `#44`, all five jobs successful;
- specification SHA-256:
  `3b4d77b371cb23e2acf5420d74ded9d890a877f9555d781bc7842d0b715eb0ee`;
- specification payload SHA-256:
  `0dfa64aa23e7120415a58b48eb00bb5d92274518d16051f2cb419525ea3b364c`.

The formal host fast-forwarded to the exact implementation commit before dry-run or
apply. The worktree was clean. The write-free validation passed before the single
acknowledged apply.

## 2. Formal host evidence

| Evidence | SHA-256 / result |
| --- | --- |
| dry-run transcript | `fee8612a2208ddcedddcc99904a52e20635fb4369f2c2ced8f7e7c8c30c80d1c` |
| apply transcript | `c623f8572a8776671789c32f7a02fcfaa43c30a716cbc80c919dd4b217dfcc44` |
| secret-free bootstrap receipt | `94fad69a2fdffe50e599c08fdc0e7c94aa3a381a30d1515b126a1f8b88076234` |
| relative database inventory | `b3c7f0e146c3a994171325f773b1b9d53ac6c6613abe5675ee5252863484ba38` |
| independent read-only scan transcript | `9f7b38b453de739557fd18fa50a6977cc156895e119a155ca4649b46fdb8e2c7` |
| authenticated API verification receipt | `d4c2a52d1c141ed5f0b8b24a13a985e47e38b3b78eac27eb5d59b452c18ca8a6` |
| database inventory verification | all six inventoried files `OK` |
| SQLite quick checks | five databases `ok` |
| read-only scanner counts | five databases, one production database, one production run |
| authenticated Public API exact-match | seven resources, `PASS` |

The transcripts and receipts remain in the operator-controlled evidence directory.
They are represented here only by secret-free hashes and non-sensitive results; the
databases, creative payloads, bearer credential and host logs are not committed.

## 3. Canonical lineage facts

| Fact | Exact value |
| --- | --- |
| Workspace | `workspace-6c2c70926cf64cd68435537ffd4de92d` |
| Project | `project-00482509a3a14837be7f29f1467c0ced` |
| Series | `series-c0a74d5580b44aeea75747ad1d33438a` |
| Episode | `episode-cdca5216389242cb92ccbc638f57eec7` |
| EpisodeProductionRun | `episode-production-run-f918dc281320440b9848bcb476f5605a` |
| production-run upstream digest | `964aea6b8893593a7b706f006e615678e99097568c8609b859dda61f0b5fbcd2` |
| production-run payload digest | `cf372747b4047e098c693da836c38e019d38fefb2791f173a0c8981c2e21030e` |

The independent scanner found exactly one production run. The authenticated Creator
Public API returned exact matches for Series, Project, Episode, Series Plan workspace,
Script workspace, production-run detail and production-run list. The verifier also
revalidated the checked-in specification, repository revision, root permissions,
database hashes, receipt inventory, scene/shot counts, digests and single-run
cardinality.

## 4. Exit state and hard boundary

```text
K2_CANONICAL_ROOT_STATUS=ROOTS_READY
M6_AUTHORITY_STATUS=NOT_CREATED
IDENTITY_LOCK_STATUS=NOT_CREATED
P1_GATE=NOT_PASSED
PUBLICATION_ALLOWED=false
```

Canonical G1 is complete. This result establishes the durable root required by the
downstream contract, but supplies none of M6 Authority, Identity Lock, external
Rights/Provider/budget authority, provider execution, asset admission, human approval,
master/export or publication eligibility.

The next valid transition is the existing same-lineage G2 operation: independently
append one M6 Authority decision and one V5 Identity Lock after exact source/reference
authority is available. No P1 provider dispatch may occur before those facts and P0's
external authority decisions pass fail-closed validation.

## 5. Repository closeout verification

The evidence-only closeout patch passed:

- canonical bootstrap/API focused tests: `18 / 18`;
- complete Core regression: `587 / 587`;
- Python compileall for `apps`, `services`, `scripts` and `tests`;
- tracked Markdown validation: `116` files;
- local documentation links: `343` links;
- staged diff whitespace validation.

No production database, host transcript, creative payload or credential is part of
the repository patch.
