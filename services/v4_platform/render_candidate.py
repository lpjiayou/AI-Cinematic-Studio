"""V4 sealed adapter for M13 CPU-only, non-publishing render candidates."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Mapping

from services.v3_render_core.render_candidate import (
    DeterministicRenderCandidateExecutor,
    RENDERER_IDENTITY,
    RENDERER_VERSION,
    build_render_core_request,
    build_video_composition_plan,
)


RENDER_EXECUTION_REQUEST_SCHEMA_VERSION = "v4.m13-render-execution-request.v1"
RENDER_EXECUTION_RESULT_SCHEMA_VERSION = "v4.m13-render-execution-result.v1"

_RAW_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,511}\Z")
_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "executionRequestRef",
        "timelineVersionRef",
        "timelineVersionDigest",
        "compositionVersionRef",
        "compositionVersionDigest",
        "renderManifestRef",
        "renderManifestDigest",
        "allInputBindingsDigest",
        "compositionCommandDigest",
        "runtimeBindingDigest",
        "outputArtifactBindingRef",
        "renderProfile",
        "publicationAllowed",
        "payloadDigest",
    }
)
_REQUEST_COMMAND_FIELDS = _REQUEST_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)
_PROFILE_FIELDS = frozenset(
    {
        "outputProfile",
        "videoEncoding",
        "colorMetadata",
        "audioEncoding",
        "subtitleMode",
        "subtitleTimingDigest",
        "subtitleFontAssetVersionRef",
        "subtitleFontAssetVersionDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegBinaryDigest",
        "ffprobeBinaryDigest",
    }
)
_FORBIDDEN_REQUEST_PARTS = (
    "path",
    "storagekey",
    "filter",
    "argv",
    "shellcommand",
    "environmentoverride",
    "runtimebinary",
    "modelpath",
    "downloadurl",
    "outputpath",
    "masterstate",
    "exportstate",
)


class RenderExecutionError(RuntimeError):
    pass


class RenderExecutionRequestError(RenderExecutionError):
    pass


class RenderExecutionAssetError(RenderExecutionError):
    pass


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RenderExecutionRequestError("render request is not canonical JSON") from exc


def _closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RenderExecutionRequestError(f"{label} fields are invalid")
    result = deepcopy(dict(value))
    _reject_floats(result)
    return result


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise RenderExecutionRequestError("float render authority is forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RenderExecutionRequestError("render object key is invalid")
            _reject_floats(item)
    elif isinstance(value, list):
        for item in value:
            _reject_floats(item)


def _ref(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or _REF.fullmatch(value) is None
        or value.startswith(("/", "\\"))
        or ".." in value.split("/")
        or "://" in value
    ):
        raise RenderExecutionRequestError(f"{label} is invalid")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _RAW_DIGEST.fullmatch(value) is None:
        raise RenderExecutionRequestError(f"{label} is invalid")
    return value


def _reject_private_request_claims(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            folded = key.replace("_", "").replace("-", "").lower()
            if any(part in folded for part in _FORBIDDEN_REQUEST_PARTS):
                raise RenderExecutionRequestError(f"{key} is forbidden")
            _reject_private_request_claims(item)
    elif isinstance(value, list):
        for item in value:
            _reject_private_request_claims(item)


def _private_free(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _private_free(item)
            for key, item in value.items()
            if key.replace("_", "").replace("-", "").lower()
            not in {
                "storagekey",
                "internalpath",
                "outputstoragekey",
                "path",
            }
        }
    if isinstance(value, list):
        return [_private_free(item) for item in value]
    return deepcopy(value)


def render_input_bindings_digest(
    *,
    composition_version: Mapping[str, Any],
    composition_command: Mapping[str, Any],
    subtitle_cues: list[Mapping[str, Any]],
) -> str:
    """Bind every immutable source while excluding internal locators."""

    value = {
        "schemaVersion": "v4.m13-render-input-bindings.v1",
        "compositionVersionDigest": composition_version.get("payloadDigest"),
        "compositionGraphDigest": composition_version.get("compositionGraphDigest"),
        "videoTrackBindings": composition_version.get("videoTrackBindings"),
        "audioTrackBindings": composition_version.get("audioTrackBindings"),
        "subtitleTrackBindings": composition_version.get("subtitleTrackBindings"),
        "effectTrackBindings": composition_version.get("effectTrackBindings"),
        "compositionCommand": _private_free(composition_command),
        "subtitleCues": deepcopy(subtitle_cues),
    }
    return sha256(_canonical_json(value)).hexdigest()


def composition_command_digest(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json(_private_free(value))).hexdigest()


def runtime_binding_digest(profile: Mapping[str, Any]) -> str:
    return sha256(
        _canonical_json(
            {
                "schemaVersion": "v4.m13-render-runtime-binding.v1",
                **{
                    field: profile.get(field)
                    for field in (
                        "rendererIdentity",
                        "rendererVersion",
                        "ffmpegBinaryDigest",
                        "ffprobeBinaryDigest",
                    )
                },
            }
        )
    ).hexdigest()


def validate_render_execution_request(value: Any) -> dict[str, Any]:
    request = _closed(value, _REQUEST_FIELDS, "render execution request")
    supplied = request.pop("payloadDigest")
    _digest(supplied, "payloadDigest")
    if supplied != sha256(_canonical_json(request)).hexdigest():
        raise RenderExecutionRequestError("render execution request seal is invalid")
    request["payloadDigest"] = supplied
    if (
        request["schemaVersion"] != RENDER_EXECUTION_REQUEST_SCHEMA_VERSION
        or request["publicationAllowed"] is not False
    ):
        raise RenderExecutionRequestError("render execution boundary is invalid")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "executionRequestRef",
        "timelineVersionRef",
        "compositionVersionRef",
        "renderManifestRef",
        "outputArtifactBindingRef",
    ):
        _ref(request[field], field)
    for field in (
        "timelineVersionDigest",
        "compositionVersionDigest",
        "renderManifestDigest",
        "allInputBindingsDigest",
        "compositionCommandDigest",
        "runtimeBindingDigest",
    ):
        _digest(request[field], field)
    profile = _closed(request["renderProfile"], _PROFILE_FIELDS, "renderProfile")
    for field in ("rendererIdentity", "rendererVersion"):
        _ref(profile[field], field)
    for field in ("ffmpegBinaryDigest", "ffprobeBinaryDigest"):
        _digest(profile[field], field)
    if runtime_binding_digest(profile) != request["runtimeBindingDigest"]:
        raise RenderExecutionRequestError("runtime binding digest is stale")
    _reject_private_request_claims(request)
    request["renderProfile"] = profile
    return request


def build_render_execution_request(command: Mapping[str, Any]) -> dict[str, Any]:
    selected = _closed(
        command, _REQUEST_COMMAND_FIELDS, "render execution request command"
    )
    _reject_private_request_claims(selected)
    result = {
        "schemaVersion": RENDER_EXECUTION_REQUEST_SCHEMA_VERSION,
        **selected,
    }
    result["payloadDigest"] = sha256(_canonical_json(result)).hexdigest()
    return validate_render_execution_request(result)


def _descriptor_digest(descriptor: int) -> tuple[os.stat_result, str]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
        raise RenderExecutionAssetError("subtitle FONT staged file is invalid")
    digest = sha256()
    offset = 0
    while True:
        block = os.pread(descriptor, 1024 * 1024, offset)
        if not block:
            break
        digest.update(block)
        offset += len(block)
    after = os.fstat(descriptor)
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_size",
        "st_mtime_ns",
    )
    if any(
        getattr(before, field) != getattr(after, field)
        for field in stable_fields
    ):
        raise RenderExecutionAssetError("subtitle FONT staged file changed")
    return after, digest.hexdigest()


def _publish_staged_font_no_replace(
    *,
    root: Path,
    directory: Path,
    temporary_path: Path,
    output_name: str,
    expected_digest: str,
    expected_byte_size: int,
) -> Path:
    """Publish a held regular FONT through no-follow directory descriptors."""

    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise RenderExecutionAssetError("subtitle FONT staging escaped root") from exc
    if (
        not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or Path(output_name).name != output_name
    ):
        raise RenderExecutionAssetError("subtitle FONT staging path is invalid")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or directory_flag is None:
        raise RenderExecutionAssetError(
            "subtitle FONT no-follow staging is unavailable"
        )
    directory_flags = os.O_RDONLY | no_follow | directory_flag
    file_flags = os.O_RDONLY | no_follow
    if hasattr(os, "O_CLOEXEC"):
        directory_flags |= os.O_CLOEXEC
        file_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        file_flags |= os.O_NONBLOCK
    descriptors: list[int] = []
    source_descriptor: int | None = None
    existing_descriptor: int | None = None
    try:
        source_descriptor = os.open(temporary_path, file_flags)
        source_state, source_digest = _descriptor_digest(source_descriptor)
        if (
            source_state.st_size != expected_byte_size
            or source_digest != expected_digest
        ):
            raise RenderExecutionAssetError("subtitle FONT staged digest changed")
        current_descriptor = os.open(root, directory_flags)
        descriptors.append(current_descriptor)
        for part in relative.parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=current_descriptor)
            except FileExistsError:
                pass
            next_descriptor = os.open(
                part, directory_flags, dir_fd=current_descriptor
            )
            descriptors.append(next_descriptor)
            current_descriptor = next_descriptor
        try:
            os.link(
                temporary_path,
                output_name,
                dst_dir_fd=current_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            existing_descriptor = os.open(
                output_name, file_flags, dir_fd=current_descriptor
            )
            existing_state, existing_digest = _descriptor_digest(
                existing_descriptor
            )
            entry = os.stat(
                output_name,
                dir_fd=current_descriptor,
                follow_symlinks=False,
            )
            if (
                existing_state.st_dev != entry.st_dev
                or existing_state.st_ino != entry.st_ino
                or existing_state.st_size != expected_byte_size
                or existing_digest != expected_digest
            ):
                raise RenderExecutionAssetError(
                    "subtitle FONT staging collision"
                )
        else:
            entry = os.stat(
                output_name,
                dir_fd=current_descriptor,
                follow_symlinks=False,
            )
            source_after, source_digest_after = _descriptor_digest(
                source_descriptor
            )
            if (
                entry.st_dev != source_after.st_dev
                or entry.st_ino != source_after.st_ino
                or entry.st_size != expected_byte_size
                or source_digest_after != expected_digest
            ):
                try:
                    os.unlink(output_name, dir_fd=current_descriptor)
                except OSError:
                    pass
                raise RenderExecutionAssetError(
                    "subtitle FONT publication changed"
                )
            os.fsync(current_descriptor)
    except RenderExecutionAssetError:
        raise
    except OSError as exc:
        raise RenderExecutionAssetError("subtitle FONT staging failed") from exc
    finally:
        if existing_descriptor is not None:
            os.close(existing_descriptor)
        if source_descriptor is not None:
            os.close(source_descriptor)
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
    return directory / output_name


def _stage_current_font(
    *,
    artifact_root: Path,
    workspace_ref: str,
    production_run_ref: str,
    projection: Mapping[str, Any],
    font_asset_authority: Any,
    required_text: str,
) -> dict[str, Any]:
    require_current = getattr(
        font_asset_authority, "require_current_font_asset_projection", None
    )
    open_current = getattr(font_asset_authority, "open_current_font_file", None)
    if not callable(require_current) or not callable(open_current):
        raise RenderExecutionAssetError("current subtitle FONT authority is unavailable")
    asset = projection.get("fontAssetVersion")
    validation = projection.get("fontTechnicalValidation")
    if not isinstance(asset, Mapping) or not isinstance(validation, Mapping):
        raise RenderExecutionAssetError("subtitle FONT projection is invalid")
    try:
        current = require_current(
            workspace_ref,
            production_run_ref,
            asset["assetVersionRef"],
            asset["payloadDigest"],
            required_text=required_text,
        )
    except Exception as exc:
        raise RenderExecutionAssetError("subtitle FONT projection is stale") from exc
    if current != projection:
        raise RenderExecutionAssetError("subtitle FONT projection changed")
    try:
        descriptor = open_current(
            projection["storageBindingRef"],
            expected_file_digest=asset["fileDigest"],
            expected_byte_size=asset["byteSize"],
            declared_media_type=asset["mediaType"],
            required_text=required_text,
        )
    except Exception as exc:
        raise RenderExecutionAssetError("subtitle FONT file is stale") from exc
    suffix = ".ttf" if asset["fontFormat"] == "TTF" else ".otf"
    workspace_hash = sha256(workspace_ref.encode("utf-8")).hexdigest()[:20]
    run_hash = sha256(production_run_ref.encode("utf-8")).hexdigest()[:20]
    directory = artifact_root / workspace_hash / run_hash / "render-inputs"
    destination = directory / f"subtitle-font-{asset['fileDigest']}{suffix}"
    temporary_path: Path | None = None
    try:
        source_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(source_before.st_mode)
            or source_before.st_size != asset["byteSize"]
        ):
            raise RenderExecutionAssetError("subtitle FONT descriptor is invalid")
        os.lseek(descriptor, 0, os.SEEK_SET)
        with tempfile.NamedTemporaryFile(
            prefix=".subtitle-font-",
            suffix=suffix,
            dir=artifact_root,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            digest = sha256()
            remaining = asset["byteSize"]
            while remaining:
                block = os.read(descriptor, min(1024 * 1024, remaining))
                if not block:
                    raise RenderExecutionAssetError("subtitle FONT ended early")
                digest.update(block)
                temporary.write(block)
                remaining -= len(block)
            if os.read(descriptor, 1):
                raise RenderExecutionAssetError("subtitle FONT size changed")
            temporary.flush()
            os.fsync(temporary.fileno())
        source_after = os.fstat(descriptor)
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(source_before, field) != getattr(source_after, field)
            for field in stable_fields
        ):
            raise RenderExecutionAssetError("subtitle FONT changed while staging")
        if digest.hexdigest() != asset["fileDigest"]:
            raise RenderExecutionAssetError("subtitle FONT digest changed")
        destination = _publish_staged_font_no_replace(
            root=artifact_root,
            directory=directory,
            temporary_path=temporary_path,
            output_name=destination.name,
            expected_digest=asset["fileDigest"],
            expected_byte_size=asset["byteSize"],
        )
        return {
            "storageKey": str(destination.relative_to(artifact_root)),
            "fileDigest": asset["fileDigest"],
            "byteSize": asset["byteSize"],
            "fontFamily": validation["fontFamily"],
        }
    finally:
        os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _composition_video_plan(
    *,
    composition_version: Mapping[str, Any],
    composition_command: Mapping[str, Any],
) -> dict[str, Any]:
    base = composition_command.get("baseVideo")
    output = composition_command.get("output")
    bindings = composition_version.get("videoTrackBindings")
    if (
        not isinstance(base, Mapping)
        or not isinstance(output, Mapping)
        or not isinstance(bindings, list)
    ):
        raise RenderExecutionRequestError("Composition video plan is unavailable")
    clips: list[dict[str, Any]] = []
    for raw in bindings:
        if not isinstance(raw, Mapping):
            raise RenderExecutionRequestError("Composition video binding is invalid")
        if raw.get("enabled") is not True or raw.get("trackEnabled") is not True:
            continue
        source = raw.get("sourceBinding")
        transform = raw.get("transform")
        speed = raw.get("speed")
        masks = raw.get("maskBindings")
        if (
            not isinstance(source, Mapping)
            or not isinstance(transform, Mapping)
            or not isinstance(speed, Mapping)
            or not isinstance(masks, list)
            or source.get("assetVersionRef") != base.get("assetVersionRef")
            or source.get("assetVersionDigest")
            != base.get("assetVersionDigest")
            or transform.get("perspectiveMode") != "NONE"
        ):
            raise RenderExecutionRequestError(
                "Composition video binding cannot use the current source projection"
            )

        def transition(field: str) -> dict[str, Any] | None:
            value = raw.get(field)
            if value is None:
                return None
            if not isinstance(value, Mapping):
                raise RenderExecutionRequestError(
                    "Composition video transition is invalid"
                )
            return {
                "kind": value.get("transitionKind"),
                "durationFrames": value.get("durationFrames"),
                "curve": value.get("curve"),
                "alignment": value.get("alignment"),
            }

        mask_digests = []
        for mask in masks:
            if not isinstance(mask, Mapping) or not isinstance(
                mask.get("payloadDigest"), str
            ):
                raise RenderExecutionRequestError(
                    "Composition video mask binding is invalid"
                )
            mask_digests.append(mask["payloadDigest"])
        clips.append(
            {
                "clipRef": raw.get("clipRef"),
                "clipDigest": raw.get("clipDigest"),
                "timelineStartFrameInclusive": raw.get(
                    "timelineStartFrameInclusive"
                ),
                "timelineEndFrameExclusive": raw.get(
                    "timelineEndFrameExclusive"
                ),
                "sourceInFrameInclusive": source.get(
                    "sourceInFrameInclusive"
                ),
                "sourceOutFrameExclusive": source.get(
                    "sourceOutFrameExclusive"
                ),
                "layer": raw.get("layer"),
                "zOrder": raw.get("zOrder"),
                "opacity": raw.get("opacity"),
                "blendMode": raw.get("blendMode"),
                "transitionIn": transition("transitionIn"),
                "transitionOut": transition("transitionOut"),
                "speed": {
                    "numerator": speed.get("numerator"),
                    "denominator": speed.get("denominator"),
                },
                "transform": {
                    field: deepcopy(transform.get(field))
                    for field in (
                        "positionXPixels",
                        "positionYPixels",
                        "scaleX",
                        "scaleY",
                        "rotationMilliDegrees",
                        "anchorXPixels",
                        "anchorYPixels",
                        "opacity",
                    )
                },
                "maskBindingDigests": mask_digests,
            }
        )
    clips.sort(
        key=lambda item: (
            item["layer"],
            item["zOrder"],
            item["timelineStartFrameInclusive"],
            item["clipRef"],
        )
    )
    return build_video_composition_plan(
        {
            "canvasWidth": output.get("width"),
            "canvasHeight": output.get("height"),
            "frameRate": deepcopy(output.get("frameRate")),
            "totalFrames": output.get("totalFrames"),
            "maskLayerPlanDigest": composition_version.get(
                "maskLayerPlanDigest"
            ),
            "clips": clips,
        }
    )


class V4RenderCandidateExecutor:
    def __init__(
        self,
        artifact_root: Path | str,
        composition_executor: Any,
        *,
        font_asset_authority: Any | None = None,
    ) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.composition_executor = composition_executor
        self.font_asset_authority = font_asset_authority

    def execute(
        self,
        execution_request: Mapping[str, Any],
        *,
        composition_version: Mapping[str, Any],
        composition_command: Mapping[str, Any],
        resolved_artifacts: Mapping[str, Any],
        subtitle_cues: list[Mapping[str, Any]],
        font_projection: Mapping[str, Any] | None,
        font_required_text: str | None,
    ) -> dict[str, Any]:
        request = validate_render_execution_request(execution_request)
        if (
            request["compositionVersionDigest"]
            != composition_version.get("payloadDigest")
            or request["compositionVersionRef"]
            != composition_version.get("compositionVersionRef")
            or request["timelineVersionRef"]
            != composition_command.get("timelineVersionRef")
            or request["timelineVersionDigest"]
            != composition_command.get("timelineVersionDigest")
            or request["compositionCommandDigest"]
            != composition_command_digest(composition_command)
            or request["allInputBindingsDigest"]
            != render_input_bindings_digest(
                composition_version=composition_version,
                composition_command=composition_command,
                subtitle_cues=subtitle_cues,
            )
        ):
            raise RenderExecutionRequestError("render input bindings are stale")
        video_plan = _composition_video_plan(
            composition_version=composition_version,
            composition_command=composition_command,
        )
        try:
            preview = self.composition_executor.compose_timeline_preview_v2(
                composition_command,
                resolved_artifacts=resolved_artifacts,
            )
        except Exception as exc:
            raise RenderExecutionError("full Timeline render execution failed") from exc
        if (
            not isinstance(preview, Mapping)
            or preview.get("timelineVersionRef") != request["timelineVersionRef"]
            or preview.get("timelineVersionDigest") != request["timelineVersionDigest"]
            or preview.get("publicationAllowed") is not False
            or preview.get("providerUsed") is not False
            or preview.get("gpuUsed") is not False
            or not isinstance(preview.get("outputDigest"), Mapping)
            or not isinstance(preview.get("outputMediaProbe"), Mapping)
        ):
            raise RenderExecutionError("full Timeline render result is stale")
        profile = request["renderProfile"]
        subtitle_font = None
        if profile["subtitleMode"] == "BURN_IN":
            if (
                font_projection is None
                or not isinstance(font_required_text, str)
                or not font_required_text
            ):
                raise RenderExecutionAssetError("BURN_IN subtitle FONT is unavailable")
            subtitle_font = _stage_current_font(
                artifact_root=self.artifact_root,
                workspace_ref=request["workspaceRef"],
                production_run_ref=request["productionRunRef"],
                projection=font_projection,
                font_asset_authority=self.font_asset_authority,
                required_text=font_required_text,
            )
        low_profile = {
            field: deepcopy(profile[field])
            for field in (
                "outputProfile",
                "videoEncoding",
                "colorMetadata",
                "audioEncoding",
                "subtitleMode",
                "subtitleTimingDigest",
                "rendererIdentity",
                "rendererVersion",
                "ffmpegBinaryDigest",
                "ffprobeBinaryDigest",
            )
        }
        low_request = build_render_core_request(
            {
                "executionRequestRef": request["executionRequestRef"],
                "executionRequestDigest": request["payloadDigest"],
                "workspaceRef": request["workspaceRef"],
                "productionRunRef": request["productionRunRef"],
                "outputArtifactBindingRef": request["outputArtifactBindingRef"],
                "sourceArtifact": {
                    "storageKey": preview["outputStorageKey"],
                    "byteSize": preview["outputByteSize"],
                    "fileDigest": preview["outputDigest"]["fileDigest"],
                    "decodedFramePixelDigest": preview["outputDigest"][
                        "decodedFramePixelDigest"
                    ],
                    "decodedFramePixelDigestSpec": preview["outputDigest"][
                        "decodedFramePixelDigestSpec"
                    ],
                    "pcmContentDigest": preview["outputDigest"]["pcmContentDigest"],
                    "pcmContentDigestSpec": preview["outputDigest"]["pcmDigestSpec"],
                    "mediaProbe": deepcopy(preview["outputMediaProbe"]),
                },
                "videoCompositionPlan": video_plan,
                "renderProfile": low_profile,
                "subtitleCues": deepcopy(subtitle_cues),
                "subtitleFont": subtitle_font,
                "publicationAllowed": False,
            }
        )
        try:
            result = DeterministicRenderCandidateExecutor(
                self.artifact_root
            ).render(low_request)
        except Exception as exc:
            raise RenderExecutionError("V3 deterministic final render failed") from exc
        if (
            result.get("schemaVersion") != "v3.m13-render-core-result.v1"
            or result.get("executionRequestRef") != request["executionRequestRef"]
            or result.get("executionRequestDigest") != request["payloadDigest"]
            or result.get("outputArtifactBindingRef")
            != request["outputArtifactBindingRef"]
            or result.get("rendererIdentity") != RENDERER_IDENTITY
            or result.get("rendererVersion") != RENDERER_VERSION
            or result.get("ffmpegBinaryDigest") != profile["ffmpegBinaryDigest"]
            or result.get("ffprobeBinaryDigest") != profile["ffprobeBinaryDigest"]
            or result.get("gpuUsed") is not False
            or result.get("providerUsed") is not False
            or result.get("publicationAllowed") is not False
        ):
            raise RenderExecutionError("V3 deterministic render result is stale")
        return {
            **deepcopy(dict(result)),
            "schemaVersion": RENDER_EXECUTION_RESULT_SCHEMA_VERSION,
            "executionRequest": deepcopy(request),
            "v3ExecutionRequestDigest": low_request["payloadDigest"],
            "previewCompositionResultDigest": preview["payloadDigest"],
        }

    def inspect(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        storage_binding_ref: str,
        expected: Mapping[str, Any],
    ) -> dict[str, Any]:
        return DeterministicRenderCandidateExecutor(self.artifact_root).inspect(
            workspace_ref=workspace_ref,
            production_run_ref=production_run_ref,
            storage_binding_ref=storage_binding_ref,
            expected=expected,
        )


__all__ = [
    "RENDER_EXECUTION_REQUEST_SCHEMA_VERSION",
    "RENDER_EXECUTION_RESULT_SCHEMA_VERSION",
    "RenderExecutionAssetError",
    "RenderExecutionError",
    "RenderExecutionRequestError",
    "V4RenderCandidateExecutor",
    "build_render_execution_request",
    "composition_command_digest",
    "render_input_bindings_digest",
    "runtime_binding_digest",
    "validate_render_execution_request",
]
