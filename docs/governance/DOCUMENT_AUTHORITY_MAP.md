# Document Authority Map

Status: `GENERATED_REFERENCE`

This human-readable projection mirrors
[`DOCUMENT_REGISTRY.json`](DOCUMENT_REGISTRY.json). It does not create authority;
the policy and source documents remain controlling within their declared scopes.

## Authority chain

1. bounded Project Lead authorization;
2. applicable `AGENTS.md`;
3. Accepted ADRs and mandatory governance contracts;
4. System/UI Master Plans;
5. Golden and normative contracts;
6. current-state projection;
7. implementation/test evidence and receipts;
8. immutable historical context.

Scope always matters. `CURRENT_MILESTONE.md` cannot override an Accepted ADR,
and historical evidence cannot authorize current execution.

## Classification totals

| Class | Count | Current-state claims allowed |
| --- | ---: | --- |
| `ACCEPTED_DECISION` | 20 | no |
| `NORMATIVE_ARCHITECTURE` | 14 | no |
| `NORMATIVE_CONTRACT` | 31 | no |
| `CURRENT_STATUS` | 4 | yes |
| `CAPABILITY_MATRIX` | 1 | yes |
| `OPERATIONAL_RUNBOOK` | 18 | no |
| `IMPLEMENTATION_EVIDENCE` | 21 | no |
| `HISTORICAL_EVIDENCE` | 36 | no |
| `SUPERSEDED` | 9 | no |
| `DRAFT` | 3 | no |
| `DEPRECATED` | 0 | no |
| `GENERATED_REFERENCE` | 15 | no |

## ACCEPTED_DECISION

| Document | Status | Owner |
| --- | --- | --- |
| [`governance/ADR-0001-separate-commercial-experience-layer-from-core-creator-runtime.md`](../../governance/ADR-0001-separate-commercial-experience-layer-from-core-creator-runtime.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0002-v5-lifecycle-integrity-boundary.md`](../../governance/ADR-0002-v5-lifecycle-integrity-boundary.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0003-m6-series-intelligence-baseline.md`](../../governance/ADR-0003-m6-series-intelligence-baseline.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0004-m6-series-intelligence-durable-sqlite-boundary.md`](../../governance/ADR-0004-m6-series-intelligence-durable-sqlite-boundary.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0005-m6-series-intelligence-consumer-boundary.md`](../../governance/ADR-0005-m6-series-intelligence-consumer-boundary.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0006-v5-text-generation-capability-boundary.md`](../../governance/ADR-0006-v5-text-generation-capability-boundary.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0007-creator-public-api-authentication-and-workspace-isolation.md`](../../governance/ADR-0007-creator-public-api-authentication-and-workspace-isolation.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0008-k2-single-episode-production-closure.md`](../../governance/ADR-0008-k2-single-episode-production-closure.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0009-k2-publishable-media-production.md`](../../governance/ADR-0009-k2-publishable-media-production.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0010-k2-canonical-lineage-bootstrap.md`](../../governance/ADR-0010-k2-canonical-lineage-bootstrap.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0011-k2-internal-self-hosted-p1.md`](../../governance/ADR-0011-k2-internal-self-hosted-p1.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0012-k2-internal-image-first-real-media-revision.md`](../../governance/ADR-0012-k2-internal-image-first-real-media-revision.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0013-k2-control-plane-convergence.md`](../../governance/ADR-0013-k2-control-plane-convergence.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0014-k2-001-archive-k2-002-changan-start.md`](../../governance/ADR-0014-k2-001-archive-k2-002-changan-start.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0015-m12-isolated-audio-runtime-and-acyclic-voice-clone-lineage.md`](../../governance/ADR-0015-m12-isolated-audio-runtime-and-acyclic-voice-clone-lineage.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0016-m13-timeline-render-candidate-and-deterministic-post-boundary.md`](../../governance/ADR-0016-m13-timeline-render-candidate-and-deterministic-post-boundary.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0017-canonical-static-resource-assets-and-font-license-boundary.md`](../../governance/ADR-0017-canonical-static-resource-assets-and-font-license-boundary.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0018-canonical-identity-reference-version-projection-and-runtime-currentness-boundary.md`](../../governance/ADR-0018-canonical-identity-reference-version-projection-and-runtime-currentness-boundary.md) | `ACCEPTED` | Architecture Owner / Documentation Governance Owner |
| [`governance/ADR-0019-upstream-execution-method-and-requirement-routing.md`](../../governance/ADR-0019-upstream-execution-method-and-requirement-routing.md) | `ACCEPTED` | Architecture Owner / M3-M12 Domain Owners |
| [`governance/ADR-0020-m12-cpu-build-host-and-a100-offline-consumer.md`](../../governance/ADR-0020-m12-cpu-build-host-and-a100-offline-consumer.md) | `ACCEPTED` | Project Lead / Architecture Owner / Infrastructure Owner / M12 Domain Owner |

## NORMATIVE_ARCHITECTURE

| Document | Status | Owner |
| --- | --- | --- |
| [`AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`](../../AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md) | `ACTIVE` | Architecture Owner |
| [`AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md`](../../AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md) | `ACTIVE` | Architecture Owner |
| [`architecture/dependency-map.md`](../../architecture/dependency-map.md) | `ACTIVE` | Architecture Owner |
| [`architecture/dependency-rules.md`](../../architecture/dependency-rules.md) | `ACTIVE` | Architecture Owner |
| [`architecture/layer-boundaries.md`](../../architecture/layer-boundaries.md) | `ACTIVE` | Architecture Owner |
| [`architecture/module-responsibility-matrix.md`](../../architecture/module-responsibility-matrix.md) | `ACTIVE` | Architecture Owner |
| [`architecture/system-context.md`](../../architecture/system-context.md) | `ACTIVE` | Architecture Owner |
| [`architecture/system-overview.md`](../../architecture/system-overview.md) | `ACTIVE` | Architecture Owner |
| [`docs/03-data-design/data-domain-model.md`](../03-data-design/data-domain-model.md) | `ACTIVE` | Data Architecture Owner |
| [`docs/03-data-design/data-ownership.md`](../03-data-design/data-ownership.md) | `ACTIVE` | Data Architecture Owner |
| [`docs/07-v3-render-core/render-core-boundary.md`](../07-v3-render-core/render-core-boundary.md) | `ACTIVE` | Runtime Owner |
| [`docs/14-application-design/application-layer-overview.md`](../14-application-design/application-layer-overview.md) | `ACTIVE` | Application Owner |
| [`docs/14-application-design/ui-domain-mapping.md`](../14-application-design/ui-domain-mapping.md) | `ACTIVE` | Application Owner |
| [`docs/14-application-design/user-flow-mapping.md`](../14-application-design/user-flow-mapping.md) | `ACTIVE` | Application Owner |

## NORMATIVE_CONTRACT

| Document | Status | Owner |
| --- | --- | --- |
| [`.github/pull_request_template.md`](../../.github/pull_request_template.md) | `ACTIVE` | Documentation Governance Owner |
| [`AGENTS.md`](../../AGENTS.md) | `ACTIVE` | Documentation Governance Owner |
| [`architecture/CREATOR_PUBLIC_API_AUTHENTICATION_AND_WORKSPACE_ISOLATION_CONTRACT.md`](../../architecture/CREATOR_PUBLIC_API_AUTHENTICATION_AND_WORKSPACE_ISOLATION_CONTRACT.md) | `ACTIVE` | Architecture Owner |
| [`architecture/K2_CANONICAL_LINEAGE_BOOTSTRAP_CONTRACT.md`](../../architecture/K2_CANONICAL_LINEAGE_BOOTSTRAP_CONTRACT.md) | `ACTIVE` | Architecture Owner |
| [`architecture/K2_GOLDEN_EPISODE_PRODUCTION_CONTRACT.md`](../../architecture/K2_GOLDEN_EPISODE_PRODUCTION_CONTRACT.md) | `ACTIVE` | Architecture Owner |
| [`architecture/K2_INTERNAL_IMAGE_FIRST_REAL_MEDIA_REVISION_CONTRACT.md`](../../architecture/K2_INTERNAL_IMAGE_FIRST_REAL_MEDIA_REVISION_CONTRACT.md) | `ACTIVE` | Architecture Owner |
| [`architecture/K2_INTERNAL_SELF_HOSTED_P1_CONTRACT.md`](../../architecture/K2_INTERNAL_SELF_HOSTED_P1_CONTRACT.md) | `ACTIVE` | Architecture Owner |
| [`architecture/M3_M11_UPSTREAM_METHOD_CLOSURE_CONTRACT.md`](../../architecture/M3_M11_UPSTREAM_METHOD_CLOSURE_CONTRACT.md) | `ACTIVE` | Architecture Owner / M3-M12 Domain Owners |
| [`architecture/M6_SERIES_INTELLIGENCE_CONSUMER_CONTRACT.md`](../../architecture/M6_SERIES_INTELLIGENCE_CONSUMER_CONTRACT.md) | `ACTIVE` | Architecture Owner |
| [`architecture/M6_SERIES_INTELLIGENCE_DOMAIN_CONTRACT.md`](../../architecture/M6_SERIES_INTELLIGENCE_DOMAIN_CONTRACT.md) | `ACTIVE` | Architecture Owner |
| [`architecture/M6_SERIES_INTELLIGENCE_SQLITE_CONTRACT.md`](../../architecture/M6_SERIES_INTELLIGENCE_SQLITE_CONTRACT.md) | `ACTIVE` | Architecture Owner |
| [`architecture/V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md`](../../architecture/V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md) | `ACTIVE` | Architecture Owner |
| [`docs/03-data-design/asset-lifecycle.md`](../03-data-design/asset-lifecycle.md) | `ACTIVE` | Data Architecture Owner |
| [`docs/03-data-design/data-consistency-rules.md`](../03-data-design/data-consistency-rules.md) | `ACTIVE` | Data Architecture Owner |
| [`docs/03-data-design/data-storage-abstraction.md`](../03-data-design/data-storage-abstraction.md) | `ACTIVE` | Data Architecture Owner |
| [`docs/04-interface-contract/application-v5-contract.md`](../04-interface-contract/application-v5-contract.md) | `ACTIVE` | Public Contract Owner |
| [`docs/04-interface-contract/creator-public-http-v1.md`](../04-interface-contract/creator-public-http-v1.md) | `ACTIVE` | Public Contract Owner |
| [`docs/04-interface-contract/error-code-standard.md`](../04-interface-contract/error-code-standard.md) | `ACTIVE` | Public Contract Owner |
| [`docs/04-interface-contract/event-contract.md`](../04-interface-contract/event-contract.md) | `ACTIVE` | Public Contract Owner |
| [`docs/04-interface-contract/v3-compute-contract.md`](../04-interface-contract/v3-compute-contract.md) | `ACTIVE` | Public Contract Owner |
| [`docs/04-interface-contract/v4-v3-contract.md`](../04-interface-contract/v4-v3-contract.md) | `ACTIVE` | Public Contract Owner |
| [`docs/04-interface-contract/v5-v4-contract.md`](../04-interface-contract/v5-v4-contract.md) | `ACTIVE` | Public Contract Owner |
| [`docs/14-application-design/application-command-contract.md`](../14-application-design/application-command-contract.md) | `ACTIVE` | Application Owner |
| [`docs/14-application-design/internal-content-lab-ui-scope.md`](../14-application-design/internal-content-lab-ui-scope.md) | `ACTIVE` | Application Owner |
| [`docs/governance/CI_DOCS_ONLY_FAST_PATH_VALIDATION_2026-09-02.md`](CI_DOCS_ONLY_FAST_PATH_VALIDATION_2026-09-02.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`docs/governance/CI_REQUIRED_CHECK_FAST_PATH_POLICY.md`](CI_REQUIRED_CHECK_FAST_PATH_POLICY.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`docs/governance/DOCUMENTATION_GOVERNANCE_POLICY.md`](DOCUMENTATION_GOVERNANCE_POLICY.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`governance/AI_CINEMATIC_STUDIO_DELIVERY_GOVERNANCE_PACKAGE_V1.md`](../../governance/AI_CINEMATIC_STUDIO_DELIVERY_GOVERNANCE_PACKAGE_V1.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`governance/ARCHITECTURE_CHANGE_PROCESS.md`](../../governance/ARCHITECTURE_CHANGE_PROCESS.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`governance/ARCHITECTURE_GUARD.md`](../../governance/ARCHITECTURE_GUARD.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`governance/RISK_REGISTER.md`](../../governance/RISK_REGISTER.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |

## CURRENT_STATUS

| Document | Status | Owner |
| --- | --- | --- |
| [`CURRENT_MILESTONE.md`](../../CURRENT_MILESTONE.md) | `CURRENT` | Project Lead / Documentation Governance Owner |
| [`architecture/M12_C3_DEDICATED_LINUX_CPU_BUILD_HOST_SPECIFICATION.md`](../../architecture/M12_C3_DEDICATED_LINUX_CPU_BUILD_HOST_SPECIFICATION.md) | `CURRENT` | Project Lead / Architecture Owner / Infrastructure Owner / Repository Governance Owner / M12 Domain Owner |
| [`docs/status/CORE_PUBLIC_JSON_AND_NUMERIC_INTEGRITY_HARDENING_2026-09-05.md`](../status/CORE_PUBLIC_JSON_AND_NUMERIC_INTEGRITY_HARDENING_2026-09-05.md) | `CURRENT` | Project Lead / Creator Public Contract Owner / V5 Domain Owners |
| [`docs/status/CROSS_REPOSITORY_BASELINE.md`](../status/CROSS_REPOSITORY_BASELINE.md) | `CURRENT` | Documentation Governance Owner |
| [`docs/status/M12_A100_BUILD_HOST_REFLIGHT_2026-09-03.md`](../status/M12_A100_BUILD_HOST_REFLIGHT_2026-09-03.md) | `CURRENT` | Project Lead / Infrastructure Owner / Architecture Owner / M12 Domain Owner |

## CAPABILITY_MATRIX

| Document | Status | Owner |
| --- | --- | --- |
| [`docs/status/M1-M19-CAPABILITY-STATUS.md`](../status/M1-M19-CAPABILITY-STATUS.md) | `CURRENT` | Documentation Governance Owner |

## OPERATIONAL_RUNBOOK

| Document | Status | Owner |
| --- | --- | --- |
| [`docs/governance/CI_WAITING_RUNBOOK.md`](CI_WAITING_RUNBOOK.md) | `ACTIVE` | Repository Governance Owner / CI Governance Owner |
| [`docs/08-compute/k2-comfyui-wan22-operator-runbook.md`](../08-compute/k2-comfyui-wan22-operator-runbook.md) | `ACTIVE` | Runtime Owner |
| [`docs/11-testing/release-validation.md`](../11-testing/release-validation.md) | `ACTIVE` | Verification Owner |
| [`docs/11-testing/test-evidence-standard.md`](../11-testing/test-evidence-standard.md) | `ACTIVE` | Verification Owner |
| [`docs/11-testing/test-levels.md`](../11-testing/test-levels.md) | `ACTIVE` | Verification Owner |
| [`docs/11-testing/testing-strategy.md`](../11-testing/testing-strategy.md) | `ACTIVE` | Verification Owner |
| [`docs/11-testing/verification-gates.md`](../11-testing/verification-gates.md) | `ACTIVE` | Verification Owner |
| [`docs/16-k2-production/K2-G2-AUTHORITY-PREPARATION-RUNBOOK.md`](../16-k2-production/K2-G2-AUTHORITY-PREPARATION-RUNBOOK.md) | `ACTIVE` | K2 Domain Owner |
| [`docs/16-k2-production/K2-INTERNAL-SELF-HOSTED-P1-RUNBOOK.md`](../16-k2-production/K2-INTERNAL-SELF-HOSTED-P1-RUNBOOK.md) | `ACTIVE` | K2 Domain Owner |
| [`experiments/k2-002-ep01-i2v/RUNBOOK.md`](../../experiments/k2-002-ep01-i2v/RUNBOOK.md) | `ACTIVE` | Experiment Owner |
| [`governance/BASELINE_RELEASE_PROCESS.md`](../../governance/BASELINE_RELEASE_PROCESS.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`governance/BRANCH_PROTECTION.md`](../../governance/BRANCH_PROTECTION.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`governance/BRANCH_STRATEGY.md`](../../governance/BRANCH_STRATEGY.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`governance/CODE_REVIEW_RULES.md`](../../governance/CODE_REVIEW_RULES.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`governance/COMMIT_CONVENTION.md`](../../governance/COMMIT_CONVENTION.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`governance/DEFINITION_OF_DONE.md`](../../governance/DEFINITION_OF_DONE.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`governance/DEVELOPMENT_RULES.md`](../../governance/DEVELOPMENT_RULES.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |
| [`governance/GIT_WORKFLOW.md`](../../governance/GIT_WORKFLOW.md) | `ACTIVE` | Architecture Owner / Documentation Governance Owner |

## IMPLEMENTATION_EVIDENCE

| Document | Status | Owner |
| --- | --- | --- |
| [`docs/archive/AGENTS_ARCHIVE_MIGRATION_MANIFEST.json`](../archive/AGENTS_ARCHIVE_MIGRATION_MANIFEST.json) | `RECORDED` | Repository Governance Owner / CI Governance Owner |
| [`design-qa.md`](../../design-qa.md) | `RECORDED` | Documentation Governance Owner |
| [`docs/04-interface-contract/v5-v3-vertical-slice-review.md`](../04-interface-contract/v5-v3-vertical-slice-review.md) | `RECORDED` | Public Contract Owner |
| [`docs/14-application-design/REFERENCE_VIDEO_CAPABILITY_AND_WORKSPACE_MERGED_BASELINE.md`](../14-application-design/REFERENCE_VIDEO_CAPABILITY_AND_WORKSPACE_MERGED_BASELINE.md) | `RECORDED` | Application Owner |
| [`experiments/ccv-r1/CHARACTER_CONSISTENCY_VALIDATION_REPORT_R1.md`](../../experiments/ccv-r1/CHARACTER_CONSISTENCY_VALIDATION_REPORT_R1.md) | `RECORDED` | Experiment Owner |
| [`experiments/ccv-r1/README.md`](../../experiments/ccv-r1/README.md) | `RECORDED` | Experiment Owner |
| [`experiments/ccv-r1/evidence/README.md`](../../experiments/ccv-r1/evidence/README.md) | `RECORDED` | Experiment Owner |
| [`experiments/ccv-r1/experiment-manifest.schema.json`](../../experiments/ccv-r1/experiment-manifest.schema.json) | `RECORDED` | Experiment Owner |
| [`experiments/ccv-r1/workflows/README.md`](../../experiments/ccv-r1/workflows/README.md) | `RECORDED` | Experiment Owner |
| [`experiments/k2-001-canonical-bootstrap/README.md`](../../experiments/k2-001-canonical-bootstrap/README.md) | `RECORDED` | Experiment Owner |
| [`experiments/k2-001-m6-draft/README.md`](../../experiments/k2-001-m6-draft/README.md) | `RECORDED` | Experiment Owner |
| [`experiments/k2-001-preboot/README.md`](../../experiments/k2-001-preboot/README.md) | `RECORDED` | Experiment Owner |
| [`experiments/k2-002-changan-preproduction/README.md`](../../experiments/k2-002-changan-preproduction/README.md) | `RECORDED` | Experiment Owner |
| [`experiments/k2-002-ep01-i2v-v2/README.md`](../../experiments/k2-002-ep01-i2v-v2/README.md) | `RECORDED` | Experiment Owner |
| [`experiments/k2-002-ep01-i2v-v2/anchor_manifest.json`](../../experiments/k2-002-ep01-i2v-v2/anchor_manifest.json) | `RECORDED` | Experiment Owner |
| [`experiments/k2-002-ep01-i2v-v2/archive_manifest.json`](../../experiments/k2-002-ep01-i2v-v2/archive_manifest.json) | `RECORDED` | Experiment Owner |
| [`governance/AI_CINEMATIC_STUDIO_STAGE_ASSET_INVENTORY_2026-08-21.md`](../../governance/AI_CINEMATIC_STUDIO_STAGE_ASSET_INVENTORY_2026-08-21.md) | `RECORDED` | Architecture Owner / Documentation Governance Owner |
| [`tests/fixtures/m13/e2/manifest.json`](../../tests/fixtures/m13/e2/manifest.json) | `RECORDED` | Verification Owner |
| [`tests/fixtures/m13/r2/manifest.json`](../../tests/fixtures/m13/r2/manifest.json) | `RECORDED` | Verification Owner |
| [`tests/fixtures/m13/zhen/source_manifest.json`](../../tests/fixtures/m13/zhen/source_manifest.json) | `RECORDED` | Verification Owner |
| [`tests/fixtures/v5_fonts/OFL.txt`](../../tests/fixtures/v5_fonts/OFL.txt) | `RECORDED` | Verification Owner |

## HISTORICAL_EVIDENCE

| Document | Status | Owner |
| --- | --- | --- |
| [`CURRENT_MILESTONE_HISTORY_THROUGH_2026-09-02.md`](../../CURRENT_MILESTONE_HISTORY_THROUGH_2026-09-02.md) | `HISTORICAL` | Documentation Governance Owner |
| [`docs/archive/AGENTS_HISTORICAL_EXECUTION_RECORDS_THROUGH_2026-09-03.md`](../archive/AGENTS_HISTORICAL_EXECUTION_RECORDS_THROUGH_2026-09-03.md) | `HISTORICAL` | Documentation Governance Owner |
| [`docs/status/M12_A100_BUILD_HOST_PREFLIGHT_2026-09-03.md`](../status/M12_A100_BUILD_HOST_PREFLIGHT_2026-09-03.md) | `HISTORICAL` | Project Lead / Repository Governance Owner / M12 Domain Owner |
| [`docs/status/M12_C3_WSL2_CPU_BUILD_HOST_PREFLIGHT_2026-09-04.md`](../status/M12_C3_WSL2_CPU_BUILD_HOST_PREFLIGHT_2026-09-04.md) | `HISTORICAL` | Project Lead / Architecture Owner / Infrastructure Owner / M12 Domain Owner |
| [`docs/12-release/baseline-asset-acceptance-decision-record.md`](../12-release/baseline-asset-acceptance-decision-record.md) | `HISTORICAL` | Release Owner |
| [`docs/12-release/baseline-v0.1.0-candidate-manifest.md`](../12-release/baseline-v0.1.0-candidate-manifest.md) | `HISTORICAL` | Release Owner |
| [`docs/12-release/investor-readiness-acceptance-record.md`](../12-release/investor-readiness-acceptance-record.md) | `HISTORICAL` | Release Owner |
| [`docs/12-release/phase-0-exit-record.md`](../12-release/phase-0-exit-record.md) | `HISTORICAL` | Release Owner |
| [`docs/12-release/phase-1-execution-authorization.md`](../12-release/phase-1-execution-authorization.md) | `HISTORICAL` | Release Owner |
| [`docs/12-release/phase-1-production-validation-plan.md`](../12-release/phase-1-production-validation-plan.md) | `HISTORICAL` | Release Owner |
| [`docs/12-release/phase-1-responsibility-assignment.md`](../12-release/phase-1-responsibility-assignment.md) | `HISTORICAL` | Release Owner |
| [`docs/12-release/phase-1-scope-approval.md`](../12-release/phase-1-scope-approval.md) | `HISTORICAL` | Release Owner |
| [`docs/12-release/phase-1-vertical-slice-authorization.md`](../12-release/phase-1-vertical-slice-authorization.md) | `HISTORICAL` | Release Owner |
| [`docs/15-investor-readiness/milestones/M001-v5-identity-engine-foundation.md`](../15-investor-readiness/milestones/M001-v5-identity-engine-foundation.md) | `HISTORICAL` | Project Lead |
| [`docs/15-investor-readiness/milestones/M002-v5-project-engine-foundation.md`](../15-investor-readiness/milestones/M002-v5-project-engine-foundation.md) | `HISTORICAL` | Project Lead |
| [`docs/15-investor-readiness/milestones/M003-v5-asset-registry-foundation.md`](../15-investor-readiness/milestones/M003-v5-asset-registry-foundation.md) | `HISTORICAL` | Project Lead |
| [`docs/15-investor-readiness/milestones/M004-v5-project-asset-relationship-foundation.md`](../15-investor-readiness/milestones/M004-v5-project-asset-relationship-foundation.md) | `HISTORICAL` | Project Lead |
| [`docs/16-k2-production/K2-001-HISTORICAL-VALIDATION-ARCHIVE.md`](../16-k2-production/K2-001-HISTORICAL-VALIDATION-ARCHIVE.md) | `HISTORICAL` | K2 Domain Owner |
| [`docs/16-k2-production/k2-002-changan/K2-002-CHANGAN-SERIES-AND-EP01-03-v1.4.md`](../16-k2-production/k2-002-changan/K2-002-CHANGAN-SERIES-AND-EP01-03-v1.4.md) | `HISTORICAL` | K2 Domain Owner |
| [`docs/governance/DOCUMENT_AUDIT_REPORT_2026-09-02.md`](DOCUMENT_AUDIT_REPORT_2026-09-02.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G0.md`](../../governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G0.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1-AUTHORIZATION.md`](../../governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1-AUTHORIZATION.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1-CLOSEOUT-M6-P3-G0-OWNER-REVIEW.md`](../../governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1-CLOSEOUT-M6-P3-G0-OWNER-REVIEW.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-CCV-R1-EVIDENCE-HARDENING.md`](../../governance/ACS-CCV-R1-EVIDENCE-HARDENING.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-GOV-POST-M6-P3-G1-CLOSEOUT.md`](../../governance/ACS-GOV-POST-M6-P3-G1-CLOSEOUT.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-K2-002-NON-GPU-PREPRODUCTION-REBASELINE.md`](../../governance/ACS-K2-002-NON-GPU-PREPRODUCTION-REBASELINE.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-K2-002-SCRIPT-V1-4-ACCEPTANCE-AND-EP01-IMPLEMENTATION.md`](../../governance/ACS-K2-002-SCRIPT-V1-4-ACCEPTANCE-AND-EP01-IMPLEMENTATION.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-K2-002-SCRIPT-V1-4-EXACT-DIGEST-REBASELINE.md`](../../governance/ACS-K2-002-SCRIPT-V1-4-EXACT-DIGEST-REBASELINE.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-M6-P0-P1-R2-CLOSEOUT-G2-M6-P2-AUTHORIZATION.md`](../../governance/ACS-M6-P0-P1-R2-CLOSEOUT-G2-M6-P2-AUTHORIZATION.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-M6-P2-G1-CLOSEOUT-G3-M6-P3-G0.md`](../../governance/ACS-M6-P2-G1-CLOSEOUT-G3-M6-P3-G0.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING.md`](../../governance/ACS-M6-P3-B1-EPISODE-PLAN-ITEM-BINDING.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-M6-P3-G0-OWNER-ACCEPTANCE.md`](../../governance/ACS-M6-P3-G0-OWNER-ACCEPTANCE.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/ACS-M6-P3-G1-EPISODE-BASELINE-CONSUMER.md`](../../governance/ACS-M6-P3-G1-EPISODE-BASELINE-CONSUMER.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/K2_001_ADR_0013_MAIN_CLOSEOUT_2026-08-25.md`](../../governance/K2_001_ADR_0013_MAIN_CLOSEOUT_2026-08-25.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/K2_CANONICAL_LINEAGE_G1_HOST_CLOSEOUT_2026-08-21.md`](../../governance/K2_CANONICAL_LINEAGE_G1_HOST_CLOSEOUT_2026-08-21.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |
| [`governance/PRE-M6-RB1.3-CLOSEOUT-M6-P0-P1-AUTHORIZATION.md`](../../governance/PRE-M6-RB1.3-CLOSEOUT-M6-P0-P1-AUTHORIZATION.md) | `HISTORICAL` | Architecture Owner / Documentation Governance Owner |

## SUPERSEDED

| Document | Status | Owner |
| --- | --- | --- |
| [`architecture/K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT.md`](../../architecture/K2_PUBLISHABLE_MEDIA_PRODUCTION_CONTRACT.md) | `SUPERSEDED` | Architecture Owner |
| [`docs/16-k2-production/K2-001-PREPRODUCTION-CANDIDATE.md`](../16-k2-production/K2-001-PREPRODUCTION-CANDIDATE.md) | `SUPERSEDED` | K2 Domain Owner |
| [`docs/16-k2-production/K2-P1-PREBOOT-TO-LIVE-RUNBOOK.md`](../16-k2-production/K2-P1-PREBOOT-TO-LIVE-RUNBOOK.md) | `SUPERSEDED` | K2 Domain Owner |
| [`docs/16-k2-production/k2-002-changan/K2-002-CHANGAN-SERIES-AND-EP01-03-v1.3.md`](../16-k2-production/k2-002-changan/K2-002-CHANGAN-SERIES-AND-EP01-03-v1.3.md) | `SUPERSEDED` | K2 Domain Owner |
| [`docs/16-k2-production/k2-002-changan/source/K2-002-CHANGAN-SOURCE-v1.2.md`](../16-k2-production/k2-002-changan/source/K2-002-CHANGAN-SOURCE-v1.2.md) | `SUPERSEDED` | K2 Domain Owner |
| [`docs/16-k2-production/k2-002-changan/source/K2-002-CHANGAN-UPLOADED-OWNER-REVISION-v1.4.md`](../16-k2-production/k2-002-changan/source/K2-002-CHANGAN-UPLOADED-OWNER-REVISION-v1.4.md) | `SUPERSEDED` | K2 Domain Owner |
| [`governance/K2_P1_PREBOOT_OFFLINE_PACKAGE.md`](../../governance/K2_P1_PREBOOT_OFFLINE_PACKAGE.md) | `SUPERSEDED` | Architecture Owner / Documentation Governance Owner |
| [`governance/K2_PUBLISHABLE_P0_EXTERNAL_HOLD.md`](../../governance/K2_PUBLISHABLE_P0_EXTERNAL_HOLD.md) | `SUPERSEDED` | Architecture Owner / Documentation Governance Owner |
| [`governance/K2_PUBLISHABLE_PRODUCTION_EXECUTION_PACKAGE.md`](../../governance/K2_PUBLISHABLE_PRODUCTION_EXECUTION_PACKAGE.md) | `SUPERSEDED` | Architecture Owner / Documentation Governance Owner |

## DRAFT

| Document | Status | Owner |
| --- | --- | --- |
| [`architecture/technology-stack-decision.md`](../../architecture/technology-stack-decision.md) | `DRAFT` | Architecture Owner |
| [`experiments/ccv-r1/experiment-manifest.pending.json`](../../experiments/ccv-r1/experiment-manifest.pending.json) | `DRAFT` | Experiment Owner |
| [`governance/ADR_TEMPLATE.md`](../../governance/ADR_TEMPLATE.md) | `DRAFT` | Architecture Owner / Documentation Governance Owner |

## DEPRECATED

| Document | Status | Owner |
| --- | --- | --- |
| _None_ | — | — |

## GENERATED_REFERENCE

| Document | Status | Owner |
| --- | --- | --- |
| [`README.md`](../../README.md) | `REFERENCE` | Project Lead / Documentation Governance Owner |
| [`docs/03-data-design/README.md`](../03-data-design/README.md) | `REFERENCE` | Data Architecture Owner |
| [`docs/04-interface-contract/README.md`](../04-interface-contract/README.md) | `REFERENCE` | Public Contract Owner |
| [`docs/07-v3-render-core/README.md`](../07-v3-render-core/README.md) | `REFERENCE` | Runtime Owner |
| [`docs/11-testing/README.md`](../11-testing/README.md) | `REFERENCE` | Verification Owner |
| [`docs/14-application-design/README.md`](../14-application-design/README.md) | `REFERENCE` | Application Owner |
| [`docs/15-investor-readiness/README.md`](../15-investor-readiness/README.md) | `REFERENCE` | Project Lead |
| [`docs/16-k2-production/README.md`](../16-k2-production/README.md) | `REFERENCE` | K2 Domain Owner |
| [`docs/16-k2-production/k2-002-changan/README.md`](../16-k2-production/k2-002-changan/README.md) | `REFERENCE` | K2 Domain Owner |
| [`docs/README.md`](../README.md) | `REFERENCE` | Documentation Governance Owner |
| [`docs/governance/DOCUMENT_AUTHORITY_MAP.md`](DOCUMENT_AUTHORITY_MAP.md) | `REFERENCE` | Architecture Owner / Documentation Governance Owner |
| [`docs/governance/DOCUMENT_REGISTRY.json`](DOCUMENT_REGISTRY.json) | `REFERENCE` | Architecture Owner / Documentation Governance Owner |
| [`docs/governance/DOCUMENT_SUPERSESSION_MAP.md`](DOCUMENT_SUPERSESSION_MAP.md) | `REFERENCE` | Architecture Owner / Documentation Governance Owner |
| [`tests/README.md`](../../tests/README.md) | `REFERENCE` | Verification Owner |
| [`tests/fixtures/v5_fonts/README.md`](../../tests/fixtures/v5_fonts/README.md) | `REFERENCE` | Verification Owner |

## Historical isolation

Every `IMPLEMENTATION_EVIDENCE`, `HISTORICAL_EVIDENCE` and `SUPERSEDED` entry
is non-authoritative for current execution and carries
`HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true` in the registry. Drafts and
generated references likewise create no architecture or execution authority.
