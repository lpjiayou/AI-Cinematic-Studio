"""V5 authoritative single-episode production root boundary."""

from .authority import (
    IdentityReferenceAuthorityPort,
    RejectingIdentityReferenceAuthority,
    StaticIdentityReferenceAuthority,
)

from .foundation import (
    EpisodeProductionService,
    InMemoryEpisodeProductionAdapter,
    SqliteEpisodeProductionAdapter,
)
from .public import (
    EpisodeProductionPublicBoundary,
    EpisodeProductionPublicError,
    create_in_memory_boundary,
    create_local_development_boundary,
    create_local_development_boundary_from_environment,
)
from .shot_graph import validate_executable_shot_graph

__all__ = [
    "EpisodeProductionPublicBoundary",
    "EpisodeProductionPublicError",
    "EpisodeProductionService",
    "InMemoryEpisodeProductionAdapter",
    "IdentityReferenceAuthorityPort",
    "RejectingIdentityReferenceAuthority",
    "SqliteEpisodeProductionAdapter",
    "StaticIdentityReferenceAuthority",
    "create_in_memory_boundary",
    "create_local_development_boundary",
    "create_local_development_boundary_from_environment",
    "validate_executable_shot_graph",
]
