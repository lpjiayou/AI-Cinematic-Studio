"""V4 execution boundary delegating deterministic composition to V3."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from services.v3_render_core import DeterministicFfmpegComposer, RenderArtifactError


class CompositionExecutionError(RuntimeError):
    code = "worker_unavailable"


class V4CompositionExecutor:
    adapter_identity = "v4.local-composition-executor.v1"
    provenance = "LOCAL_EVIDENCE"

    def __init__(self, composer: DeterministicFfmpegComposer) -> None:
        self.composer = composer
        self.artifact_root = Path(composer.artifact_root).resolve()

    @classmethod
    def from_artifact_root(cls, artifact_root: Path | str) -> "V4CompositionExecutor":
        """Compose the V4 execution boundary without exposing V3 to V5 callers."""
        return cls(DeterministicFfmpegComposer(artifact_root))

    def compose(self, command: Mapping[str, Any]) -> dict[str, Any]:
        try:
            result = self.composer.compose(
                workspace_ref=command["workspaceRef"],
                run_ref=command["productionRunRef"],
                timeline_digest=command["timelineDigest"],
                items=command["items"],
                output=command["output"],
            )
        except (KeyError, TypeError, RenderArtifactError) as exc:
            raise CompositionExecutionError("V3 preview composition failed") from exc
        return {
            **result,
            "adapterIdentity": self.adapter_identity,
            "provenance": self.provenance,
            "gpuUsed": False,
            "publicationAllowed": False,
        }

    def finalize(self, command: Mapping[str, Any]) -> dict[str, Any]:
        try:
            result = self.composer.finalize(
                workspace_ref=command["workspaceRef"],
                run_ref=command["productionRunRef"],
                preview_storage_key=command["previewStorageKey"],
                master_key=command["masterKey"],
            )
        except (KeyError, TypeError, RenderArtifactError) as exc:
            raise CompositionExecutionError("V3 master finalization failed") from exc
        return {
            **result,
            "adapterIdentity": self.adapter_identity,
            "provenance": self.provenance,
            "gpuUsed": False,
            "publicationAllowed": False,
        }
