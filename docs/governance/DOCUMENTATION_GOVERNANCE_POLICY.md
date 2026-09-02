# Documentation Governance Policy

Status: `ACTIVE`

Owner: `Project Lead / Architecture Owner / Documentation Governance Owner`

Reviewed baseline: Core `a455c8e76427d53d75bb7f15259b9875d9768914`,
tree `d92159d5c3c5d3896d1fe9e56b896413277fe4e8`, on `2026-09-02`.

## 1. Purpose

This policy governs every version-controlled document in the Core repository. It
separates current authority from plans, operational guidance, generated reference and
immutable evidence so that a historical statement cannot silently become current
execution authority.

The machine-readable inventory is
[`DOCUMENT_REGISTRY.json`](DOCUMENT_REGISTRY.json). The human-readable projection is
[`DOCUMENT_AUTHORITY_MAP.md`](DOCUMENT_AUTHORITY_MAP.md), and the complete navigation
index is [`../README.md`](../README.md).

## 2. Existing authority order

This policy records, but does not replace, the authority order already established by
[`AGENTS.md`](../../AGENTS.md),
[`ARCHITECTURE_CHANGE_PROCESS.md`](../../governance/ARCHITECTURE_CHANGE_PROCESS.md),
the Accepted ADRs, the System Master Plan, the UI Master Plan and the current-state
projection.

When two statements appear inconsistent, apply this order:

1. an explicit Project Lead task authorization for the bounded task being executed;
2. the nearest applicable `AGENTS.md`, then the repository-root `AGENTS.md`;
3. Accepted ADRs and mandatory governance contracts;
4. the System Master Plan and UI Master Plan within their declared scopes;
5. Golden and other normative contracts within their declared scopes;
6. `CURRENT_MILESTONE.md` for current baseline, authorization, blocker and next-task
   projection only;
7. implementation evidence, test evidence and task receipts as proof of what happened;
8. historical snapshots as immutable context only.

The higher item wins only inside its own scope. An implementation receipt cannot make
an architectural decision, and a current-state projection cannot amend an Accepted
ADR.

The following invariants are explicit:

```text
HISTORICAL_DOCUMENT_GRANTS_CURRENT_AUTHORITY=false
PR_DESCRIPTION_OVERRIDES_ACCEPTED_ADR=false
CURRENT_MILESTONE_OVERRIDES_ACCEPTED_ADR=false
TASK_RECEIPT_CREATES_ARCHITECTURE_AUTHORITY=false
```

If two Accepted ADRs make genuinely incompatible demands for the same current
behavior, ordinary documentation work must stop with
`ACCEPTED_ARCHITECTURE_DOCUMENT_CONFLICT`. Only the established architecture-change
process may resolve that conflict.

## 3. Authority scopes

| Source | What it may govern | What it cannot do |
| --- | --- | --- |
| Accepted ADR | Durable architecture decision and explicit scope/amendment relationship | Claim implementation, runtime or production completion without evidence |
| System Master Plan | Product architecture, milestone intent and system boundaries | Override an Accepted ADR or independently authorize execution |
| UI Master Plan | Experience architecture and product-surface intent | Override Core authority, Accepted ADRs or current runtime truth |
| Golden or normative contract | Exact interface, lineage, invariant or operator boundary in its declared scope | Broaden itself beyond that scope or convert evidence into publication authority |
| `CURRENT_MILESTONE.md` | Concise current baselines, behavior tag, high-level M1–M19 state, current authorization, blockers, next legal task and prohibitions | Amend architecture or preserve an ever-growing execution diary |
| PR description | Explain a proposed diff and its document impact | Become architecture or current-state authority by itself |
| Tests and receipts | Prove a bounded execution or verification result | Grant provider, GPU, production, approval or publication authority |
| Historical snapshot | Preserve what was believed, attempted or observed at a stated time | Authorize current execution or override later accepted decisions |

Machine QC is not human approval. A `RenderCandidate` is not an `EpisodeMaster` or an
`ExportArtifact`. Technical evidence is not live-production authority.

## 4. Document classes

Every governed document has exactly one primary `documentClass`:

| Class | Meaning | Current-state claims |
| --- | --- | --- |
| `ACCEPTED_DECISION` | Accepted architecture decision | Only the durable decision and its explicit scope |
| `NORMATIVE_ARCHITECTURE` | Current architecture description subordinate to Accepted ADRs | Architecture statements, not execution completion |
| `NORMATIVE_CONTRACT` | Current interface, governance or data contract | Contract statements, not runtime completion |
| `CURRENT_STATUS` | Current baseline/authorization/blocker projection | Allowed and must be evidence-backed |
| `CAPABILITY_MATRIX` | Dimensioned current capability projection | Allowed and must be evidence-backed |
| `OPERATIONAL_RUNBOOK` | Reproducible operator procedure | Preconditions and steps, not completion unless recorded separately |
| `IMPLEMENTATION_EVIDENCE` | Bounded implementation/test evidence | Historical result only |
| `HISTORICAL_EVIDENCE` | Immutable historical snapshot | Never |
| `SUPERSEDED` | Replaced document retained for traceability | Never |
| `DRAFT` | Proposal or incomplete template | Never |
| `DEPRECATED` | Retained but unsupported material | Never |
| `GENERATED_REFERENCE` | Index, generated manifest or navigation aid | Never independently |

`DOCUMENT_CLASS=UNKNOWN` is forbidden. A secondary characteristic belongs in `notes`;
it must not create a second primary class.

## 5. Registry requirements

Each registry record contains:

- `path` and `repository`;
- exactly one `documentClass` and one `status`;
- accountable `owner`;
- `authoritativeFor`, `supersedes` and `supersededBy` arrays;
- `currentStateClaimsAllowed`;
- `historicalMutationPolicy`;
- `lastReviewedBaseline` and `lastReviewedAt`;
- `linkedFromIndex`;
- explanatory `notes`.

The registry covers all tracked Markdown, MDX and RST files, documentary text files,
documentary manifests, repository guidance, PR/issue templates and the registry
itself. Generated media, dependencies, build output, caches, model files and test
output are outside this inventory.

## 6. Current and historical mutation rules

Accepted decisions are amended or superseded only through the architecture-change
process. Historical and implementation evidence is immutable except for metadata,
link repair or an explicit non-semantic supersession annotation. A correction must be
additive and must not turn a failure into a pass.

Historical paths may remain truthful evidence. Their registry note must include:

```text
HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true
```

Current normative documents and runbooks must not depend on `sandbox:/workspace`, a
temporary agent directory, another conversation sandbox, or an undeclared local
absolute path. Declared runtime roots and loopback defaults are permitted only when
their portability and configuration boundary are explicit.

## 7. Supersession

Supersession is directional and explicit:

- a `SUPERSEDED` record has at least one `supersededBy` path;
- the successor lists the predecessor in `supersedes` when the replacement is total;
- a scope-limited amendment is recorded in both records' notes without pretending the
  older historical decision disappeared;
- versioned evidence remains readable and is never overwritten in place.

The consolidated graph is published in
[`DOCUMENT_SUPERSESSION_MAP.md`](DOCUMENT_SUPERSESSION_MAP.md). The registry remains
the machine-readable source for known relationships.

## 8. Pull-request document impact

Each pull request declares one of:

```text
DOC_IMPACT=NONE|STATUS|PUBLIC_CONTRACT|ARCHITECTURE|RUNTIME
```

It also declares required/updated files, whether `CURRENT_MILESTONE.md`, a public
contract, ADR, risk register or Frontend pin is affected. A work-in-progress push must
not predeclare a formal `PASS`; formal status changes require merge plus required-check
success.

Pure documentation work must use the repository's bounded Markdown and link checks.
It must not mechanically touch every document, rewrite evidence, move behavior tags or
change a Frontend pin for an internal implementation detail.

## 9. Frozen baseline invariants

This governance wave begins from:

```text
CORE_MAIN=a455c8e76427d53d75bb7f15259b9875d9768914
CORE_TREE=d92159d5c3c5d3896d1fe9e56b896413277fe4e8
M13_BASE_TAG=m13-base-backend-v1
M13_BASE_TAG_OBJECT=b2d086b622bdb5456f6af325e458aa3771e43e80
M13_BASE_TAG_TARGET=a455c8e76427d53d75bb7f15259b9875d9768914
FRONTEND_MAIN=a0be9edc91437bf0e7c5dd14883e656e750b3aee
FRONTEND_TREE=c25b9e3744d561c93fed26d0a07e59a1915a6071
```

Documentation commits may advance `main`, but the annotated behavior tag is immutable.
This wave does not authorize A100, M12-C3/C4, M13 Extension G0, a provider, GPU,
admission, Master/Export or publication.
