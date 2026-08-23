# ADR-0012 — K2 Internal Image-First Real-Media Revision

- Status: `ACCEPTED / M10 LIVE CANDIDATES COMPLETE / EXACT SELECTION + ADMISSION HOST-IMPLEMENTED / CORE 638 PASS / RUNTIME ADMISSION PENDING`
- Date: `2026-08-23`
- Decision owner: Project Lead / Architecture Owner `蔺鹏`
- Required base: `1650c3462b32899151cdba795ddc10e5171ff1da`
- Parent: ADR-0011
- Contract: `architecture/K2_INTERNAL_IMAGE_FIRST_REAL_MEDIA_REVISION_CONTRACT.md`

## Context

The canonical K2-001 run has immutable G2-G6 facts and is at `QC_READY`. P1 proved
one real Wan2.2/A100 video path but its candidate is unselected and not admitted.
Every current G3 shot contains both 林澈 and 顾言, while G4 contains no shot-image
request. Directly treating one character reference as the start image for each shot
would discard required identity lineage and does not implement M10.

## Decision

1. Real-media production is image-first: four multi-reference shot images are
   planned, executed, selected and admitted before four image-to-video requests.
2. Both current G2 visual references are bound to every current M10 request. A
   selected shot image becomes the single M11 start image.
3. Existing G2-G6 facts, local video/audio AssetVersions and original preview remain
   immutable. The revision uses the same production run and existing V5/V4/V3
   ownership boundaries.
4. The state validator uses an explicit allowed-edge graph. It preserves the legacy
   `QC_READY → APPROVAL_READY` edge and adds the image-first branch defined by the
   contract.
5. M10 planning advances only to `REAL_IMAGE_PLAN_READY`. It records no candidate,
   selection, AssetVersion, approval, Master or publication fact.
6. Live image execution fails closed until current ComfyUI node/model evidence proves
   an accepted multi-reference identity-conditioning workflow. Text-only fallback is
   forbidden.
7. Candidate selection remains an exact human decision over four candidate refs and
   digests. Technical PASS and general automatic-execution authorization are not
   creative approval.
8. Rights/Provider/Budget external authorities are not prerequisites only for this
   exact internal self-hosted non-publishing path. The commercial/publication path is
   unchanged and fail-closed.
9. Frontend/G7 work is not a prerequisite for M10/M11 execution; the accepted
   authenticated Creator Public API is the application boundary.
10. One exact four-item selection command is atomic. The authenticated credential is
    the decision actor, V4 owns private paths and re-verification, and V5 alone records
    candidates, decisions, immutable image AssetVersions and the
    `REAL_IMAGE_PLAN_READY → REAL_IMAGE_READY` gate.

## Rejected alternatives

- Directly feed one character board to every M11 shot: loses the second required
  identity and skips M10.
- Reuse the P1 candidate as a production AssetVersion: experiment candidates are not
  selected/admitted assets.
- Overwrite G5/G6: violates append-only evidence.
- Create a second Asset/Provider/Queue/Timeline stack: creates an ownership island.
- Claim multi-reference capability from filenames or model presence alone: live node
  and execution evidence are required.
- Automatically approve unseen images or videos: technical verification is not a
  creative selection decision.

## Consequences

M10 live capability and four-candidate execution have passed on the current A100
host. Exact selection/admission is CPU and persistence work; it does not require
ComfyUI or a running GPU process. M11 planning may begin only after the four exact
selections have produced four immutable image AssetVersions.
