"""V3 deterministic render primitives."""

from .composition import DeterministicFfmpegComposer, RenderArtifactError
from .digests import (
    DigestError,
    IMAGE_PIXEL_DIGEST_SPEC,
    VIDEO_PIXEL_DIGEST_SPEC,
    file_digest,
    file_sha256,
    image_digest_metadata,
    pixel_sha256,
    video_digest_metadata,
)

__all__ = [
    "DeterministicFfmpegComposer",
    "DigestError",
    "IMAGE_PIXEL_DIGEST_SPEC",
    "RenderArtifactError",
    "VIDEO_PIXEL_DIGEST_SPEC",
    "file_digest",
    "file_sha256",
    "image_digest_metadata",
    "pixel_sha256",
    "video_digest_metadata",
]
