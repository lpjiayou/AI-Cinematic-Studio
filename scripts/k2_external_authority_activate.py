#!/usr/bin/env python3
"""Validate external K2 authority bundles and print secret-free activation exports.

This tool does not create, approve or modify authority facts. It validates two
operator-supplied files, computes their exact content digests and prints the four
environment assignments consumed by the Creator server.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import shlex
import sys

from services.v5_core_os.episode_production import (
    ExternalAuthorityConfigurationError,
    external_authorities_from_environment,
)


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate exact K2 Rights/Provider authority bundles and print "
            "digest-pinned environment assignments."
        )
    )
    parser.add_argument("--rights-bundle", type=Path, required=True)
    parser.add_argument("--provider-bundle", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    rights = args.rights_bundle.resolve()
    provider = args.provider_bundle.resolve()
    try:
        environment = {
            "CREATOR_RIGHTS_AUTHORITY_BUNDLE_PATH": str(rights),
            "CREATOR_RIGHTS_AUTHORITY_BUNDLE_SHA256": _digest(rights),
            "CREATOR_PROVIDER_AUTHORITY_BUNDLE_PATH": str(provider),
            "CREATOR_PROVIDER_AUTHORITY_BUNDLE_SHA256": _digest(provider),
        }
        rights_authority, provider_authority = external_authorities_from_environment(
            environment
        )
        if not rights_authority.available or not provider_authority.available:
            raise ExternalAuthorityConfigurationError(
                "external authorities did not activate"
            )
    except (OSError, ExternalAuthorityConfigurationError) as exc:
        print(f"external authority activation validation failed: {exc}", file=sys.stderr)
        return 2
    for name, value in environment.items():
        print(f"export {name}={shlex.quote(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
