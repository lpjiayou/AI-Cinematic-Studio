"""Errors exposed by the V5 Core OS Asset Registry."""


class AssetRegistryError(Exception):
    """Base error for all Asset Registry failures."""


class ValidationError(AssetRegistryError, ValueError):
    """Raised when a caller supplies invalid input."""


class DuplicateAssetError(AssetRegistryError):
    """Raised when an Asset identifier is already registered."""


class AssetNotFoundError(AssetRegistryError, LookupError):
    """Raised when an Asset cannot be found."""
