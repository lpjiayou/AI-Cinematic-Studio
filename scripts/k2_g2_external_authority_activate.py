#!/usr/bin/env python3
"""Validate digest-pinned G2 M6 and optional Identity authority bundles.

This tool is validate-only.  It does not create M6 facts, select identities,
approve decisions, call the Creator API or advance the K2 production run.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import shlex
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.v5_core_os.episode_production import (
    ExternalAuthorityConfigurationError,
    identity_reference_authority_from_environment,
)
from services.v5_core_os.series_intelligence import (
    M6ExternalAuthorityConfigurationError,
    m6_external_authorities_from_environment,
)


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def _resolved_bundle(path: Path, name: str) -> Path:
    resolved = path.resolve()
    if not str(resolved).isprintable():
        raise ExternalAuthorityConfigurationError(
            f"{name} path contains non-printable characters"
        )
    return resolved


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate exact K2 G2 M6/Identity authority bundles and print "
            "digest-pinned environment assignments."
        )
    )
    parser.add_argument("--m6-bundle", type=Path, required=True)
    parser.add_argument("--identity-bundle", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        m6 = _resolved_bundle(args.m6_bundle, "M6 authority bundle")
        environment = {
            "CREATOR_M6_AUTHORITY_BUNDLE_PATH": str(m6),
            "CREATOR_M6_AUTHORITY_BUNDLE_SHA256": _digest(m6),
        }
        m6_external_authorities_from_environment(environment)
        if args.identity_bundle is not None:
            identity = _resolved_bundle(
                args.identity_bundle, "identity reference authority bundle"
            )
            environment.update(
                {
                    "CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_PATH": str(
                        identity
                    ),
                    "CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_SHA256": _digest(
                        identity
                    ),
                }
            )
            identity_reference_authority_from_environment(environment)
    except (
        OSError,
        ExternalAuthorityConfigurationError,
        M6ExternalAuthorityConfigurationError,
    ) as exc:
        print(
            f"G2 external authority activation validation failed: {exc}",
            file=sys.stderr,
        )
        return 2
    for name, value in environment.items():
        print(f"export {name}={shlex.quote(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
