# CCV-R1 Historical Evidence Capture Preparation

> `EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE`
>
> `SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION`

This directory prepares a future read-only recovery window on the powered-off
external GPU host. G0 does not access that host and does not rerun the experiment.

## Required order

1. complete the G1 no-GPU tooling closure and remote verification;
2. obtain a separate external-collection G2 authorization;
3. snapshot the external disk if the provider supports it;
4. write a capture template before the source host is accessed;
5. locate only explicitly registered files and hash them without modification;
6. preserve original bytes outside Git in access-controlled storage;
7. derive usage links only from raw workflow/log/history/embedded metadata;
8. shut down the GPU host after two independent inventory copies agree;
9. finalize manifests and perform independent review offline.

Do not start ComfyUI, install or update dependencies, rewrite metadata, normalize
images in place, regenerate missing files or infer a seed.

## Evidence states

```text
PENDING
RECOVERED_USAGE_LINK_VERIFIED
RECOVERED_USAGE_LINK_UNVERIFIED
MISSING
AMBIGUOUS
```

The source host may contain a candidate file without proof that it was used. Custody
and historical usage are separate facts.

## External layout

The future collection should use a repository-external root such as:

```text
ccv-r1-2026-08-14-evidence/
├─ raw/
│  ├─ scripts/
│  ├─ workflows/
│  ├─ references/
│  ├─ skeletons/
│  ├─ logs/
│  ├─ outputs/
│  └─ environment/
├─ inventory/
├─ manifests/
└─ custody/
```

Models may remain in an immutable disk snapshot or restricted object store. Their
bytes must remain available to the independent reviewer; a digest alone is not a
substitute for preserving the underlying evidence.

## Pending-plan validation

Run from the repository root without GPU dependencies:

```bash
python experiments/ccv-r1/validation/validate_capture_plan.py
```

The validator proves that the plan references the checked-in 50-run register, covers
the required non-output evidence groups and contains no guessed external path, size
or digest.

## G1 tooling

The finalizer is an offline evidence normalizer. It does not start ComfyUI or access a
provider by itself.

Generate a collection-input template before the future authorized host window:

```bash
python experiments/ccv-r1/capture/finalize_historical_capture.py \
  --write-template /external/restricted/ccv-r1/capture-input.json
```

After a separately authorized read-only collection, finalize against the preserved
external root:

```bash
python experiments/ccv-r1/capture/finalize_historical_capture.py \
  --capture-input /external/restricted/ccv-r1/capture-input.json \
  --evidence-root /external/restricted/ccv-r1/raw \
  --manifest-out /external/restricted/ccv-r1/historical-evidence-manifest.json
```

The input must contain the exact 27 non-output records and 50 run IDs. Recovered
files are path-confined, positive-size and SHA-256 hashed. `MISSING` and `AMBIGUOUS`
remain explicit, so a partial recovery cannot become a complete capture. The three
historical-script records derive `historicalScriptBytesRecovered`; custody does not
by itself prove historical usage.

Run the no-GPU tooling regression:

```bash
python experiments/ccv-r1/validation/validate_capture_tooling.py
```

## Secret and rights handling

Original logs, scripts and workflows may contain credentials or sensitive paths.
Preserve original bytes only in restricted external storage. Do not commit them.
The normalized repository evidence must contain no token, API key or credential.

Rights and license uncertainty is explicit and blocks production reuse. This package
does not turn synthetic experiment files into commercial assets.
