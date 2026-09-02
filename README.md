# AI Cinematic Studio Core

AI Cinematic Studio Core owns the authoritative Creator domain, lifecycle, public
HTTP/API boundary, deterministic orchestration and evidence-backed media execution.
The commercial Frontend remains a separate repository and may reach Core only through
the authenticated Creator Public API.

## Current behavior baseline

```text
CORE_COMMIT=a455c8e76427d53d75bb7f15259b9875d9768914
CORE_TREE=d92159d5c3c5d3896d1fe9e56b896413277fe4e8
M13_BASE_TAG=m13-base-backend-v1
M13_BASE_TAG_OBJECT=b2d086b622bdb5456f6af325e458aa3771e43e80
M13_BASE_TAG_TARGET=a455c8e76427d53d75bb7f15259b9875d9768914
FRONTEND_COMMIT=a0be9edc91437bf0e7c5dd14883e656e750b3aee
FRONTEND_TREE=c25b9e3744d561c93fed26d0a07e59a1915a6071
```

Documentation-only governance merges may advance `main`; they do not move this
behavior tag or change the frozen product behavior. See the
[cross-repository baseline](docs/status/CROSS_REPOSITORY_BASELINE.md).

## Current state

```text
M13_BASE_BACKEND_COMPLETE=true
M13_BASE_CLOSEOUT_ACCEPTED=true
M13_PRODUCT_CAPABILITY_COMPLETE=false
M13_EXTENSION_G0_AUTHORIZED=false
M13_EXTENSION_IMPLEMENTATION_AUTHORIZED=false

M12_RUNTIME_G0=NOT_COMPLETE
M12_G0_3_STATE=ENVIRONMENT_HOLD
M12_C3_READY_TO_START=false

A100_START_AUTHORIZED=false
PUBLICATION_ALLOWED=false
```

M13 currently ends at `PreviewCandidate`, non-publishing `RenderCandidate` and
`RenderManifest`. It does not create `ExportCandidate`, `EpisodeMaster` or
`ExportArtifact`. Machine QC is not human Approval.

M12's domain and isolated-runtime protocols are merged, but neither runtime is
installed and Runtime G0 is not complete. The persistent CPU build root remains absent.

The complete six-dimensional M1–M19 projection is
[M1–M19 Capability Status](docs/status/M1-M19-CAPABILITY-STATUS.md). The concise current
authorization, blockers and next legal task are in
[Current Milestone](CURRENT_MILESTONE.md).

## Architecture boundary

The accepted dependency direction is:

```text
Browser
→ Frontend Experience Adapter
→ Creator Public HTTP/API v1
→ Creator Application
→ V5 Core OS
→ V4 Platform
→ V3 Render Core
→ Compute / Foundation
```

- V5 owns authoritative facts, versions, lineage and lifecycle.
- V4 owns sealed execution orchestration and provider/runtime boundaries.
- V3 owns deterministic composition and rendering.
- The Frontend does not own Core identities or write internal Core routes.
- Historical K2 evidence does not grant authority for a new project or live write.

See the [System Master Plan](AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md),
[UI Master Plan](AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md) and
[module responsibility matrix](architecture/module-responsibility-matrix.md).

## Documentation authority

All governed documents are classified and indexed:

- [complete documentation index](docs/README.md);
- [documentation governance policy](docs/governance/DOCUMENTATION_GOVERNANCE_POLICY.md);
- [machine-readable document registry](docs/governance/DOCUMENT_REGISTRY.json);
- [human-readable authority map](docs/governance/DOCUMENT_AUTHORITY_MAP.md);
- [document supersession map](docs/governance/DOCUMENT_SUPERSESSION_MAP.md);
- [2026-09-02 audit report](docs/governance/DOCUMENT_AUDIT_REPORT_2026-09-02.md).

Accepted ADRs govern durable architecture inside their explicit scopes. Current status
does not override them. Implementation evidence and historical snapshots prove what
happened but do not authorize current execution.

## Repository layout

```text
apps/            Creator delivery/application boundary
services/        V5, V4 and V3 runtime layers
packages/        validated shared capabilities
architecture/    current architecture and contracts
governance/      ADRs and engineering governance
docs/            indexed engineering documentation
scripts/         repository automation
tests/           unit, contract and integration verification
```

## Validation

Follow [`AGENTS.md`](AGENTS.md). For a pure documentation diff, run only:

```bash
python scripts/validate_markdown.py
python scripts/validate_doc_links.py
```

The protected repository workflow retains exactly five required jobs: Markdown,
Documentation Links, Unit Tests, Contract Tests and Integration Tests.

## Next legal project boundary

```text
NEXT_TASK=LOCAL_WSL2_HANDOFF_AND_M12_C3_PREFLIGHT
```

This is a handoff/preflight boundary only. It does not authorize M12-C3/C4, A100, model
downloads, GPU/provider execution, M13 Extension G0, Asset Admission, Master/Export or
publication.
