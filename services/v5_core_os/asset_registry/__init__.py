"""Deprecated package surface retained only for fail-closed compatibility."""

from .engine import AssetRegistry
from .errors import (
    AssetNotFoundError,
    AssetRegistryDeprecatedError,
    AssetRegistryError,
    DuplicateAssetError,
    ValidationError,
)
from .models import Asset, AssetType, AssetVersion

__all__ = [
    "Asset",
    "AssetNotFoundError",
    "AssetRegistry",
    "AssetRegistryDeprecatedError",
    "AssetRegistryError",
    "AssetType",
    "AssetVersion",
    "DuplicateAssetError",
    "ValidationError",
]
