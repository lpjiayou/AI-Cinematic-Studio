"""Dependency-free in-memory foundation for the V5 Asset Registry MVP."""

from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Dict, Optional, Sequence

from .errors import AssetNotFoundError, DuplicateAssetError, ValidationError
from .models import Asset, AssetType, AssetVersion

Clock = Callable[[], datetime]

MAX_IDENTIFIER_LENGTH = 128


class AssetRegistry:
    """Create, query, and list process-local Asset registrations.

    Within one registry instance, V5 is the single writer for Asset identity,
    broad type, and initial version-registration facts created here. This MVP
    makes no claim of authority over Asset content or external systems.
    """

    def __init__(self, *, clock: Optional[Clock] = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._assets: Dict[str, Asset] = {}
        self._lock = RLock()

    def create_asset(
        self,
        *,
        asset_id: str,
        asset_type: AssetType,
        version_id: str,
    ) -> Asset:
        """Register an Asset and its immutable initial version."""

        normalized_asset_id = self._identifier(asset_id, "asset_id")
        normalized_version_id = self._identifier(version_id, "version_id")
        if not isinstance(asset_type, AssetType):
            raise ValidationError("asset_type must be an AssetType")

        with self._lock:
            if normalized_asset_id in self._assets:
                raise DuplicateAssetError(
                    "Asset already exists: {}".format(normalized_asset_id)
                )

            timestamp = self._timestamp()
            initial_version = AssetVersion(
                version_id=normalized_version_id,
                asset_id=normalized_asset_id,
                registered_at=timestamp,
            )
            asset = Asset(
                asset_id=normalized_asset_id,
                asset_type=asset_type,
                initial_version=initial_version,
                created_at=timestamp,
            )
            self._assets[normalized_asset_id] = asset
            return asset

    def get_asset(self, asset_id: str) -> Asset:
        """Return an Asset by its opaque identifier."""

        normalized_asset_id = self._identifier(asset_id, "asset_id")
        with self._lock:
            try:
                return self._assets[normalized_asset_id]
            except KeyError as error:
                raise AssetNotFoundError(
                    "Asset not found: {}".format(normalized_asset_id)
                ) from error

    def list_assets(self) -> Sequence[Asset]:
        """Return an immutable snapshot without an ordering promise."""

        with self._lock:
            return tuple(self._assets.values())

    def _timestamp(self) -> datetime:
        timestamp = self._clock()
        if not isinstance(timestamp, datetime):
            raise ValidationError("clock must return a datetime")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValidationError("clock must return a timezone-aware datetime")
        return timestamp.astimezone(timezone.utc)

    @staticmethod
    def _identifier(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValidationError("{} must be a string".format(field_name))
        if not value or value != value.strip():
            raise ValidationError(
                "{} must be non-empty and contain no surrounding whitespace".format(
                    field_name
                )
            )
        if len(value) > MAX_IDENTIFIER_LENGTH:
            raise ValidationError(
                "{} must not exceed {} characters".format(
                    field_name,
                    MAX_IDENTIFIER_LENGTH,
                )
            )
        if not value.isprintable() or any(character.isspace() for character in value):
            raise ValidationError(
                "{} must contain printable, non-whitespace characters only".format(
                    field_name
                )
            )
        return value
