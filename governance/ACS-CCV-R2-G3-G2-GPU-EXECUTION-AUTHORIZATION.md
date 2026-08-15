# ACS-CCV-R2-G3-G2 GPU Execution Authorization

## Decision

The Project Lead explicitly authorizes `ACS-CCV-R2-G3-G2-GPU-EXECUTION` on
2026-08-15, bound to the closed G3-G1 readiness controls below.

| Control | Frozen value |
| --- | --- |
| G3-G1 preparation root | `/data/ccv-r2-2026-08-15-preparation-g3-g1` |
| G3 readiness SHA-256 | `e39ac4a8c3ddbf1f26571b295bcb00da7ff6b499acd49e8ad47291726bbbc5e4` |
| Preparation inventory SHA-256 | `20878b06608af6310cc1e60648d5b5e59a05cc6aa43475feb9ff3f9ae1e62845` |
| Unique requests | `51` |
| Maximum queued requests | `51` |
| Maximum in flight | `1` |
| Automatic retry | `false` |
| Result root | `/data/ccv-r2-2026-08-15-results-g3-g2` |

## Authorized scope

The authorization permits only:

1. revalidation of the exact G3-G1 readiness and inventory controls;
2. local ComfyUI execution of the 51 already-materialized opaque requests;
3. one in-flight request at a time;
4. copying digest-verified PNG outputs into the isolated G3-G2 result root;
5. atomic result/failure ledgers, result inventory, execution receipt and blind review package;
6. independent technical result validation after generation.

## Fail-closed boundary

- no automatic retry;
- stop after the first terminal request failure;
- do not overwrite an existing output;
- do not mutate G2 results, G2 archives or G3-G1 preparation inputs;
- do not reveal `technical-map.sealed.json` to blind reviewers;
- do not treat the external P0 arm as primary acceptance evidence;
- do not set `validationAccepted` or `productionReady` to true;
- do not enter product, schema, migration, worker-integration or production deployment work.

## Exit state

Successful image generation and technical validation may report a G3-G2 checkpoint
candidate only. Independent blind visual review remains required. Final acceptance is
reserved to the Project Lead.

