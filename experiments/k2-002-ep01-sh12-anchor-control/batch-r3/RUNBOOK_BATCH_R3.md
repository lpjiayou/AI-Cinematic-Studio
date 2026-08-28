# K2-002 EP01 batch-r3 convergence

This directory records the technical baseline produced by the authorized 14-shot sequential batch.

## Immutable execution inputs

- Snapshot: /data/coding/k2-002-ep01-i2v-batch-r3
- Snapshot SHA-256: 39b13db7522e0a6393627a3bf584067df9a578b118989e3e2cde02d87be250c3
- Source shots.json SHA-256: 52e24c8c781f2c729239d6152246677c8eb633d43d17463550c22bb91c8fd9c9
- Exact allowlist: SH04-SH11 and SH13-SH18.
- Excluded: SH01, SH02, SH03, SH12.
- Sampling is frozen by the execution snapshot. Outbound /10/inputs/fps is float 24.0.

## Execution result

- Prompt POSTs: 14 authorized / 14 actual.
- Automatic retries: 0.
- Technical result: 14/14 PASS.
- Visual result: 4 PASS, 4 PASS_WITH_MINOR_DEFECT, 6 FAIL_VISUAL.
- Visual failures were not automatically rerun.

Use EVIDENCE_INDEX.json for remote evidence paths and hashes. SHOT_STATUS_MATRIX.json is the unified 18-shot state record. K2-002-EP01-BASELINE-DRAFT.json is not a publication or canonical admission.

## Governance

AUTHORITY_STATE=TECHNICAL_EVIDENCE_ONLY
PUBLICATION_ALLOWED=false
CANONICAL_MUTATIONS=0

ComfyUI 8188 and the A100 remain running with an empty queue after batch completion.
