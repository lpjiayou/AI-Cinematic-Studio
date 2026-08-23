"""Immutable records returned by the V5 Core OS Asset Registry."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AssetType(Enum):
    """Broad Asset classification without format or processing semantics."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    OTHER = "other"


@dataclass(frozen=True)
class AssetVersion:
    """The immutable initial version registration for an Asset.

    version_id is opaque and scoped to its Asset. This MVP does not define
    later-version ordering or relationship semantics.
    """

    version_id: str
    asset_id: str
    registered_at: datetime


@dataclass(frozen=True)
class Asset:
    """An immutable Asset identity, type, and initial version record."""

    asset_id: str
    asset_type: AssetType
    initial_version: AssetVersion
    created_at: datetime
