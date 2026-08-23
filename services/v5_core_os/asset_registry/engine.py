"""Deprecated compatibility surface for the former process-local registry.

AssetVersion authority now lives exclusively in the Episode Production
canonical evidence journal. Keeping a writable in-memory registry would make
asset identity depend on process lifetime and create a second authority.
"""

from typing import Any

from .errors import AssetRegistryDeprecatedError


class AssetRegistry:
    """Fail-closed tombstone for the retired M003 in-memory authority."""

    DEPRECATION = (
        "AssetRegistry is retired; use "
        "episode_production.CanonicalAssetVersionAuthority"
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    @classmethod
    def _retired(cls) -> None:
        raise AssetRegistryDeprecatedError(cls.DEPRECATION)

    def create_asset(self, **kwargs: Any) -> Any:
        del kwargs
        self._retired()

    def get_asset(self, asset_id: str) -> Any:
        del asset_id
        self._retired()

    def list_assets(self) -> tuple[()]:
        self._retired()


__all__ = ["AssetRegistry"]
