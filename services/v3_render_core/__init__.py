"""V3 deterministic render primitives."""

from .composition import DeterministicFfmpegComposer, RenderArtifactError
from .digests import (
    CANONICAL_PCM_CHANNEL_COUNT,
    CANONICAL_PCM_SAMPLE_RATE,
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    DigestError,
    IMAGE_PIXEL_DIGEST_SPEC,
    PCM_CONTENT_DIGEST_SPEC,
    VIDEO_PIXEL_DIGEST_SPEC,
    canonical_pcm_digest_metadata,
    decoded_frame_pixel_digest_metadata,
    file_digest,
    file_sha256,
    image_digest_metadata,
    pixel_sha256,
    video_digest_metadata,
)

__all__ = [
    "CANONICAL_PCM_CHANNEL_COUNT",
    "CANONICAL_PCM_SAMPLE_RATE",
    "DeterministicFfmpegComposer",
    "DECODED_FRAME_PIXEL_DIGEST_SPEC_V2",
    "DigestError",
    "IMAGE_PIXEL_DIGEST_SPEC",
    "PCM_CONTENT_DIGEST_SPEC",
    "RenderArtifactError",
    "VIDEO_PIXEL_DIGEST_SPEC",
    "canonical_pcm_digest_metadata",
    "decoded_frame_pixel_digest_metadata",
    "file_digest",
    "file_sha256",
    "image_digest_metadata",
    "pixel_sha256",
    "video_digest_metadata",
]
