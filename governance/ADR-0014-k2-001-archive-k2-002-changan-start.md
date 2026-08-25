# ADR-0014 — Archive K2-001 and Start K2-002-CHANGAN

- Status: `ACCEPTED / OWNER AUTHORIZED / NON-GPU PREPRODUCTION ACTIVE`
- Date: `2026-08-25`
- Decision owner: Project Lead / Architecture Owner `蔺鹏`
- Supersedes as current project: K2-001 production execution
- Preserves: K2-001 immutable history, ADR-0013 control-plane authority,
  fail-closed selection/admission/publication rules
- Production Ready: `NO`
- Publication allowed: `false`

## Context

K2-001 completed its bounded validation role. Its current M11 v1 video set failed
semantic visual QC, and neither that set nor the Shot 01 R2–R7 calibration candidates
is eligible for further production. The four admitted M10 v1 images remain historical
facts, not current action-ready inputs. The next Internal Content Lab validation
project is `K2-002-CHANGAN` / 《长安刮痕》, planned as 30 episodes of
approximately 30 seconds. The reviewed source package covers the series bible,
30-episode outline and reviewed editorial plans for EP01–EP03; those plans are not
yet an `ExecutableShotGraph`.

The existing K2-001 bootstrap and media-planning packages are exact-scope historical
tools. Reusing them would either invent K2-001 refs or create a second canonical
database island. K2-002 must enter through the existing Public API and the single
V5/V4 production spine.

## Decision

1. K2-001 is frozen as historical validation evidence and is closed for further
   production.
2. K2-002-CHANGAN is the active project, but initially only EP01 is active;
   `bulkGenerationAllowed=false`.
3. The uploaded v1.2 byte stream digest is
   `8dec72d6bde85768c846ec93dd7f06adfa1f5dd9bcddb0f118455b2f9abe37de`.
   The repository preserves its LF-normalized UTF-8 text at digest
   `7773438973da8fa0b0bd5e51d7adac542cdadf273c4eaf1cc5afcc5504d87f8b`;
   both values are recorded so line-ending normalization is not mistaken for an
   identical byte copy.
   The corrected repository review candidate is v1.3; final script acceptance remains
   a separate Project Lead decision.
4. Human-authored content may enter Script Studio only as an unconfirmed reviewed
   import; it must not be mislabeled as AI generation. The current route records an
   authenticated actor's three external digest assertions and a server-computed
   canonical Script-content digest, but it does not independently receive/re-hash the
   source documents or prove their semantic binding. Generic confirmation is therefore
   blocked for the complete reviewed-import lineage until a trusted Owner approval
   resolver is implemented.
5. Project registration must be idempotent and package-digest pinned. Replay with
   identical facts returns existing refs; a changed payload conflicts and fails
   closed.
6. K2-002 uses a vertical production profile with separate generation, edit and
   delivery canvases. `704×1280` is not mislabeled as strict 9:16.
7. EP01 carries an explicit 12-shot local structural representation. It is not an
   approved ShotPlan and has no accepted ShotPlan ref/version/digest/approval lineage.
   Contract validation may preserve durations, visible-identity modes, dialogue-sync
   modes and deterministic-postprocess requirements instead of inventing even shot
   splits, but camera facts remain `NOT_READY` and synthetic test cameras must never be
   promoted into production authority.
8. Media candidates must continue through the accepted ADR-0013 chain. Provider
   experiment results remain preflight evidence and cannot be promoted directly.
9. Missing reference images, scene masters, glyph masks and postprocess inputs are
   registered as requirements, not fabricated AssetVersions.
10. No GPU dispatch occurs until the exact EP01 Project/Series/Episode/Plan/Script,
    Script Owner acceptance, approved ShotPlan/camera lineage, M6 scope,
    identity/reference and rights authorities, provider policy, budget authority,
    production profile, runtime capability and artifact inputs are independently
    current and digest-pinned.

The conditions in decision 10 are necessary gates, not a standing GPU authorization.
This accepted wave is non-GPU only; any Provider/GPU dispatch requires a separate
Project Lead authorization after every prerequisite is independently verified.

## Initial status

```text
PROJECT_KEY=K2-002-CHANGAN
SOURCE_PACKAGE=V1.3_REVIEWED_CORRECTION_CANDIDATE
SCRIPT_OWNER_ACCEPTANCE=PENDING
ACTIVE_EPISODE_SET=EP01
EDITORIAL_SHOT_PLAN=LOCAL_STRUCTURAL_REPRESENTATION_ONLY
SHOT_PLAN_APPROVAL=NOT_VERIFIED
EXECUTABLE_SHOT_GRAPH=NOT_COMPILED
REFERENCE_ASSETS=MISSING
PRODUCTION_ASSETS=NOT_ADMITTED
GPU_DISPATCH=NOT_STARTED
BULK_GENERATION_ALLOWED=false
PUBLICATION_ALLOWED=false
PRODUCTION_READY=NO
```

## Consequences

The highest truthful repository state before real assets and a live host apply is
`SOURCE PACKAGE REVIEWED / OWNER ACCEPTANCE PENDING / NON-GPU CHAIN CORRECTION IN
PROGRESS`. Repository tests
or fake-adapter evidence cannot be reported as generated K2-002 media.
