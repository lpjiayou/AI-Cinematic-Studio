from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest import mock

from services.v5_core_os.episode_production import delivery
from services.v5_core_os.episode_production.foundation import StaleInputError, _digest


class _Wire:
    def __init__(self, value: dict) -> None:
        self._value = deepcopy(value)

    def as_dict(self) -> dict:
        return deepcopy(self._value)


class _Evidence:
    @staticmethod
    def read_snapshot(workspace_ref: str, run_ref: str):
        return SimpleNamespace(
            workspaceRef=workspace_ref,
            productionRunRef=run_ref,
            revisionToken="f" * 64,
        )


class M13E4DeliveryPreviewDispatchContractTests(unittest.TestCase):
    def test_real_delivery_entrypoint_has_closed_e4_replay_dispatch(self) -> None:
        """Exercise the service method, not only the V3/V4 bridge builders."""

        workspace = "workspace-m13-e4-preview-dispatch"
        run_ref = "run-m13-e4-preview-dispatch"
        timeline_ref = "timeline-version-m13-e4-preview-dispatch"
        timeline_digest = "1" * 64
        normalized = {
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "expectedRunVersion": 7,
            "expectedEvidenceRevision": "2" * 64,
            "idempotencyKey": "m13-e4-preview-dispatch-idempotency",
            "operationRef": "m13-e4-preview-dispatch-operation",
            "timelineVersionRef": timeline_ref,
            "timelineVersionDigest": timeline_digest,
        }
        timeline = _Wire(
            {
                "timelineVersionRef": timeline_ref,
                "payloadDigest": timeline_digest,
            }
        )
        restored = {
            "timelineVersion": timeline,
            "versionHistory": [timeline],
        }
        composition = _Wire(
            {
                "compositionResultRef": "composition-result-m13-e4",
                "payloadDigest": "3" * 64,
            }
        )
        preview = _Wire(
            {
                "previewCandidateVersionRef": "preview-version-m13-e4",
                "payloadDigest": "4" * 64,
            }
        )
        gate = {"toState": "REAL_PREVIEW_READY"}
        observed: dict[str, str] = {}

        service = object.__new__(delivery.K2DeliveryService)
        service.composition = SimpleNamespace(
            compose_timeline_preview_v2=lambda *_args, **_kwargs: None
        )
        service.evidence = _Evidence()

        def existing(
            seen_workspace: str,
            seen_run_ref: str,
            gate_name: str,
            idempotency_key: str,
            request_digest: str,
        ):
            self.assertEqual((seen_workspace, seen_run_ref), (workspace, run_ref))
            self.assertEqual(gate_name, delivery.M13_EFFECT_COMPOSITION_GATE)
            observed["idempotencyKey"] = idempotency_key
            observed["requestDigest"] = request_digest
            return gate

        stored = {
            "timelineVersion": timeline,
            "compositionResult": composition,
            "previewCandidate": preview,
        }
        context = {
            "snapshot": SimpleNamespace(revisionToken="2" * 64),
            "run": {"payloadDigest": "5" * 64},
        }
        with (
            mock.patch.object(
                service,
                "_editing_timeline_preview_command",
                return_value=normalized,
            ),
            mock.patch.object(
                service, "_timeline_authority_context", return_value=context
            ),
            mock.patch.object(
                service, "_restore_editing_timeline", return_value=restored
            ),
            mock.patch.object(
                service,
                "_editing_preview_layout",
                return_value={"effectProfile": "M13_E4"},
            ),
            mock.patch.object(service, "_existing", side_effect=existing),
            mock.patch.object(
                service,
                "_validated_stored_effect_timeline_preview",
                return_value=stored,
            ),
            mock.patch.object(
                delivery,
                "validated_evidence_snapshot",
                return_value=SimpleNamespace(revisionToken="f" * 64),
            ),
        ):
            result = service.compose_editing_timeline_preview({})

        self.assertEqual(result["timelineVersion"], timeline.as_dict())
        self.assertEqual(result["compositionResult"], composition.as_dict())
        self.assertEqual(result["previewCandidate"], preview.as_dict())
        self.assertTrue(result["idempotentReplay"])
        self.assertEqual(
            observed["idempotencyKey"],
            _digest(
                {
                    "clientIdempotencyKey": normalized["idempotencyKey"],
                    "operationRef": normalized["operationRef"],
                    "stage": "m13-e4-editing-timeline-composition",
                }
            ),
        )
        self.assertEqual(
            observed["requestDigest"],
            _digest(
                {
                    "schemaVersion": "v5.m13-effect-preview-command.v4",
                    "command": normalized,
                    "deliveryId": delivery.TIMELINE_PREVIEW_DELIVERY_ID,
                }
            ),
        )

    def test_real_delivery_entrypoint_rejects_authority_drift_during_render(
        self,
    ) -> None:
        workspace = "workspace-m13-e4-preview-currentness"
        run_ref = "run-m13-e4-preview-currentness"
        timeline_ref = "timeline-version-m13-e4-preview-currentness"
        timeline_digest = "6" * 64
        normalized = {
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "expectedRunVersion": 9,
            "expectedEvidenceRevision": "7" * 64,
            "idempotencyKey": "m13-e4-preview-currentness-idempotency",
            "operationRef": "m13-e4-preview-currentness-operation",
            "timelineVersionRef": timeline_ref,
            "timelineVersionDigest": timeline_digest,
        }
        timeline = _Wire(
            {
                "timelineVersionRef": timeline_ref,
                "payloadDigest": timeline_digest,
            }
        )
        restored = {
            "timelineVersion": timeline,
            "versionHistory": [timeline],
        }
        before = {
            "compositionCommand": {"command": "before"},
            "resolvedArtifacts": {"subject": {"fileDigest": "8" * 64}},
        }
        after = deepcopy(before)
        after["resolvedArtifacts"]["subject"]["fileDigest"] = "9" * 64
        first_context = {
            "snapshot": SimpleNamespace(
                revisionToken=normalized["expectedEvidenceRevision"],
                currentState="REAL_VIDEO_READY",
            ),
            "run": {"payloadDigest": "a" * 64},
        }
        second_context = {
            "snapshot": SimpleNamespace(
                revisionToken=normalized["expectedEvidenceRevision"],
                currentState="REAL_VIDEO_READY",
            ),
            "run": {"payloadDigest": "a" * 64},
        }
        append = mock.Mock()
        service = object.__new__(delivery.K2DeliveryService)
        service.composition = SimpleNamespace(
            compose_timeline_preview_v2=mock.Mock(
                return_value={"rendered": True}
            )
        )
        service.evidence = SimpleNamespace(append_records_and_gate=append)
        service._clock = lambda: "2026-08-31T00:00:00Z"

        with (
            mock.patch.object(
                service,
                "_editing_timeline_preview_command",
                return_value=normalized,
            ),
            mock.patch.object(
                service,
                "_timeline_authority_context",
                side_effect=(first_context, second_context),
            ),
            mock.patch.object(
                service,
                "_restore_editing_timeline",
                side_effect=(restored, restored),
            ),
            mock.patch.object(
                service,
                "_editing_preview_layout",
                return_value={"effectProfile": "M13_E4"},
            ),
            mock.patch.object(service, "_existing", return_value=None),
            mock.patch.object(
                service,
                "_editing_effect_preview_projection",
                side_effect=(before, after),
            ),
        ):
            with self.assertRaisesRegex(
                StaleInputError,
                "authority changed during composition",
            ):
                service.compose_editing_timeline_preview({})

        service.composition.compose_timeline_preview_v2.assert_called_once_with(
            before["compositionCommand"],
            resolved_artifacts=before["resolvedArtifacts"],
        )
        append.assert_not_called()

    def test_real_delivery_entrypoint_preserves_exact_revision_during_render(
        self,
    ) -> None:
        workspace = "workspace-m13-e4-preview-revision"
        run_ref = "run-m13-e4-preview-revision"
        timeline_ref = "timeline-version-m13-e4-preview-revision"
        timeline_digest = "c" * 64
        normalized = {
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "expectedRunVersion": 11,
            "expectedEvidenceRevision": "d" * 64,
            "idempotencyKey": "m13-e4-preview-revision-idempotency",
            "operationRef": "m13-e4-preview-revision-operation",
            "timelineVersionRef": timeline_ref,
            "timelineVersionDigest": timeline_digest,
        }
        timeline = _Wire(
            {
                "timelineVersionRef": timeline_ref,
                "payloadDigest": timeline_digest,
            }
        )
        restored = {
            "timelineVersion": timeline,
            "versionHistory": [timeline],
        }
        projection = {
            "compositionCommand": {"command": "stable"},
            "resolvedArtifacts": {"subject": {"fileDigest": "e" * 64}},
        }
        first_context = {
            "snapshot": SimpleNamespace(
                revisionToken=normalized["expectedEvidenceRevision"],
                currentState="REAL_VIDEO_READY",
            ),
            "run": {"payloadDigest": "f" * 64},
        }
        second_context = {
            "snapshot": SimpleNamespace(
                revisionToken="0" * 64,
                currentState="REAL_VIDEO_READY",
            ),
            "run": {"payloadDigest": "f" * 64},
        }
        append = mock.Mock()
        service = object.__new__(delivery.K2DeliveryService)
        service.composition = SimpleNamespace(
            compose_timeline_preview_v2=mock.Mock(
                return_value={"rendered": True}
            )
        )
        service.evidence = SimpleNamespace(append_records_and_gate=append)
        service._clock = lambda: "2026-08-31T00:00:00Z"

        with (
            mock.patch.object(
                service,
                "_editing_timeline_preview_command",
                return_value=normalized,
            ),
            mock.patch.object(
                service,
                "_timeline_authority_context",
                side_effect=(first_context, second_context),
            ),
            mock.patch.object(
                service,
                "_restore_editing_timeline",
                side_effect=(restored, restored),
            ),
            mock.patch.object(
                service,
                "_editing_preview_layout",
                return_value={"effectProfile": "M13_E4"},
            ),
            mock.patch.object(service, "_existing", return_value=None),
            mock.patch.object(
                service,
                "_editing_effect_preview_projection",
                side_effect=(projection, deepcopy(projection)),
            ),
        ):
            with self.assertRaisesRegex(
                StaleInputError,
                "authority changed during composition",
            ):
                service.compose_editing_timeline_preview({})

        service.composition.compose_timeline_preview_v2.assert_called_once()
        append.assert_not_called()


if __name__ == "__main__":
    unittest.main()
