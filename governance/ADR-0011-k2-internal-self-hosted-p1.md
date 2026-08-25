# ADR-0011 — K2 Internal Self-hosted P1 Execution Rebaseline

- Status: `ACCEPTED / K2-001 HISTORICAL VALIDATION / HOST-VERIFIED FOR THE EXACT ARCHIVED RUN / NOT TRANSFERABLE TO K2-002`
- Date: `2026-08-22`
- Decision owner: Project Lead / Architecture Owner `蔺鹏`
- Supersedes: `ADR-0009` only for the exact K2 Internal Content Lab P1 scope
- Preserves: `ADR-0009` for commercial/publication execution
- Contract: `architecture/K2_INTERNAL_SELF_HOSTED_P1_CONTRACT.md`

> 2026-08-25 archive note: this decision and its internal self-hosted exception are
> closed as validation history for the exact K2-001 `workspaceRef` and
> `productionRunRef`. They do not authorize K2-002, do not admit any K2-001 media,
> and do not change `publicationAllowed=false`. The current transition is recorded
> by ADR-0014 and the ADR-0013 main closeout.

## Historical decision-time context

The canonical K2-001 run has advanced through same-lineage G2–G6 host execution.
The latest reported facts are:

- G4 resolved 18 requirements and created eight generation requests;
- G5 registered four MP4 and four WAV `LOCAL_EVIDENCE` AssetVersions;
- G6 created one preview candidate and machine QC passed all six checks;
- the preview remains `UNAPPROVED`;
- no Episode Master or export artifact exists;
- P1 is not passed and publication is disabled;
- no provider-experiment candidate exists for the current run.

The previous publishable-production contract made external Rights Evidence,
Provider Policy, credential/usage terms and Budget Authority prerequisites for any
P1 provider dispatch.  That contract models a Commercial SaaS/publication boundary.
It is not the correct blocking boundary for the K2 Internal Content Lab using an
operator-controlled self-hosted ComfyUI/Wan2.2 runtime.

The repository already contains the required production path: Public API → V5
current asset lineage → V4 MediaJob/Attempt → ComfyUI/Wan2.2 → independently probed
candidate.  A second execution stack, a direct ComfyUI script or a new frontend is
therefore unnecessary and would create an island.

## Decision

1. K2 P1 gains one explicit `INTERNAL_SELF_HOSTED` execution mode.  It is enabled
   only by server-held configuration and is bound to one exact `workspaceRef` and
   one exact `productionRunRef`.
2. In this exact internal mode, `RightsManifest`, `ProviderExecutionPolicy`,
   `providerCapabilityRef`, credential-source approval, usage-terms approval and
   `budgetAuthorityRef` are not P1 prerequisites.  They must not be synthesized,
   copied into the internal request or stored on the internal candidate.
3. This exception does not apply to the commercial/publication path.  When the exact
   internal grant is absent or the requested run does not match it, the existing
   external-authority path remains unchanged and fail-closed.
4. The browser supplies only an idempotency key and one existing current video
   `sourceGenerationRequestRef`.  Workspace/run scope is injected by the authenticated
   server.  Provider/model/runtime configuration comes only from the validated V4
   adapter; browser-supplied provider selection is rejected.
5. V5 must re-read the current G4 asset plan and bind the smoke request to the exact
   source GenerationRequest, AssetRequirement and CreativeShotVersion.  No direct SQL,
   detached experiment table or raw ComfyUI call is allowed.
6. V4 remains responsible for MediaJob, lease, Attempt, artifact containment and
   execution.  The existing ComfyUI/Wan2.2 adapter remains responsible for workflow
   construction and provider transport.
7. Technical controls remain mandatory: exact runtime-attestation ref/digest, exact
   configured model identities and file digests, one CUDA device, GPU-used evidence,
   bounded timeout/cost, artifact SHA-256, independent media probe and request/result
   lineage verification.
8. K2 P1 passes when one current same-lineage 49-frame internal video smoke candidate
   is technically verified.  Image and audio provider experiments are not P1 blockers
   for this internal checkpoint.
9. A P1 candidate remains `UNSELECTED`, `NOT_ADMITTED` and experiment-only.  It does
   not replace the G5 local-evidence AssetVersion, create a Master, satisfy human
   approval or authorize publication.
10. `publicationAllowed=false` is invariant.  Commercial publication, external
    distribution and release remain outside this decision.
11. Frontend/G7 work is not a prerequisite for P1.  The existing authenticated Public
    API is the only application entrypoint for this checkpoint.

## Required sequence

```text
exact K2 workspace/run grant configured server-side
→ existing G4 video GenerationRequest selected
→ authenticated Public API command
→ V5 current-lineage verification
→ V4 MediaJob + Attempt
→ self-hosted ComfyUI/Wan2.2 GPU execution
→ artifact containment + SHA-256 + media probe + attestation verification
→ unselected internal candidate persisted
→ P1 PASSED_INTERNAL_VIDEO_EXECUTION
→ STOP before selection/admission/P2/publication
```

## Rejected alternatives

- **Delete the commercial policy models globally:** rejected because it would weaken
  the separate Commercial SaaS/publication boundary.
- **Insert a fake approved policy/rights/budget bundle:** rejected because it would
  fabricate authority facts.
- **Call ComfyUI directly from an operator shell:** rejected because it loses the
  current V5/V4 lineage and creates detached evidence.
- **Modify canonical SQLite directly:** rejected because it bypasses Core ownership,
  validation and idempotency.
- **Clone or repair the frontend before P1:** rejected because the accepted Public API
  and production boundaries already exist and frontend is not on the execution path.
- **Auto-admit the successful smoke as a formal AssetVersion:** rejected because
  provider execution success is not an asset selection/admission decision.

## Authorized exit state

The P1 checkpoint may report only:

```text
K2_P1_EXECUTION_MODE=INTERNAL_SELF_HOSTED
K2_P1_STATE=PASSED_INTERNAL_VIDEO_EXECUTION
VERIFIED_VIDEO_EXPERIMENTS=1
CANDIDATE_SELECTION=UNSELECTED
ASSET_ADMISSION=NOT_ADMITTED
EPISODE_MASTER=NOT_CREATED
EXPORT_ARTIFACT=NOT_CREATED
PUBLICATION_ALLOWED=false
```

It must not report publication readiness, commercial provider approval, rights
clearance or budget approval.
