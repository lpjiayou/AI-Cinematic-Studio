"""V3 deterministic render primitives."""

from .composition import DeterministicFfmpegComposer, RenderArtifactError
from .digests import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    DigestError,
    IMAGE_PIXEL_DIGEST_SPEC,
    VIDEO_PIXEL_DIGEST_SPEC,
    decoded_frame_pixel_digest_metadata,
    file_digest,
    file_sha256,
    image_digest_metadata,
    pixel_sha256,
    video_digest_metadata,
)

__all__ = [
    "DeterministicFfmpegComposer",
    "DECODED_FRAME_PIXEL_DIGEST_SPEC_V2",
    "DigestError",
    "IMAGE_PIXEL_DIGEST_SPEC",
    "RenderArtifactError",
    "VIDEO_PIXEL_DIGEST_SPEC",
    "decoded_frame_pixel_digest_metadata",
    "file_digest",
    "file_sha256",
    "image_digest_metadata",
    "pixel_sha256",
    "video_digest_metadata",
]
