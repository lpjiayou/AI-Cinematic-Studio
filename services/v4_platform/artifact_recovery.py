"""Fail-closed artifact inventory and quarantine for the V4 media worker.

The store never follows symlinks and never deletes an artifact.  Quarantine is an
atomic, deterministic move inside the configured artifact root so the same command
can be replayed safely after a process restart.
"""

from __future__ import annotations

import errno
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Iterable


class ArtifactRecoveryStoreError(RuntimeError):
    """Artifact recovery could not prove a path or filesystem operation safe."""


class ArtifactRecoveryStore:
    """Own deterministic paths, inventory and non-destructive quarantine."""

    def __init__(self, artifact_root: Path | str) -> None:
        raw = Path(os.path.abspath(os.fspath(artifact_root)))
        existing = raw
        while not os.path.lexists(existing) and existing != existing.parent:
            existing = existing.parent
        try:
            existing_resolved = existing.resolve(strict=True)
        except OSError as exc:
            raise ArtifactRecoveryStoreError("artifact root parent is unavailable") from exc
        if existing_resolved != existing:
            raise ArtifactRecoveryStoreError("artifact root path contains a symlink")
        raw.mkdir(parents=True, exist_ok=True)
        try:
            resolved = raw.resolve(strict=True)
        except OSError as exc:
            raise ArtifactRecoveryStoreError("artifact root is unavailable") from exc
        if resolved != raw or not raw.is_dir():
            raise ArtifactRecoveryStoreError(
                "artifact root contains a symlink or is not a directory"
            )
        self.root = raw

    @staticmethod
    def _scope_hash(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()[:20]

    def _assert_under_root(self, path: Path) -> Path:
        absolute = Path(os.path.abspath(os.fspath(path)))
        try:
            absolute.relative_to(self.root)
        except ValueError as exc:
            raise ArtifactRecoveryStoreError(
                "artifact path escaped configured root"
            ) from exc
        return absolute

    def _assert_no_symlinks(self, path: Path) -> None:
        absolute = self._assert_under_root(path)
        relative = absolute.relative_to(self.root)
        cursor = self.root
        try:
            root_mode = os.lstat(cursor).st_mode
        except OSError as exc:
            raise ArtifactRecoveryStoreError(
                "artifact root became unavailable"
            ) from exc
        if stat.S_ISLNK(root_mode):
            raise ArtifactRecoveryStoreError("artifact root became a symlink")
        for part in relative.parts:
            cursor = cursor / part
            if os.path.lexists(cursor) and stat.S_ISLNK(os.lstat(cursor).st_mode):
                raise ArtifactRecoveryStoreError("artifact path contains a symlink")

    @staticmethod
    def _validate_storage_key(storage_key: str) -> tuple[str, ...]:
        if (
            not isinstance(storage_key, str)
            or not storage_key
            or "\\" in storage_key
        ):
            raise ArtifactRecoveryStoreError("artifact storage key is invalid")
        pure = PurePosixPath(storage_key)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ArtifactRecoveryStoreError("artifact storage key is invalid")
        return pure.parts

    def run_root(
        self, workspace_ref: str, run_ref: str, *, create: bool = True
    ) -> Path:
        if not isinstance(workspace_ref, str) or not workspace_ref:
            raise ArtifactRecoveryStoreError("workspace scope is invalid")
        if not isinstance(run_ref, str) or not run_ref:
            raise ArtifactRecoveryStoreError("production-run scope is invalid")
        root = (
            self.root
            / self._scope_hash(workspace_ref)
            / self._scope_hash(run_ref)
        )
        self._assert_no_symlinks(root)
        if create:
            root.mkdir(parents=True, exist_ok=True)
        self._assert_no_symlinks(root)
        if os.path.lexists(root) and (
            not stat.S_ISDIR(os.lstat(root).st_mode)
            or root.resolve(strict=True) != root
        ):
            raise ArtifactRecoveryStoreError("run artifact root is unsafe")
        return root

    def scoped_path(
        self,
        workspace_ref: str,
        run_ref: str,
        path: Path | str,
        *,
        require_regular_file: bool = False,
    ) -> Path:
        run_root = self.run_root(workspace_ref, run_ref)
        absolute = Path(os.path.abspath(os.fspath(path)))
        try:
            absolute.relative_to(run_root)
        except ValueError as exc:
            raise ArtifactRecoveryStoreError(
                "artifact path escaped production-run scope"
            ) from exc
        self._assert_no_symlinks(absolute)
        if require_regular_file:
            try:
                mode = os.lstat(absolute).st_mode
            except OSError as exc:
                raise ArtifactRecoveryStoreError("artifact file is unavailable") from exc
            if not stat.S_ISREG(mode):
                raise ArtifactRecoveryStoreError("artifact is not a regular file")
        return absolute

    def path_from_storage_key(
        self,
        storage_key: str,
        *,
        require_regular_file: bool = False,
    ) -> Path:
        parts = self._validate_storage_key(storage_key)
        path = self.root.joinpath(*parts)
        self._assert_no_symlinks(path)
        if require_regular_file:
            try:
                mode = os.lstat(path).st_mode
            except OSError as exc:
                raise ArtifactRecoveryStoreError("artifact file is unavailable") from exc
            if not stat.S_ISREG(mode):
                raise ArtifactRecoveryStoreError("artifact is not a regular file")
        return path

    def storage_key(self, path: Path | str) -> str:
        absolute = self._assert_under_root(Path(path))
        self._assert_no_symlinks(absolute)
        return absolute.relative_to(self.root).as_posix()

    def attempt_paths(
        self,
        workspace_ref: str,
        run_ref: str,
        generation_request_ref: str,
        job_ref: str,
        attempt_ref: str,
        attempt_number: int,
        extension: str,
        *,
        create: bool = True,
    ) -> tuple[Path, Path]:
        if (
            not isinstance(attempt_number, int)
            or isinstance(attempt_number, bool)
            or attempt_number < 1
            or extension not in {".mp4", ".wav"}
        ):
            raise ArtifactRecoveryStoreError("artifact attempt identity is invalid")
        run_root = self.run_root(workspace_ref, run_ref, create=create)
        request_hash = self._scope_hash(generation_request_ref)
        job_hash = self._scope_hash(job_ref)
        attempt_hash = self._scope_hash(attempt_ref)
        directory = run_root / "jobs" / request_hash / job_hash
        self._assert_no_symlinks(directory)
        if create:
            directory.mkdir(parents=True, exist_ok=True)
            self._assert_no_symlinks(directory)
        candidate = directory / (
            f"attempt-{attempt_number}-{attempt_hash}.part{extension}"
        )
        final = directory / f"attempt-{attempt_number}-{attempt_hash}{extension}"
        self._assert_no_symlinks(candidate)
        self._assert_no_symlinks(final)
        return candidate, final

    def require_absent(self, path: Path | str) -> None:
        absolute = self._assert_under_root(Path(path))
        self._assert_no_symlinks(absolute)
        if os.path.lexists(absolute):
            raise ArtifactRecoveryStoreError(
                "deterministic artifact path is already occupied"
            )

    @staticmethod
    def _fsync_file(path: Path) -> os.stat_result:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise ArtifactRecoveryStoreError(
                    "artifact fsync target is not a regular file"
                )
            os.fsync(descriptor)
            return opened
        finally:
            os.close(descriptor)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def durable_replace(self, source: Path | str, destination: Path | str) -> Path:
        source_path = self._assert_under_root(Path(source))
        destination_path = self._assert_under_root(Path(destination))
        self._assert_no_symlinks(source_path)
        self._assert_no_symlinks(destination_path)
        try:
            source_stat = self._fsync_file(source_path)
        except (ArtifactRecoveryStoreError, OSError) as exc:
            raise ArtifactRecoveryStoreError("candidate artifact is unavailable") from exc
        if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_nlink != 1:
            raise ArtifactRecoveryStoreError("candidate artifact is not a regular file")
        if os.path.lexists(destination_path):
            raise ArtifactRecoveryStoreError("final artifact path is already occupied")
        self._assert_no_symlinks(destination_path.parent)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        self._assert_no_symlinks(destination_path.parent)
        try:
            os.link(source_path, destination_path, follow_symlinks=False)
            destination_stat = self._fsync_file(destination_path)
            current_source_stat = os.lstat(source_path)
            if (
                destination_stat.st_dev != source_stat.st_dev
                or destination_stat.st_ino != source_stat.st_ino
                or current_source_stat.st_dev != source_stat.st_dev
                or current_source_stat.st_ino != source_stat.st_ino
            ):
                raise ArtifactRecoveryStoreError(
                    "artifact changed during no-clobber publication"
                )
            self._fsync_directory(destination_path.parent)
            os.unlink(source_path)
            self._fsync_directory(source_path.parent)
        except ArtifactRecoveryStoreError:
            raise
        except OSError as exc:
            raise ArtifactRecoveryStoreError(
                "artifact no-clobber publication failed"
            ) from exc
        return destination_path

    def complete_linked_publication(
        self, candidate: Path | str, final: Path | str
    ) -> Path:
        """Finish only the exact hard-link state left by ``durable_replace``."""

        candidate_path = self._assert_under_root(Path(candidate))
        final_path = self._assert_under_root(Path(final))
        self._assert_no_symlinks(candidate_path)
        self._assert_no_symlinks(final_path)
        try:
            candidate_stat = os.lstat(candidate_path)
            final_stat = os.lstat(final_path)
            if (
                not stat.S_ISREG(candidate_stat.st_mode)
                or not stat.S_ISREG(final_stat.st_mode)
                or candidate_stat.st_dev != final_stat.st_dev
                or candidate_stat.st_ino != final_stat.st_ino
                or candidate_stat.st_nlink != 2
                or final_stat.st_nlink != 2
            ):
                raise ArtifactRecoveryStoreError(
                    "publication paths are not one exact interrupted hard link"
                )
            synced_final = self._fsync_file(final_path)
            current_candidate = os.lstat(candidate_path)
            current_final = os.lstat(final_path)
            if any(
                item.st_dev != final_stat.st_dev
                or item.st_ino != final_stat.st_ino
                for item in (synced_final, current_candidate, current_final)
            ):
                raise ArtifactRecoveryStoreError(
                    "interrupted publication changed during recovery"
                )
            self._fsync_directory(final_path.parent)
            os.unlink(candidate_path)
            self._fsync_directory(candidate_path.parent)
            committed = os.lstat(final_path)
            if (
                not stat.S_ISREG(committed.st_mode)
                or committed.st_dev != final_stat.st_dev
                or committed.st_ino != final_stat.st_ino
                or committed.st_nlink != 1
            ):
                raise ArtifactRecoveryStoreError(
                    "interrupted publication did not converge"
                )
        except ArtifactRecoveryStoreError:
            raise
        except OSError as exc:
            raise ArtifactRecoveryStoreError(
                "interrupted publication could not be completed"
            ) from exc
        return final_path

    @staticmethod
    def _file_digest_and_size(path: Path) -> tuple[str, int]:
        digest = sha256()
        size = 0
        try:
            descriptor = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                os.close(descriptor)
                raise ArtifactRecoveryStoreError(
                    "artifact is not one exact regular file"
                )
            with os.fdopen(descriptor, "rb") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
                closed_over = os.fstat(source.fileno())
            if (
                closed_over.st_dev != opened.st_dev
                or closed_over.st_ino != opened.st_ino
                or closed_over.st_size != opened.st_size
                or size != opened.st_size
            ):
                raise ArtifactRecoveryStoreError(
                    "artifact changed while being inventoried"
                )
        except ArtifactRecoveryStoreError:
            raise
        except OSError as exc:
            raise ArtifactRecoveryStoreError("artifact inventory hash failed") from exc
        return digest.hexdigest(), size

    def _entry(
        self,
        run_root: Path,
        path: Path,
        referenced: set[str],
    ) -> dict[str, Any]:
        storage_key = path.relative_to(self.root).as_posix()
        relative_to_run = path.relative_to(run_root)
        mode = os.lstat(path).st_mode
        in_quarantine = bool(
            relative_to_run.parts and relative_to_run.parts[0] == "quarantine"
        )
        if stat.S_ISLNK(mode):
            entry_type = "SYMLINK"
            digest = None
            byte_size = None
            state = "UNSAFE"
        elif stat.S_ISREG(mode):
            entry_type = "REGULAR_FILE"
            try:
                digest, byte_size = self._file_digest_and_size(path)
            except ArtifactRecoveryStoreError:
                digest = None
                byte_size = None
                state = "UNSAFE"
            else:
                if in_quarantine:
                    state = "QUARANTINED"
                elif storage_key in referenced:
                    state = "REFERENCED"
                else:
                    state = "ORPHAN"
        else:
            entry_type = "OTHER"
            digest = None
            byte_size = None
            state = "UNSAFE"
        return {
            "storageKey": storage_key,
            "entryType": entry_type,
            "inventoryState": state,
            "referenced": storage_key in referenced,
            "sha256": digest,
            "byteSize": byte_size,
        }

    def inventory(
        self,
        workspace_ref: str,
        run_ref: str,
        referenced_storage_keys: Iterable[str],
    ) -> list[dict[str, Any]]:
        run_root = self.run_root(workspace_ref, run_ref, create=False)
        referenced: set[str] = set()
        for storage_key in referenced_storage_keys:
            parts = self._validate_storage_key(storage_key)
            referenced.add(PurePosixPath(*parts).as_posix())
        entries: list[dict[str, Any]] = []
        if not os.path.lexists(run_root):
            return entries

        def visit(directory: Path) -> None:
            self._assert_no_symlinks(directory)
            try:
                with os.scandir(directory) as scanner:
                    children = sorted(scanner, key=lambda item: item.name)
            except OSError as exc:
                raise ArtifactRecoveryStoreError(
                    "artifact inventory could not read a directory"
                ) from exc
            for child in children:
                path = Path(child.path)
                if child.is_symlink():
                    entries.append(self._entry(run_root, path, referenced))
                elif child.is_dir(follow_symlinks=False):
                    visit(path)
                else:
                    entries.append(self._entry(run_root, path, referenced))

        visit(run_root)
        return entries

    def quarantine(
        self,
        workspace_ref: str,
        run_ref: str,
        storage_key: str,
        *,
        category: str,
        reason: str,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", category):
            raise ArtifactRecoveryStoreError("quarantine category is invalid")
        if not isinstance(reason, str) or not reason or len(reason) > 200:
            raise ArtifactRecoveryStoreError("quarantine reason is invalid")
        parts = self._validate_storage_key(storage_key)
        normalized_key = PurePosixPath(*parts).as_posix()
        source = self.root.joinpath(*parts)
        run_root = self.run_root(workspace_ref, run_ref)
        try:
            source.relative_to(run_root)
        except ValueError as exc:
            raise ArtifactRecoveryStoreError(
                "artifact is outside the requested production run"
            ) from exc
        if "quarantine" in source.relative_to(run_root).parts:
            raise ArtifactRecoveryStoreError("artifact is already quarantined")
        suffix = source.suffix if len(source.suffix) <= 16 else ""
        key_hash = sha256(
            f"{normalized_key}\0{category}\0{reason}".encode("utf-8")
        ).hexdigest()[:24]
        destination = run_root / "quarantine" / category / f"artifact-{key_hash}{suffix}"
        self._assert_no_symlinks(destination.parent)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._assert_no_symlinks(destination.parent)
        self._assert_no_symlinks(destination)

        if not os.path.lexists(source):
            if os.path.lexists(destination):
                self._assert_no_symlinks(destination)
                destination_stat = os.lstat(destination)
                if (
                    not stat.S_ISREG(destination_stat.st_mode)
                    or destination_stat.st_nlink != 1
                ):
                    raise ArtifactRecoveryStoreError(
                        "quarantine replay target is unsafe"
                    )
                entry = self._entry(run_root, destination, set())
                entry.update(
                    {
                        "originalStorageKey": normalized_key,
                        "quarantineReason": reason,
                        "idempotentReplay": True,
                    }
                )
                return entry
            raise ArtifactRecoveryStoreError("artifact to quarantine is unavailable")

        self._assert_no_symlinks(source)
        source_stat = os.lstat(source)
        if not stat.S_ISREG(source_stat.st_mode):
            raise ArtifactRecoveryStoreError(
                "only one exact regular artifact may be quarantined"
            )
        interrupted_link = False
        if source_stat.st_nlink != 1:
            if source_stat.st_nlink == 2 and os.path.lexists(destination):
                destination_stat = os.lstat(destination)
                interrupted_link = (
                    stat.S_ISREG(destination_stat.st_mode)
                    and destination_stat.st_dev == source_stat.st_dev
                    and destination_stat.st_ino == source_stat.st_ino
                    and destination_stat.st_nlink == 2
                )
            if not interrupted_link:
                raise ArtifactRecoveryStoreError(
                    "only one exact regular artifact may be quarantined"
                )
        created_link = False
        replay = interrupted_link or os.path.lexists(destination)
        completed_elsewhere = False
        try:
            try:
                synced_source = self._fsync_file(source)
            except FileNotFoundError:
                if not os.path.lexists(destination):
                    raise
                completed_destination = os.lstat(destination)
                if (
                    not stat.S_ISREG(completed_destination.st_mode)
                    or completed_destination.st_dev != source_stat.st_dev
                    or completed_destination.st_ino != source_stat.st_ino
                    or completed_destination.st_nlink != 1
                ):
                    raise ArtifactRecoveryStoreError(
                        "quarantine target already exists"
                    )
                synced_source = source_stat
                interrupted_link = True
                replay = True
                completed_elsewhere = True
            if (
                synced_source.st_dev != source_stat.st_dev
                or synced_source.st_ino != source_stat.st_ino
                or not stat.S_ISREG(synced_source.st_mode)
                or synced_source.st_nlink not in {1, 2}
            ):
                raise ArtifactRecoveryStoreError(
                    "artifact changed before quarantine claim"
                )
            if not completed_elsewhere and synced_source.st_nlink == 2:
                if not os.path.lexists(destination):
                    raise ArtifactRecoveryStoreError(
                        "artifact has an unclaimed hard link"
                    )
                linked_destination = os.lstat(destination)
                if (
                    not stat.S_ISREG(linked_destination.st_mode)
                    or linked_destination.st_dev != synced_source.st_dev
                    or linked_destination.st_ino != synced_source.st_ino
                    or linked_destination.st_nlink != 2
                ):
                    raise ArtifactRecoveryStoreError(
                        "artifact has an unsafe hard link"
                    )
                interrupted_link = True
                replay = True
            if not interrupted_link:
                try:
                    os.link(source, destination, follow_symlinks=False)
                    created_link = True
                except OSError as exc:
                    if exc.errno == errno.EEXIST:
                        replay = True
                    elif exc.errno == errno.ENOENT and os.path.lexists(
                        destination
                    ):
                        replay = True
                    else:
                        raise

            for _ in range(4):
                source_exists = os.path.lexists(source)
                destination_exists = os.path.lexists(destination)
                if not destination_exists:
                    raise ArtifactRecoveryStoreError(
                        "quarantine claim disappeared"
                    )
                destination_stat = os.lstat(destination)
                if (
                    not stat.S_ISREG(destination_stat.st_mode)
                    or destination_stat.st_dev != synced_source.st_dev
                    or destination_stat.st_ino != synced_source.st_ino
                ):
                    raise ArtifactRecoveryStoreError(
                        "quarantine target already exists"
                    )
                if not source_exists:
                    if destination_stat.st_nlink != 1:
                        raise ArtifactRecoveryStoreError(
                            "quarantine move did not converge"
                        )
                    self._fsync_file(destination)
                    self._fsync_directory(destination.parent)
                    break
                current_source = os.lstat(source)
                if (
                    not stat.S_ISREG(current_source.st_mode)
                    or current_source.st_dev != synced_source.st_dev
                    or current_source.st_ino != synced_source.st_ino
                    or current_source.st_nlink != 2
                    or destination_stat.st_nlink != 2
                ):
                    raise ArtifactRecoveryStoreError(
                        "artifact changed during quarantine"
                    )
                synced_destination = self._fsync_file(destination)
                if (
                    synced_destination.st_dev != synced_source.st_dev
                    or synced_destination.st_ino != synced_source.st_ino
                    or synced_destination.st_nlink != 2
                ):
                    raise ArtifactRecoveryStoreError(
                        "quarantine target changed"
                    )
                self._fsync_directory(destination.parent)
                try:
                    os.unlink(source)
                except FileNotFoundError:
                    continue
                self._fsync_directory(source.parent)
            else:
                raise ArtifactRecoveryStoreError(
                    "quarantine move did not converge"
                )
        except ArtifactRecoveryStoreError:
            if created_link:
                try:
                    if os.path.lexists(source) and os.path.lexists(destination):
                        current_source = os.lstat(source)
                        current_destination = os.lstat(destination)
                        if (
                            current_source.st_dev == synced_source.st_dev
                            and current_source.st_ino == synced_source.st_ino
                            and current_destination.st_dev == synced_source.st_dev
                            and current_destination.st_ino == synced_source.st_ino
                            and current_source.st_nlink == 2
                            and current_destination.st_nlink == 2
                        ):
                            os.unlink(destination)
                            self._fsync_directory(destination.parent)
                except OSError as rollback_exc:
                    raise ArtifactRecoveryStoreError(
                        "artifact quarantine rollback failed"
                    ) from rollback_exc
            raise
        except OSError as exc:
            if created_link:
                try:
                    if os.path.lexists(source) and os.path.lexists(destination):
                        current_source = os.lstat(source)
                        current_destination = os.lstat(destination)
                        if (
                            current_source.st_dev == synced_source.st_dev
                            and current_source.st_ino == synced_source.st_ino
                            and current_destination.st_dev == synced_source.st_dev
                            and current_destination.st_ino == synced_source.st_ino
                            and current_source.st_nlink == 2
                            and current_destination.st_nlink == 2
                        ):
                            os.unlink(destination)
                            self._fsync_directory(destination.parent)
                except OSError as rollback_exc:
                    raise ArtifactRecoveryStoreError(
                        "artifact quarantine rollback failed"
                    ) from rollback_exc
            raise ArtifactRecoveryStoreError("artifact quarantine failed") from exc
        entry = self._entry(run_root, destination, set())
        entry.update(
            {
                "originalStorageKey": normalized_key,
                "quarantineReason": reason,
                "idempotentReplay": replay,
            }
        )
        return entry


__all__ = ["ArtifactRecoveryStore", "ArtifactRecoveryStoreError"]
