"""Deterministic FFmpeg timeline composition owned by V3 Render Core."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping


class RenderArtifactError(RuntimeError):
    pass


def _scope_root(root: Path, workspace_ref: str, run_ref: str) -> Path:
    workspace_hash = sha256(workspace_ref.encode()).hexdigest()[:20]
    run_hash = sha256(run_ref.encode()).hexdigest()[:20]
    result = (root / workspace_hash / run_hash).resolve()
    if root not in result.parents:
        raise RenderArtifactError("composition scope escaped artifact root")
    result.mkdir(parents=True, exist_ok=True)
    return result


def _safe_input(root: Path, storage_key: str) -> Path:
    if not isinstance(storage_key, str) or not storage_key:
        raise RenderArtifactError("composition input storage key is invalid")
    path = (root / storage_key).resolve()
    if root not in path.parents or not path.is_file():
        raise RenderArtifactError("composition input escaped artifact root")
    return path


def _probe(path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-count_frames", "-show_streams",
                "-show_format", "-of", "json", str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise RenderArtifactError("composed artifact probe failed") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list) or not streams:
        raise RenderArtifactError("composed artifact has no streams")
    return {
        "streams": [
            {
                key: stream.get(key)
                for key in (
                    "codec_type", "codec_name", "width", "height", "pix_fmt",
                    "avg_frame_rate", "nb_frames", "nb_read_frames", "sample_rate",
                    "channels", "duration",
                )
                if stream.get(key) is not None
            }
            for stream in streams
            if isinstance(stream, Mapping)
        ],
        "formatName": payload.get("format", {}).get("format_name"),
        "durationSeconds": payload.get("format", {}).get("duration"),
    }


class DeterministicFfmpegComposer:
    composer_identity = "v3.deterministic-ffmpeg-composer.v1"

    def __init__(self, artifact_root: Path | str) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def _artifact(self, path: Path) -> dict[str, Any]:
        content = path.read_bytes()
        return {
            "internalPath": str(path),
            "storageKey": str(path.relative_to(self.artifact_root)),
            "byteSize": len(content),
            "sha256": sha256(content).hexdigest(),
            "probe": _probe(path),
            "composerIdentity": self.composer_identity,
        }

    def compose(
        self,
        *,
        workspace_ref: str,
        run_ref: str,
        timeline_digest: str,
        items: list[Mapping[str, Any]],
        output: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not items:
            raise RenderArtifactError("timeline has no composition items")
        root = _scope_root(self.artifact_root, workspace_ref, run_ref)
        destination = root / "composition" / f"preview-{timeline_digest}.mp4"
        if destination.is_file():
            return self._artifact(destination)
        videos: list[Path] = []
        audios: list[Path] = []
        for item in items:
            videos.append(_safe_input(self.artifact_root, item["videoStorageKey"]))
            audios.append(_safe_input(self.artifact_root, item["audioStorageKey"]))
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.stem}.part.mp4")
        command = ["ffmpeg", "-v", "error"]
        for video, audio in zip(videos, audios):
            command.extend(["-i", str(video), "-i", str(audio)])
        concat_inputs = "".join(
            f"[{index * 2}:v:0][{index * 2 + 1}:a:0]"
            for index in range(len(items))
        )
        command.extend(
            [
                "-filter_complex",
                f"{concat_inputs}concat=n={len(items)}:v=1:a=1[outv][outa]",
                "-map", "[outv]", "-map", "[outa]", "-r",
                str(output["frameRate"]), "-c:v", "libx264", "-preset",
                "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a",
                "128k", "-movflags", "+faststart", "-y", str(temporary),
            ]
        )
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=180)
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            if temporary.exists():
                temporary.unlink()
            raise RenderArtifactError("FFmpeg timeline composition failed") from exc
        probe = _probe(temporary)
        video_streams = [
            stream for stream in probe["streams"] if stream.get("codec_type") == "video"
        ]
        audio_streams = [
            stream for stream in probe["streams"] if stream.get("codec_type") == "audio"
        ]
        if len(video_streams) != 1 or len(audio_streams) != 1:
            temporary.unlink(missing_ok=True)
            raise RenderArtifactError("preview stream layout is invalid")
        video = video_streams[0]
        frame_count = video.get("nb_read_frames") or video.get("nb_frames")
        try:
            actual_frames = int(frame_count)
        except (TypeError, ValueError):
            actual_frames = -1
        if (
            video.get("width") != output["width"]
            or video.get("height") != output["height"]
            or actual_frames != output["totalFrames"]
        ):
            temporary.unlink(missing_ok=True)
            raise RenderArtifactError("preview frame contract is invalid")
        temporary.replace(destination)
        return self._artifact(destination)

    def finalize(
        self,
        *,
        workspace_ref: str,
        run_ref: str,
        preview_storage_key: str,
        master_key: str,
    ) -> dict[str, Any]:
        source = _safe_input(self.artifact_root, preview_storage_key)
        root = _scope_root(self.artifact_root, workspace_ref, run_ref)
        if not isinstance(master_key, str) or len(master_key) != 64:
            raise RenderArtifactError("master key is invalid")
        destination = root / "masters" / f"episode-master-{master_key}.mp4"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            temporary = destination.with_name(f"{destination.stem}.part.mp4")
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
        return self._artifact(destination)
