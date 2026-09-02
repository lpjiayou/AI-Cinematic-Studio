# M3–M11 Upstream Execution Method Closure Contract

> Status: `ACCEPTED NORMATIVE CONTRACT / IMPLEMENTATION PENDING`
>
> Authority: [ADR-0019](../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md)
>
> Work package: `ACS-M3-M11-UPSTREAM-METHOD-CLOSURE`
>
> Effective sequence: `PR-B → PR-C → PR-D → PR-E → PR-F → FRONTEND_PIN`

## 1. Purpose and invariants

This contract defines the additive, persistence-compatible closure from an M6-bound
ScriptVersion through narrative validation, execution-method planning, media input
planning, video routing and explicit audio production. It does not make any of those
implementation stages complete merely by being Accepted.

The following invariants apply to every stage:

```text
SECOND_SCRIPT_AUTHORITY_CREATED=false
SECOND_M6_AUTHORITY_CREATED=false
SECOND_IDENTITY_AUTHORITY_CREATED=false
SECOND_SHOT_AUTHORITY_CREATED=false
SECOND_ASSET_AUTHORITY_CREATED=false
SECOND_MEDIA_QUEUE_CREATED=false
SIDECAR_DATABASE_CREATED=false
K2_HARDCODED_PRODUCTION_BRANCHES=0
```

All canonical payload digests are lowercase SHA-256 of UTF-8 canonical JSON with
sorted object keys, compact separators, no NaN/infinity and no ordinary clock fields.
Every schema is closed-world. Unknown fields, unknown enum members, duplicate refs,
cross-scope inputs, malformed digests and stale lineage fail closed before writes or
execution requests.

## 2. Ownership and persistence

| Object or behavior | Owner | Required persistence boundary |
| --- | --- | --- |
| Script / ScriptVersion / M6ConsumerBinding | M3 | existing ScriptVersion repository and SQLite `content_json`/schema projection |
| M6 Episode baseline input | M6 read boundary | existing ActiveM6BaselineReader; no copied M6 authority |
| ConsistencyValidationVersion / Finding / M8 readiness | M7 | existing Episode Production evidence journal or another already accepted single boundary |
| StoryboardVersion / CreativeShotVersion / ActionExecutionBeat | M8 | existing Episode Production evidence journal |
| Visual/Audio/Postprocess Requirement | M9 | existing Episode Production evidence journal |
| Image/conditioning input plan | M10 | existing candidate/QC/selection/admission and AssetVersion authorities |
| Video method route and job | M11 | existing MediaJobCoordinator |
| AudioGenerationRequest / AudioCue | M12 | existing audio and Episode Production authorities |
| deterministic post handoff / Timeline | M13 | existing Timeline authority under ADR-0016 |

No stage may add a database or store merely to isolate its milestone. A required new
table, marker, database, sidecar or parallel repository is a stop condition.

## 3. M6ConsumerBinding and ScriptVersion successor

The additive M3 successor schema must store exactly one server-resolved
`m6ConsumerBinding` whenever M6 influenced creation or rewrite. The binding contains:

```text
workspaceRef
projectRef
seriesRef
episodeRef
seriesPlanVersionRef
seriesPlanVersionDigest
m6BaselineSnapshotRef
m6BaselineCanonicalDigest
activationRevision
seriesBibleVersionRef
seriesBibleVersionDigest
characterContinuityVersionRef
characterContinuityVersionDigest
payloadDigest
```

The first thirteen fields are the canonical payload for `payloadDigest`. All refs are
non-empty opaque refs, every `*Digest` is a SHA-256, and `activationRevision` is a
positive integer. The binding scope must equal the Script workspace scope and the
fresh `M6EpisodeBaselineInput` scope.

Only the server may construct this object after a fresh
`get_active_episode_baseline(workspaceRef, projectRef, seriesRef, episodeRef)` read.
Create/rewrite commands recursively reject all raw binding fields. Manual or legacy
paths that are not M6-influenced retain their historical schema and semantics; an
M6-influenced path may not silently choose that legacy shape.

Existing ScriptVersion v1 records are immutable and remain readable. They are not
backfilled. A modified or rewritten Script always creates an additive successor. A
binding is current only if every scope, ref, version/digest and activation revision
equals a fresh current M5/M6 read. Otherwise its state is `STALE` or `MISMATCH`; the
historical ScriptVersion is not mutated.

## 4. M7 consistency validation

### 4.1 Version envelope

Each immutable validation version binds exactly:

```text
consistencyValidationRef
consistencyValidationVersionRef
validationVersion
workspaceRef
projectRef
seriesRef
episodeRef
scriptVersionRef
scriptVersionDigest
m6ConsumerBindingDigest
m6BaselineSnapshotRef
m6BaselineCanonicalDigest
activationRevision
seriesPlanVersionRef
seriesPlanVersionDigest
seriesBibleVersionRef
seriesBibleVersionDigest
characterContinuityVersionRef
characterContinuityVersionDigest
validationProfileRef
validationProfileVersion
validationProfileDigest
result
m8Readiness
findings[]
payloadDigest
```

`result` is `PASS|WARN|BLOCK`. `m8Readiness` is derived server-side and must equal:

| result | m8Readiness |
| --- | --- |
| `PASS` | `READY_FOR_M8` |
| `WARN` | `NOT_READY_PENDING_DISPOSITION` |
| `BLOCK` | `NOT_READY` |

No caller may submit a readiness value. No WARN waiver exists in v1.

### 4.2 Finding

Each Finding contains:

```text
findingRef
findingOrder
category
severity
sourceSpan
sourceTextDigest
ruleSourceRef
ruleSourceDigest
evidence
payloadDigest
```

The category closed set is exactly:

```text
WORLD_RULE_CONFLICT
TIMELINE_CONFLICT
LOCATION_CONFLICT
PROP_STATE_CONFLICT
CHARACTER_STATE_CONFLICT
RELATIONSHIP_CONFLICT
FORBIDDEN_BEHAVIOR
DIALOGUE_RULE_CONFLICT
UNRESOLVED_REFERENCE
SOURCE_BINDING_STALE
```

`severity` is `WARN|BLOCK`. A PASS has zero findings. A WARN has one or more WARN
findings and no BLOCK finding. A BLOCK has at least one BLOCK finding. Each finding's
source text and rule source must re-hash to their exact digest.

### 4.3 Currentness

Before create, read, replay or M8 consumption, the service re-reads the confirmed
ScriptVersion, its binding and the active M6 Episode baseline. Any drift makes the
validation `STALE`; stale state cannot authorize M8. Cross-project, cross-series,
cross-episode and foreign-workspace lookups return not-found/fail-closed semantics and
leak no existence.

Exact retry returns the existing immutable result. Same idempotency identity with a
different input digest returns conflict and creates no partial facts. Restart replay
recomputes every payload digest. M7 never writes Script or M6 facts.

## 5. Exact Script source span

M7, M8 and M9 share one server-resolved span shape:

```text
scriptSceneRef
sourceField
sourceIndex
startOffsetInclusive
endOffsetExclusive
```

`sourceField` is `ACTION|DIALOGUE|NARRATION|SUBTITLE_TEXT`. For DIALOGUE, NARRATION
and SUBTITLE_TEXT, `sourceIndex` selects the exact array item in the scene; for
ACTION it is `0`. A DIALOGUE item selects its persisted `text` field. Offsets index
Unicode code points in the selected normalized persisted string and must satisfy
`0 <= start < end <= len(text)`. The consumer stores a SHA-256 of the exact slice as
`sourceTextDigest`. It may not accept caller-provided source text as authority.

## 6. M8 action execution planning

An additive Storyboard/CreativeShot v2 contains ordered
`actionExecutionBeats[]`. Each beat contains the fields frozen in ADR-0019 and has a
canonical `payloadDigest` over all fields except itself.

The execution class is one of:

```text
STATIC_HOLD
MICRO_MOTION
CONTACT_ACTION
GAIT_LOCOMOTION
DETERMINISTIC_EVENT
```

Validation rules:

1. `beatOrder` is contiguous from 1 and `beatRef` is unique within the Shot.
2. `subjectRefs` is non-empty, normalized and duplicate-free; `targetRefs` is
   normalized and duplicate-free.
3. Every ref is resolved in current Script/M6/Shot scope; a display name is never an
   identity.
4. Every frame range is within `[0, shotFrameCount)` and start is less than end.
5. Beats for the same subject may touch but may not overlap.
6. The union of ranges covers the entire Shot; uncovered frames use explicit
   `STATIC_HOLD` beats.
7. Camera instructions remain separate shot fields and do not select an execution
   class.
8. Only `DETERMINISTIC_EVENT` has a non-empty `postprocessRequirementKey`; that class
   requires it and all other classes reject it.
9. The source span and text digest must resolve against the exact confirmed
   ScriptVersion bound by the current READY validation.

Historical v1 Storyboard/CreativeShot facts remain readable and exact-replayable but
cannot masquerade as v2 method planning.

## 7. M9 three-axis requirements

The v2 planner emits three independent ordered arrays. A requirement in any array
binds its current StoryboardVersion, CreativeShotVersion, beat ref/digest, scope and
payload digest.

### 7.1 VisualExecutionRequirement

```text
STATIC_HOLD          → STATIC_PLATE_OR_REUSE
MICRO_MOTION         → SINGLE_ANCHOR_I2V
CONTACT_ACTION       → CONTACT_CONDITIONED_VIDEO
GAIT_LOCOMOTION      → POSE_OR_TRAJECTORY_CONDITIONED_VIDEO
DETERMINISTIC_EVENT  → V3_DETERMINISTIC_COMPOSITION
```

`V3_DETERMINISTIC_COMPOSITION` produces no M11 request. `STATIC_PLATE_OR_REUSE` may
reuse an admitted plate, request a static plate or require no new asset; it never
causes unconditional video generation.

### 7.2 AudioRequirement

Audio type is `DIALOGUE|NARRATION|AMBIENCE|SFX|MUSIC|SILENCE`. DIALOGUE and
NARRATION carry an exact source span/digest. DIALOGUE also carries the server-resolved
speaker `characterRef`. Other types must not invent source text or speaker identity.
SILENCE is a positive timing requirement but creates zero generation requests.

Audio is not inferred from visual method. An explicit audio intent is required for
every non-silence request. Multiple audio requirements per Shot are permitted and
ordered deterministically.

### 7.3 PostprocessRequirement

A deterministic event creates one requirement keyed by the beat's exact
`postprocessRequirementKey`, binds event-free base media and any mask/resource/static
asset inputs, and routes only to the existing M13 deterministic-post boundary. It
never becomes a video prompt.

### 7.4 Disposition

Every requirement has exactly one disposition:

```text
REUSE_EXISTING_ASSET
GENERATE_NEW_ASSET
DERIVE_DETERMINISTIC_POSTPROCESS
CAPABILITY_UNAVAILABLE
NO_ASSET_REQUIRED
```

The disposition is a planning fact, not provider dispatch or completion. v2 creates
no request merely because a Shot exists.

## 8. M10 method-aware input plan

M10 resolves requirements through the existing AssetVersion authority and the
existing Candidate → TechnicalValidation → SemanticVisualQC → HumanSelection →
AssetAdmission chain.

| Visual method | Required usable input plan |
| --- | --- |
| `STATIC_PLATE_OR_REUSE` | current admitted plate or explicit new static-plate requirement |
| `SINGLE_ANCHOR_I2V` | one current, admitted action-ready anchor |
| `CONTACT_CONDITIONED_VIDEO` | contact-ready subject/target conditioning assets |
| `POSE_OR_TRAJECTORY_CONDITIONED_VIDEO` | pose and/or trajectory conditioning assets covering the beat |
| `V3_DETERMINISTIC_COMPOSITION` | event-free base plate plus exact mask/resource/static inputs |

Input absence is a blocker or `CAPABILITY_UNAVAILABLE`; it cannot change the method.
The generic planner has no exact-four Shot condition. Historical K2 v1 read/replay
continues unchanged.

## 9. M11 video routing

The method registry is code-defined and closed to:

```text
SINGLE_ANCHOR_I2V
CONTACT_CONDITIONED_VIDEO
POSE_OR_TRAJECTORY_CONDITIONED_VIDEO
```

The current adapter registry is:

| method | current adapter/capability |
| --- | --- |
| `SINGLE_ANCHOR_I2V` for `MICRO_MOTION` | `self-hosted-wan22-image-to-video-v1` |
| `CONTACT_CONDITIONED_VIDEO` | `CAPABILITY_UNAVAILABLE` |
| `POSE_OR_TRAJECTORY_CONDITIONED_VIDEO` | `CAPABILITY_UNAVAILABLE` |

Wan rejects CONTACT_ACTION, GAIT_LOCOMOTION and DETERMINISTIC_EVENT. STATIC_HOLD
bypasses M11. A route result never substitutes a different method. In particular:

```text
WAN_CONTACT_FALLBACK=0
WAN_GAIT_FALLBACK=0
WAN_DETERMINISTIC_EVENT_FALLBACK=0
```

Planning and routing tests must use a no-call adapter/MediaJobCoordinator and prove
GPU/provider/ComfyUI/prompt counts remain zero.

## 10. M9 to M12 bridge

M12 accepts one current M9 AudioRequirement and emits zero or one immutable typed
AudioGenerationRequest. SILENCE emits zero. Each emitted request binds:

```text
audioRequirementRef
audioRequirementDigest
scriptVersionRef
scriptVersionDigest
sourceSpan
sourceTextDigest
creativeShotVersionRef
creativeShotVersionDigest
speakerCharacterRef
audioRole
timingReference
```

Fields not applicable to a type are absent rather than fabricated. Dialogue and
Narration route only to speech/TTS semantics. Ambience and SFX route only to the
programmatic/non-speech audio capability. MUSIC returns the existing explicit
not-implemented behavior until separately implemented. Clone speech additionally
requires fresh ConsentGrantVersion, VoiceLockVersion and VoiceProfileVersion
ref/version/digest lineage.

The bridge re-reads the exact M9 requirement, ScriptVersion, CreativeShotVersion and
voice lineage before creation and before execution. Source-span, requirement,
VoiceLock or Consent drift fails closed. AudioCue binds the request/output plus a
closed timing reference suitable for M13 Timeline. No legacy sine-media write is
permitted. M11 completion is not an input precondition.

## 11. Capability projection compatibility

The Creator projection continues to accept only:

```text
available
authority_required
local_evidence_only
production_policy_required
not_open
```

Projection code must express M12 Runtime G0 incomplete, M13 base backend present,
M13 product surface incomplete and RenderCandidate availability without saying
M12/M13 production-ready. The existing Frontend adapter must parse the result without
new states. If exact truth requires a new enum or DTO schema, PR-E stops with
`CAPABILITY_PROJECTION_SCHEMA_V2_REQUIRED`.

## 12. Compatibility, replay and acceptance

Every production PR must prove focused unit, contract and integration behavior for
its exact boundary, plus SQLite restart, exact replay, changed replay conflict,
stale-input rejection and foreign-workspace not-found where applicable. Full suite is
CI-only.

PR-F adds tests/fixtures only and proves a generic non-K2 chain containing all five
execution classes. The fixture and test source must not contain `K2-001`, `K2-002`,
`EP01`, `SH12`, `裴昀`, `沈知微` or `/data/k2-technical-evidence`.

The acceptance expectations are:

```text
STATIC_HOLD → no unnecessary video request
MICRO_MOTION → SINGLE_ANCHOR_I2V selected; execution not called
CONTACT_ACTION → CONTACT_CONDITIONED_VIDEO → CAPABILITY_UNAVAILABLE
GAIT_LOCOMOTION → POSE_OR_TRAJECTORY_CONDITIONED_VIDEO → CAPABILITY_UNAVAILABLE
DETERMINISTIC_EVENT → M13 postprocess requirement; M11 request count 0
UNCONDITIONAL_AUDIO_REQUESTS=0
UNCONDITIONAL_VIDEO_REQUESTS=0
```

## 13. Runtime and publication boundary

Throughout the complete wave:

```text
A100_START_AUTHORIZED=false
GPU_OR_PROVIDER_CALLS=0
COMFYUI_START_COUNT=0
PROMPT_POST_COUNT=0
ASSET_ADMISSION=0
LIVE_CANONICAL_MUTATIONS=0
PUBLICATION_ALLOWED=false
EPISODE_MASTER_CREATED=0
EXPORT_ARTIFACT_CREATED=0
M13_EXTENSION_G0_AUTHORIZED=false
```

The next legal task after final closeout is only
`ACS-M12-C3-C4-A100-BUILD-HOST-PREFLIGHT`; this contract does not authorize that task
or start M12-C3/C4.
