"""Fail-closed artifact inventory and quarantine for the V4 media worker.

The store never follows symlinks and never deletes an artifact.  Quarantine is an
atomic, deterministic move inside the configured artifact root so the same command
can be replayed safely after a process restart.
"""

from __future__ import annotations

import errno
import fcntl
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any, Callable, Iterable


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

    def durable_replace(
        self,
        source: Path | str,
        destination: Path | str,
        *,
        assert_fence: Callable[[], None] | None = None,
    ) -> Path:
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
            if assert_fence is not None:
                assert_fence()
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
        return self._quarantine_with_directory_descriptors(
            workspace_ref,
            run_ref,
            storage_key,
            category=category,
            reason=reason,
        )

    @staticmethod
    def _directory_open_flags() -> int:
        return (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )

    @classmethod
    def _open_directory_chain(
        cls,
        base_fd: int,
        parts: Iterable[str],
        *,
        create: bool = False,
    ) -> int:
        current_fd = os.dup(base_fd)
        try:
            for part in parts:
                created = False
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=current_fd)
                        created = True
                    except FileExistsError:
                        pass
                next_fd = os.open(
                    part,
                    cls._directory_open_flags(),
                    dir_fd=current_fd,
                )
                try:
                    if created:
                        os.fsync(current_fd)
                        os.fsync(next_fd)
                    os.close(current_fd)
                except BaseException as exc:
                    try:
                        os.close(next_fd)
                    except OSError as cleanup_exc:
                        exc.add_note(
                            "new directory descriptor cleanup also failed: "
                            f"{cleanup_exc}"
                        )
                    raise
                current_fd = next_fd
            return current_fd
        except BaseException as exc:
            try:
                os.close(current_fd)
            except OSError as cleanup_exc:
                exc.add_note(
                    "directory chain cleanup also failed: "
                    f"{cleanup_exc}"
                )
            raise

    @classmethod
    def _open_absolute_directory(cls, path: Path) -> int:
        absolute = Path(os.path.abspath(os.fspath(path)))
        root_fd = os.open(os.sep, cls._directory_open_flags())
        opened_fd: int | None = None
        active_error: BaseException | None = None
        try:
            opened_fd = cls._open_directory_chain(
                root_fd,
                absolute.parts[1:],
            )
        except BaseException as exc:
            active_error = exc
            raise
        finally:
            try:
                os.close(root_fd)
            except OSError as cleanup_exc:
                if active_error is not None:
                    active_error.add_note(
                        "absolute root descriptor cleanup also failed: "
                        f"{cleanup_exc}"
                    )
                else:
                    if opened_fd is not None:
                        try:
                            os.close(opened_fd)
                        except OSError as opened_cleanup_exc:
                            cleanup_exc.add_note(
                                "opened absolute directory descriptor cleanup "
                                f"also failed: {opened_cleanup_exc}"
                            )
                    raise ArtifactRecoveryStoreError(
                        "absolute root descriptor cleanup failed"
                    ) from cleanup_exc
        if opened_fd is None:
            raise ArtifactRecoveryStoreError(
                "absolute directory could not be opened"
            )
        return opened_fd

    @classmethod
    def _assert_absolute_directory_binding(
        cls,
        path: Path,
        expected_fd: int,
    ) -> None:
        current_fd = cls._open_absolute_directory(path)
        active_error: BaseException | None = None
        try:
            current = os.fstat(current_fd)
            expected = os.fstat(expected_fd)
            if (
                current.st_dev != expected.st_dev
                or current.st_ino != expected.st_ino
            ):
                raise ArtifactRecoveryStoreError(
                    "artifact root binding changed"
                )
        except BaseException as exc:
            active_error = exc
            raise
        finally:
            try:
                os.close(current_fd)
            except OSError as cleanup_exc:
                if active_error is not None:
                    active_error.add_note(
                        "absolute binding descriptor cleanup also failed: "
                        f"{cleanup_exc}"
                    )
                else:
                    raise ArtifactRecoveryStoreError(
                        "absolute binding descriptor cleanup failed"
                    ) from cleanup_exc

    @staticmethod
    def _stat_at(directory_fd: int | None, name: str) -> os.stat_result | None:
        if directory_fd is None:
            return None
        try:
            return os.stat(
                name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return None

    @classmethod
    def _assert_directory_binding(
        cls,
        root_fd: int,
        parts: Iterable[str],
        expected_fd: int,
    ) -> None:
        current_fd = cls._open_directory_chain(root_fd, parts)
        active_error: BaseException | None = None
        try:
            current = os.fstat(current_fd)
            expected = os.fstat(expected_fd)
            if (
                current.st_dev != expected.st_dev
                or current.st_ino != expected.st_ino
            ):
                raise ArtifactRecoveryStoreError(
                    "artifact directory binding changed"
                )
        except BaseException as exc:
            active_error = exc
            raise
        finally:
            try:
                os.close(current_fd)
            except OSError as cleanup_exc:
                if active_error is not None:
                    active_error.add_note(
                        "directory binding descriptor cleanup also failed: "
                        f"{cleanup_exc}"
                    )
                else:
                    raise ArtifactRecoveryStoreError(
                        "directory binding descriptor cleanup failed"
                    ) from cleanup_exc

    def _assert_quarantine_namespace_binding(
        self,
        *,
        root_fd: int,
        run_parts: tuple[str, str],
        relative_source_parent_parts: tuple[str, ...],
        source_parent_fd: int | None,
        category: str,
        destination_parent_fd: int,
    ) -> None:
        self._assert_absolute_directory_binding(self.root, root_fd)
        if source_parent_fd is not None:
            self._assert_directory_binding(
                root_fd,
                run_parts + relative_source_parent_parts,
                source_parent_fd,
            )
        self._assert_directory_binding(
            root_fd,
            run_parts + ("quarantine", category),
            destination_parent_fd,
        )
        self._assert_absolute_directory_binding(self.root, root_fd)

    @staticmethod
    def _sync_locked_file(descriptor: int) -> os.stat_result:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ArtifactRecoveryStoreError(
                "artifact fsync target is not a regular file"
            )
        os.fsync(descriptor)
        return opened

    @staticmethod
    def _quarantine_entry_from_descriptor(
        descriptor: int,
        *,
        storage_key: str,
        original_storage_key: str,
        reason: str,
        replay: bool,
    ) -> dict[str, Any]:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ArtifactRecoveryStoreError(
                "quarantine target is not one exact regular file"
            )
        digest = sha256()
        byte_size = 0
        while byte_size < opened.st_size:
            chunk = os.pread(
                descriptor,
                min(1024 * 1024, opened.st_size - byte_size),
                byte_size,
            )
            if not chunk:
                raise ArtifactRecoveryStoreError(
                    "quarantine target changed while being inventoried"
                )
            digest.update(chunk)
            byte_size += len(chunk)
        closed_over = os.fstat(descriptor)
        if (
            closed_over.st_dev != opened.st_dev
            or closed_over.st_ino != opened.st_ino
            or closed_over.st_size != opened.st_size
            or closed_over.st_mtime_ns != opened.st_mtime_ns
            or byte_size != opened.st_size
        ):
            raise ArtifactRecoveryStoreError(
                "quarantine target changed while being inventoried"
            )
        return {
            "storageKey": storage_key,
            "entryType": "REGULAR_FILE",
            "inventoryState": "QUARANTINED",
            "referenced": False,
            "sha256": digest.hexdigest(),
            "byteSize": byte_size,
            "originalStorageKey": original_storage_key,
            "quarantineReason": reason,
            "idempotentReplay": replay,
        }

    @staticmethod
    def _close_quarantine_descriptors(
        descriptors: Iterable[int],
        *,
        active_error: BaseException | None,
    ) -> None:
        cleanup_error: OSError | None = None
        for descriptor in reversed(tuple(descriptors)):
            try:
                os.close(descriptor)
            except OSError as exc:
                if cleanup_error is None:
                    cleanup_error = exc
        if cleanup_error is None:
            return
        if active_error is not None:
            active_error.add_note(
                "artifact quarantine descriptor cleanup also failed: "
                f"{cleanup_error}"
            )
            return
        raise ArtifactRecoveryStoreError(
            "artifact quarantine descriptor cleanup failed"
        ) from cleanup_error

    def _quarantine_with_directory_descriptors(
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
        if not isinstance(workspace_ref, str) or not workspace_ref:
            raise ArtifactRecoveryStoreError("workspace scope is invalid")
        if not isinstance(run_ref, str) or not run_ref:
            raise ArtifactRecoveryStoreError("production-run scope is invalid")

        source_parts = self._validate_storage_key(storage_key)
        normalized_key = PurePosixPath(*source_parts).as_posix()
        run_parts = (
            self._scope_hash(workspace_ref),
            self._scope_hash(run_ref),
        )
        if (
            len(source_parts) <= len(run_parts)
            or source_parts[: len(run_parts)] != run_parts
        ):
            raise ArtifactRecoveryStoreError(
                "artifact is outside the requested production run"
            )
        relative_source_parts = source_parts[len(run_parts) :]
        if "quarantine" in relative_source_parts:
            raise ArtifactRecoveryStoreError("artifact is already quarantined")

        source_name = relative_source_parts[-1]
        suffix = Path(source_name).suffix
        if len(suffix) > 16:
            suffix = ""
        key_hash = sha256(
            f"{normalized_key}\0{category}\0{reason}".encode("utf-8")
        ).hexdigest()[:24]
        destination_name = f"artifact-{key_hash}{suffix}"
        destination_parts = run_parts + (
            "quarantine",
            category,
            destination_name,
        )
        destination_key = PurePosixPath(*destination_parts).as_posix()

        descriptors: list[int] = []
        source_parent_fd: int | None = None
        destination_parent_fd: int | None = None
        locked_fd: int | None = None
        try:
            root_fd = self._open_absolute_directory(self.root)
            descriptors.append(root_fd)
            run_fd = self._open_directory_chain(root_fd, run_parts)
            descriptors.append(run_fd)
            try:
                source_parent_fd = self._open_directory_chain(
                    run_fd,
                    relative_source_parts[:-1],
                )
            except FileNotFoundError:
                source_parent_fd = None
            if source_parent_fd is not None:
                descriptors.append(source_parent_fd)
            destination_parent_fd = self._open_directory_chain(
                run_fd,
                ("quarantine", category),
                create=True,
            )
            descriptors.append(destination_parent_fd)

            file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            file_flags |= getattr(os, "O_NOFOLLOW", 0)
            for parent_fd, name in (
                (source_parent_fd, source_name),
                (destination_parent_fd, destination_name),
            ):
                if parent_fd is None:
                    continue
                try:
                    locked_fd = os.open(name, file_flags, dir_fd=parent_fd)
                    break
                except FileNotFoundError:
                    continue
            if locked_fd is None:
                raise ArtifactRecoveryStoreError(
                    "artifact to quarantine is unavailable"
                )
            descriptors.append(locked_fd)
            locked_stat = os.fstat(locked_fd)
            if not stat.S_ISREG(locked_stat.st_mode):
                raise ArtifactRecoveryStoreError(
                    "only one exact regular artifact may be quarantined"
                )
            fcntl.flock(locked_fd, fcntl.LOCK_EX)

            def exact_artifact(value: os.stat_result | None) -> bool:
                return bool(
                    value is not None
                    and stat.S_ISREG(value.st_mode)
                    and value.st_dev == locked_stat.st_dev
                    and value.st_ino == locked_stat.st_ino
                )

            def current_state() -> tuple[
                os.stat_result | None,
                os.stat_result | None,
            ]:
                return (
                    self._stat_at(source_parent_fd, source_name),
                    self._stat_at(destination_parent_fd, destination_name),
                )

            source_stat, destination_stat = current_state()
            if not exact_artifact(source_stat) and not exact_artifact(
                destination_stat
            ):
                raise ArtifactRecoveryStoreError(
                    "quarantine claim conflicts with the committed reason"
                )

            replay = destination_stat is not None
            created_link = False
            try:
                if source_stat is None:
                    if (
                        not exact_artifact(destination_stat)
                        or destination_stat.st_nlink != 1
                    ):
                        raise ArtifactRecoveryStoreError(
                            "quarantine replay target is unsafe"
                        )
                    synced = self._sync_locked_file(locked_fd)
                    if synced.st_nlink != 1:
                        raise ArtifactRecoveryStoreError(
                            "quarantine replay target is unsafe"
                        )
                    os.fsync(destination_parent_fd)
                    entry = self._quarantine_entry_from_descriptor(
                        locked_fd,
                        storage_key=destination_key,
                        original_storage_key=normalized_key,
                        reason=reason,
                        replay=True,
                    )
                    self._assert_quarantine_namespace_binding(
                        root_fd=root_fd,
                        run_parts=run_parts,
                        relative_source_parent_parts=relative_source_parts[:-1],
                        source_parent_fd=source_parent_fd,
                        category=category,
                        destination_parent_fd=destination_parent_fd,
                    )
                    published_destination = self._stat_at(
                        destination_parent_fd, destination_name
                    )
                    if (
                        not exact_artifact(published_destination)
                        or published_destination.st_nlink != 1
                    ):
                        raise ArtifactRecoveryStoreError(
                            "quarantine replay target lost its namespace binding"
                        )
                    return entry

                if not exact_artifact(source_stat):
                    raise ArtifactRecoveryStoreError(
                        "only one exact regular artifact may be quarantined"
                    )
                if destination_stat is None:
                    if source_stat.st_nlink != 1:
                        raise ArtifactRecoveryStoreError(
                            "only one exact regular artifact may be quarantined"
                        )
                    self._assert_quarantine_namespace_binding(
                        root_fd=root_fd,
                        run_parts=run_parts,
                        relative_source_parent_parts=relative_source_parts[:-1],
                        source_parent_fd=source_parent_fd,
                        category=category,
                        destination_parent_fd=destination_parent_fd,
                    )
                    try:
                        os.link(
                            source_name,
                            destination_name,
                            src_dir_fd=source_parent_fd,
                            dst_dir_fd=destination_parent_fd,
                            follow_symlinks=False,
                        )
                        created_link = True
                    except OSError as exc:
                        if exc.errno not in {errno.EEXIST, errno.ENOENT}:
                            raise
                        replay = True
                elif not exact_artifact(destination_stat):
                    raise ArtifactRecoveryStoreError(
                        "quarantine target already exists"
                    )

                source_stat, destination_stat = current_state()
                if source_stat is None:
                    if (
                        not exact_artifact(destination_stat)
                        or destination_stat.st_nlink != 1
                    ):
                        raise ArtifactRecoveryStoreError(
                            "quarantine move did not converge"
                        )
                    replay = True
                else:
                    if (
                        not exact_artifact(source_stat)
                        or not exact_artifact(destination_stat)
                        or source_stat.st_nlink != 2
                        or destination_stat.st_nlink != 2
                    ):
                        raise ArtifactRecoveryStoreError(
                            "artifact changed during quarantine"
                        )
                    synced = self._sync_locked_file(locked_fd)
                    if synced.st_nlink == 1:
                        completed_source, completed_destination = current_state()
                        if (
                            completed_source is not None
                            or not exact_artifact(completed_destination)
                            or completed_destination.st_nlink != 1
                        ):
                            raise ArtifactRecoveryStoreError(
                                "quarantine target changed"
                            )
                        replay = True
                    else:
                        if synced.st_nlink != 2:
                            raise ArtifactRecoveryStoreError(
                                "quarantine target changed"
                            )
                        os.fsync(destination_parent_fd)
                        self._assert_quarantine_namespace_binding(
                            root_fd=root_fd,
                            run_parts=run_parts,
                            relative_source_parent_parts=relative_source_parts[:-1],
                            source_parent_fd=source_parent_fd,
                            category=category,
                            destination_parent_fd=destination_parent_fd,
                        )
                        try:
                            os.unlink(source_name, dir_fd=source_parent_fd)
                        except FileNotFoundError:
                            replay = True
                        os.fsync(source_parent_fd)
                        os.fsync(destination_parent_fd)

                self._assert_quarantine_namespace_binding(
                    root_fd=root_fd,
                    run_parts=run_parts,
                    relative_source_parent_parts=relative_source_parts[:-1],
                    source_parent_fd=source_parent_fd,
                    category=category,
                    destination_parent_fd=destination_parent_fd,
                )
                final_source, final_destination = current_state()
                if (
                    final_source is not None
                    or not exact_artifact(final_destination)
                    or final_destination.st_nlink != 1
                ):
                    raise ArtifactRecoveryStoreError(
                        "quarantine move did not converge"
                    )
                synced = self._sync_locked_file(locked_fd)
                if synced.st_nlink != 1:
                    raise ArtifactRecoveryStoreError(
                        "quarantine move did not converge"
                    )
                entry = self._quarantine_entry_from_descriptor(
                    locked_fd,
                    storage_key=destination_key,
                    original_storage_key=normalized_key,
                    reason=reason,
                    replay=replay,
                )
                self._assert_quarantine_namespace_binding(
                    root_fd=root_fd,
                    run_parts=run_parts,
                    relative_source_parent_parts=relative_source_parts[:-1],
                    source_parent_fd=source_parent_fd,
                    category=category,
                    destination_parent_fd=destination_parent_fd,
                )
                published_source, published_destination = current_state()
                if (
                    published_source is not None
                    or not exact_artifact(published_destination)
                    or published_destination.st_nlink != 1
                ):
                    raise ArtifactRecoveryStoreError(
                        "quarantine target lost its namespace binding"
                    )
                return entry
            except (ArtifactRecoveryStoreError, OSError) as exc:
                if created_link:
                    try:
                        rollback_source, rollback_destination = current_state()
                        if (
                            exact_artifact(rollback_source)
                            and exact_artifact(rollback_destination)
                        ):
                            os.unlink(
                                destination_name,
                                dir_fd=destination_parent_fd,
                            )
                            os.fsync(destination_parent_fd)
                        elif (
                            rollback_source is None
                            and exact_artifact(rollback_destination)
                            and rollback_destination.st_nlink == 1
                        ):
                            self._assert_directory_binding(
                                root_fd,
                                run_parts + relative_source_parts[:-1],
                                source_parent_fd,
                            )
                            os.link(
                                destination_name,
                                source_name,
                                src_dir_fd=destination_parent_fd,
                                dst_dir_fd=source_parent_fd,
                                follow_symlinks=False,
                            )
                            os.fsync(source_parent_fd)
                            self._assert_directory_binding(
                                root_fd,
                                run_parts + relative_source_parts[:-1],
                                source_parent_fd,
                            )
                            os.unlink(
                                destination_name,
                                dir_fd=destination_parent_fd,
                            )
                            os.fsync(destination_parent_fd)
                            restored_source = self._stat_at(
                                source_parent_fd, source_name
                            )
                            if (
                                not exact_artifact(restored_source)
                                or restored_source.st_nlink != 1
                            ):
                                raise ArtifactRecoveryStoreError(
                                    "artifact quarantine restore did not converge"
                                )
                    except (
                        ArtifactRecoveryStoreError,
                        OSError,
                    ) as rollback_exc:
                        raise ArtifactRecoveryStoreError(
                            "artifact quarantine rollback failed"
                        ) from rollback_exc
                if isinstance(exc, ArtifactRecoveryStoreError):
                    raise
                raise ArtifactRecoveryStoreError(
                    "artifact quarantine failed"
                ) from exc
        except ArtifactRecoveryStoreError:
            raise
        except OSError as exc:
            raise ArtifactRecoveryStoreError(
                "artifact quarantine failed"
            ) from exc
        finally:
            self._close_quarantine_descriptors(
                descriptors,
                active_error=sys.exception(),
            )


__all__ = ["ArtifactRecoveryStore", "ArtifactRecoveryStoreError"]
