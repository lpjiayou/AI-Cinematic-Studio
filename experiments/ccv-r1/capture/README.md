# CCV-R1 Historical Evidence Capture Preparation

> `EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE`
>
> `SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION`

This directory prepares a future read-only recovery window on the powered-off
external GPU host. G0 does not access that host and does not rerun the experiment.

## Required order

1. close the G0 tooling blockers recorded in the governance package;
2. obtain a separate G1 authorization;
3. snapshot the external disk if the provider supports it;
4. locate only explicitly registered files and hash them without modification;
5. preserve original bytes outside Git in access-controlled storage;
6. derive usage links only from raw workflow/log/history/embedded metadata;
7. shut down the GPU host after two independent inventory copies agree;
8. finalize manifests and perform independent review offline.

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

## Secret and rights handling

Original logs, scripts and workflows may contain credentials or sensitive paths.
Preserve original bytes only in restricted external storage. Do not commit them.
The normalized repository evidence must contain no token, API key or credential.

Rights and license uncertainty is explicit and blocks production reuse. This package
does not turn synthetic experiment files into commercial assets.
