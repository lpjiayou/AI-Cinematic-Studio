# CCV-R1 External Evidence Register

> `EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE`
>
> `SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION`

No binary evidence is stored in this repository. The following items remain pending
collection from the powered-off external GPU machine:

- exact historical bytes and SHA-256 for all three original scripts;
- three ComfyUI API workflow JSON files and their SHA-256 values;
- Round 1 source/reference selection evidence;
- Round 2 full-body reference and exact face-crop derivative;
- five separately registered Round 3 COCO-18 skeleton images, each with its own byte
  size, SHA-256 and generation source;
- all 50 output files with byte size and SHA-256;
- complete seed schedule, including the five Round 1 varying seeds;
- exact model files, byte sizes, SHA-256, sources and license status;
- ComfyUI and every custom-node commit;
- driver, CUDA, Python and PyTorch command output;
- complete raw logs, failures, retries and exclusion decisions;
- blind-review or automated-metric records, if any existed.

Nothing in this list may be backfilled from memory. Missing evidence stays explicit.
Generated images, models and logs must remain outside Git; only normalized manifest
metadata may be committed in a separately reviewed checkpoint.

Model-family finalization must derive conditioning width from the actual safetensors
header and tie the architecture evidence to the full model SHA-256. A filename or
manually declared `sd15`/`sdxl` value is not sufficient evidence.
