#!/usr/bin/env python3
"""Build or validate one closed M10 manifest-v2 input-append authority bundle.

This operator utility writes only a new bundle file.  It never opens an Episode
Production database, appends journal records, invokes a provider, or grants media
execution authority.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from services.v5_core_os.episode_production.input_append_authority import (  # noqa: E402
    DigestPinnedInputAppendAuthority,
    _read_regular,
    _strict_json,
    create_bundle,
    create_grant,
    seal_subject,
    validate_subject,
)


def _absolute(value: str, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    return path


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _write_new_regular(path: Path, data: bytes) -> None:
    normalized = Path(os.path.abspath(path))
    parent_descriptor = os.open(
        normalized.anchor, os.O_RDONLY | os.O_DIRECTORY
    )
    created = False
    try:
        for part in normalized.parts[1:-1]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_descriptor,
            )
            os.close(parent_descriptor)
            parent_descriptor = next_descriptor
        descriptor = os.open(
            normalized.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_descriptor,
        )
        created = True
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            os.unlink(normalized.name, dir_fd=parent_descriptor)
            created = False
            raise
    except OSError as exc:
        if created:
            try:
                os.unlink(normalized.name, dir_fd=parent_descriptor)
            except OSError:
                pass
        raise ValueError("bundle output path cannot be opened safely") from exc
    finally:
        os.close(parent_descriptor)


def build(args: argparse.Namespace) -> dict[str, object]:
    subject_path = _absolute(args.subject_path, "subject path")
    bundle_path = _absolute(args.bundle_path, "bundle path")
    raw_subject = _strict_json(_read_regular(subject_path))
    subject = (
        validate_subject(raw_subject)
        if isinstance(raw_subject, dict) and "payloadDigest" in raw_subject
        else seal_subject(raw_subject)
    )
    grant = create_grant(
        authority_ref=args.authority_ref,
        input_append_authority_ref=args.input_append_authority_ref,
        subject=subject,
        authority_decision_ref=args.authority_decision_ref,
        decided_at=args.decided_at,
    )
    bundle = create_bundle(authority_ref=args.authority_ref, grants=[grant])
    data = _canonical_bytes(bundle)
    _write_new_regular(bundle_path, data)
    digest = sha256(data).hexdigest()
    DigestPinnedInputAppendAuthority(bundle_path, digest)
    return {
        "bundlePath": str(bundle_path),
        "bundleSha256": digest,
        "subjectDigest": subject["payloadDigest"],
        "inputAppendAuthorityRef": args.input_append_authority_ref,
        "operation": "BUILD_ONLY_NO_JOURNAL_WRITE",
    }


def validate(args: argparse.Namespace) -> dict[str, object]:
    bundle_path = _absolute(args.bundle_path, "bundle path")
    DigestPinnedInputAppendAuthority(bundle_path, args.bundle_sha256)
    return {
        "bundlePath": str(bundle_path),
        "bundleSha256": args.bundle_sha256,
        "validation": "PASS",
        "operation": "VALIDATE_ONLY_NO_JOURNAL_WRITE",
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Build or validate a bounded M10 input-append authority bundle"
    )
    commands = result.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--subject-path", required=True)
    build_parser.add_argument("--bundle-path", required=True)
    build_parser.add_argument("--authority-ref", required=True)
    build_parser.add_argument("--input-append-authority-ref", required=True)
    build_parser.add_argument("--authority-decision-ref", required=True)
    build_parser.add_argument("--decided-at", required=True)
    build_parser.set_defaults(operation=build)

    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--bundle-path", required=True)
    validate_parser.add_argument("--bundle-sha256", required=True)
    validate_parser.set_defaults(operation=validate)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        result = arguments.operation(arguments)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(_canonical_bytes(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
