# ACS-CCV-R2 G0 Reproducible Experiment Design

## 1. Record

| Field | Value |
| --- | --- |
| Task | `ACS-CCV-R2-G0-REPRODUCIBLE-EXPERIMENT-DESIGN` |
| Date | `2026-08-15` |
| Decision | `OWNER AUTHORIZED / DESIGN AUTHORING ACTIVE` |
| Execution mode | `GOVERNANCE + DESIGN / NO GPU / FAIL-CLOSED` |
| Remote parent | `4132458d7f92e02dbd2e4be93476294aab825db6` |
| Parent decision | `G2-R1 INDEPENDENT REVIEW PASS / CLOSED` |
| PR | `#7 / DRAFT` |
| Production Ready | `NO` |

G2-R1 preserved and independently verified the available historical custody, but its
manifest remains `EVIDENCE_CAPTURE_PARTIAL_NOT_VALIDATION_ACCEPTED`. CCV-R2 must
therefore be a new forward-looking controlled experiment. It must not be described as
a reconstruction or validation of unavailable historical usage.

The Project Lead authorizes G0 only to freeze a reproducible experiment design before
any execution authority exists.

## 2. G0 objective

G0 must produce an independently reviewable protocol that makes every later CCV-R2
run attributable to exact inputs, versions, parameters, environment observations,
outputs and review decisions.

The design must answer, before execution:

1. which Character Consistency claims are being tested;
2. which model and workflow arms are compared;
3. which identity references and shot/pose inputs are used;
4. how seeds, repetitions and run identifiers are frozen;
5. which primary metrics and acceptance thresholds decide the result;
6. how blind review, failures, exclusions and retries are recorded;
7. how all source and output bytes are retained and reverified;
8. which rights, licenses and usage constraints apply.

## 3. Authorized design work

G0 may:

- read repository governance, the sanitized G2-R1 review package and registered
  evidence metadata;
- inspect existing experiment scripts and workflows without executing them;
- author the CCV-R2 experimental protocol and non-executable JSON templates;
- define fixed sample, arm, seed, repetition and run-register rules;
- define model/workflow/environment pinning and digest requirements;
- define objective and human-review metrics, thresholds and blind-review procedure;
- define a normalized failure ledger, exclusion policy and retry policy;
- define custody, archive, reattach and independent-review requirements;
- run text, JSON, schema and static no-GPU validation of G0 documents.

G0 may not start ComfyUI, a worker, model server, generation script or GPU job.

## 4. Required G0 design outputs

The G0 authoring checkpoint may add or update only:

```text
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
governance/ACS-CCV-R2-G0-REPRODUCIBLE-EXPERIMENT-DESIGN.md
experiments/ccv-r2/experiment-design.md
experiments/ccv-r2/experiment-manifest.template.json
experiments/ccv-r2/run-register.template.json
experiments/ccv-r2/review-rubric.template.json
experiments/ccv-r2/failure-ledger.template.json
```

The current activation checkpoint changes only the first five paths. The five
`experiments/ccv-r2/` design artifacts remain G0 authoring deliverables and are not
created or accepted by this authorization commit.

No generated image, model byte, archive, credential, raw provider log or secret may
enter Git.

## 5. Mandatory protocol fields

The experiment design must freeze:

- experiment and protocol version;
- hypothesis, primary endpoint and secondary endpoints;
- exact arm names and permitted comparisons;
- rights-cleared or explicitly `SYNTHETIC_TEST_ONLY` inputs;
- input path, size and SHA-256;
- model source, license state, file size, SHA-256 and architecture metadata;
- ComfyUI and Custom Node commits;
- complete workflow/API JSON bytes and SHA-256;
- sampler, scheduler, steps, CFG, dimensions, denoise and all adapter/control weights;
- integer seed values, seed allocation and repetition count;
- immutable run IDs and expected output names;
- capture-time GPU, driver, CUDA, Python and PyTorch observations;
- output size, SHA-256 and embedded prompt/workflow metadata;
- metric implementation, threshold, reviewer blinding and adjudication;
- failure event IDs, stage, reason, retry relation and terminal disposition;
- source inventory, custody inventory, deterministic archive and reattach check.

A path, version, seed, license, lineage or usage link that cannot be proved must stay
explicitly unavailable. Narrative memory may not fill it.

## 6. Model admission rule

The separately downloaded
`/data/coding/apps/ComfyUI/models/diffusion_models/z_image_turbo_bf16.safetensors`
is outside G2-R1 and is not automatically admitted to CCV-R2.

If proposed for an R2 arm, G0 must first register its authoritative source, retrieval
receipt, license or usage restriction, byte size, SHA-256, safetensors header metadata,
architecture compatibility and exact workflow dependency. Registration in a design
does not authorize loading or executing the model.

## 7. Evaluation boundary

G0 must distinguish:

- byte-level reproducibility;
- workflow and parameter reproducibility;
- deterministic repeatability where technically expected;
- statistical quality evaluation where outputs are not byte deterministic;
- identity consistency;
- pose/shot adherence;
- visual defect and contamination rates;
- operational failure and retry behavior.

No single subjective score may silently replace the declared primary endpoint.
Acceptance thresholds must be frozen before GPU execution.

## 8. Fail-closed gates

G0 is not complete unless independent review confirms:

1. the research claims are bounded and falsifiable;
2. every arm, input, model, workflow and parameter field is explicit;
3. run count, seed allocation and expected output count reconcile exactly;
4. rights and license states are explicit;
5. missing or ambiguous facts cannot validate;
6. failed and excluded runs remain in the failure ledger;
7. output digest fields are null when an output is unavailable;
8. custody and persistence can be repeated on a later instance;
9. product, schema, migration and production paths have zero diff;
10. the protocol contains no execution authority.

## 9. Explicit prohibitions

G0 does not authorize:

- GPU execution or generation;
- model download, installation, conversion or repair;
- product, Domain, Application, HTTP/API or external DTO change;
- Character Visual Identity schema or ADR implementation;
- SQL/DDL/Migration or persistence implementation;
- M6/M8/M10 production work;
- Frontend, Auth/RBAC, Worker or production ComfyUI integration;
- merge, release, deployment, tag or Production Ready.

## 10. Stop state

After the design artifacts and static validations are complete:

```text
ACS-CCV-R2-G0 DESIGN CHECKPOINT CANDIDATE
INDEPENDENT G0 REVIEW REQUIRED
NO GPU EXECUTION
NO CCV-R2-G1 AUTHORITY
NO PRODUCT / SCHEMA / PRODUCTION AUTHORITY
PRODUCTION READY: NO
```

Only an independent G0 `PASS` plus a separate Project Lead authorization may open a
later execution-preparation gate. G0 itself can never authorize a GPU run.
