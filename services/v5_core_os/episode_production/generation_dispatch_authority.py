"""Independent, pinned approval readers; no environment lookup or trust defaults."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import stat
from typing import Mapping, Protocol

from . import generation_dispatch_contracts as c

APPROVAL_CONFIG_NAMES = ("CREATOR_GENERATION_DISPATCH_APPROVAL_BUNDLE_PATH",
    "CREATOR_GENERATION_DISPATCH_APPROVAL_BUNDLE_SHA256")
REVOCATION_CONFIG_NAMES = ("CREATOR_GENERATION_DISPATCH_REVOCATION_BUNDLE_PATH",
    "CREATOR_GENERATION_DISPATCH_REVOCATION_BUNDLE_SHA256")


class ApprovalOriginalPort(Protocol):
    """Trusted composition supplies original decisions, with authenticated provenance.

    This port must locate and validate the approval original through the existing
    authority workflow, including the authority/actor/Project Lead association.
    It must not use the client or bundle's self-asserted actor as its trust root.
    Returning the original decision allows exact comparison, not a `verified` flag.
    """
    def resolve_original(self, authority_ref: str, decision_ref: str,
                         evidence_ref: str, evidence_digest: str) -> dict: ...


class RejectingApprovalOriginal:
    def resolve_original(self, authority_ref, decision_ref, evidence_ref, evidence_digest):
        raise c.DispatchError("APPROVAL_UNAVAILABLE")


@dataclass(frozen=True)
class SelectedApproval:
    """Private port return, not an additional persisted or wire authority object."""
    plan_package: dict | None
    approval: dict
    bundle_sha256: str


class ApprovalReaderPort(Protocol):
    def resolve(self, authority_decision_ref: str) -> SelectedApproval: ...


class RejectingApprovalReader:
    def resolve(self, authority_decision_ref: str) -> SelectedApproval:
        raise c.DispatchError("APPROVAL_UNAVAILABLE")


def _identity(info) -> tuple:
    return tuple(getattr(info, field) for field in (
        "st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns"))


def _open_chain(path: Path) -> list[int]:
    """The E3H openat/O_NOFOLLOW shape, retaining parents to verify renames too."""
    descriptors = []
    try:
        c.require(path.is_absolute() and ".." not in path.parts, "APPROVAL_UNAVAILABLE")
        descriptors.append(os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY))
        for name in path.parts[1:-1]:
            descriptors.append(os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                       dir_fd=descriptors[-1]))
        descriptors.append(os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                   dir_fd=descriptors[-1]))
        c.require(stat.S_ISREG(os.fstat(descriptors[-1]).st_mode), "APPROVAL_UNAVAILABLE")
        return descriptors
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def read_pinned_file(path: Path, expected_sha256: str) -> bytes:
    """Bounded regular bytes; no symlinks, path replacement or in-read mutation."""
    descriptors, check = [], []
    try:
        c.sha(expected_sha256)
        descriptors = _open_chain(path)
        before = [_identity(os.fstat(fd)) for fd in descriptors]
        size = os.fstat(descriptors[-1]).st_size
        c.require(0 < size <= c.MAX_JSON_BYTES, "APPROVAL_UNAVAILABLE")
        chunks, length = [], 0
        while length <= c.MAX_JSON_BYTES:
            block = os.read(descriptors[-1], min(65536, c.MAX_JSON_BYTES + 1 - length))
            if not block:
                break
            chunks.append(block)
            length += len(block)
        raw = b"".join(chunks)
        c.require(length == size, "APPROVAL_UNAVAILABLE")
        c.require(before == [_identity(os.fstat(fd)) for fd in descriptors], "APPROVAL_UNAVAILABLE")
        # Re-walk from the root: an unlinked/replaced pathname is not the held fd.
        check = _open_chain(path)
        c.require(before == [_identity(os.fstat(fd)) for fd in check], "APPROVAL_UNAVAILABLE")
        c.require(sha256(raw).hexdigest() == expected_sha256, "APPROVAL_UNAVAILABLE")
        return raw
    except (OSError, ValueError) as exc:
        raise c.DispatchError("APPROVAL_UNAVAILABLE") from exc
    finally:
        for descriptor in reversed(check + descriptors):
            os.close(descriptor)


class PinnedApprovalReader:
    def __init__(self, path: str | Path, expected_sha256: str, *,
                 original: ApprovalOriginalPort | None = None, revocation: bool = False):
        # Construction never reads files. Resolve performs every required fresh read.
        self._path = Path(path)
        c.require(self._path.is_absolute() and ".." not in self._path.parts, "APPROVAL_UNAVAILABLE")
        self._pin = c.sha(expected_sha256)
        self._original = original if original is not None else RejectingApprovalOriginal()
        self._revocation = revocation

    def resolve(self, authority_decision_ref: str) -> SelectedApproval:
        try:
            c.ref(authority_decision_ref)
            raw = read_pinned_file(self._path, self._pin)
            bundle = c.validate_bundle(c.strict_json(raw), revocation=self._revocation)
            entry = bundle["revocations" if self._revocation else "approvals"][0]
            approval = entry if self._revocation else entry["approval"]
            c.require(approval["authorityDecisionRef"] == authority_decision_ref, "APPROVAL_UNAVAILABLE")
            original = self._original.resolve_original(bundle["authorityRef"], authority_decision_ref,
                approval["approvalEvidenceRef"], approval["approvalEvidenceDigest"])
            c.validate_approval(original, revocation=self._revocation)
            c.require(c.canonical(original) == c.canonical(approval), "APPROVAL_UNAVAILABLE")
            return SelectedApproval(None if self._revocation else deepcopy(entry["planPackage"]),
                                    deepcopy(approval), self._pin)
        except Exception as exc:
            # This reader has no writes, and exposes no path or original body on failure.
            raise c.DispatchError("APPROVAL_UNAVAILABLE") from exc


def approval_reader_from_config(config: Mapping[str, str], *, original: ApprovalOriginalPort | None = None,
                                revocation: bool = False) -> ApprovalReaderPort:
    """Explicit configuration only. Missing configuration remains rejecting."""
    names = REVOCATION_CONFIG_NAMES if revocation else APPROVAL_CONFIG_NAMES
    values = [config.get(name) for name in names]
    if all(value is None for value in values):
        return RejectingApprovalReader()
    c.require(all(type(value) is str and value for value in values), "APPROVAL_UNAVAILABLE")
    return PinnedApprovalReader(values[0], values[1], original=original, revocation=revocation)
