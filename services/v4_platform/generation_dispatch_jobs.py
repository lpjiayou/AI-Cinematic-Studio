"""V5-verified Grant bridge into the original V4 queue; no execution entry."""
from __future__ import annotations

from copy import deepcopy

from .backend_registry import BackendValidationError, digest, ref
from .media_jobs import DISPATCH_KEY_PREFIX, MediaJobError, _validate_method_aware_video_request
from .method_aware_execution import (
    DISPATCH_JOB_SCHEMA_VERSION, DISPATCH_REQUEST_SCHEMA,
    validate_dispatch_grant_binding, validate_envelope,
)


def internal_dispatch_identity(workspace_ref, production_run_ref, generation_dispatch_grant_ref):
    for name, value in (("workspaceRef", workspace_ref), ("productionRunRef", production_run_ref),
            ("generationDispatchGrantRef", generation_dispatch_grant_ref)):
        ref(value, name)
    return {"schemaVersion": "v4.generation-dispatch-job-idempotency.v1",
        "workspaceRef": workspace_ref, "productionRunRef": production_run_ref,
        "generationDispatchGrantRef": generation_dispatch_grant_ref}


def internal_dispatch_key(workspace_ref, production_run_ref, generation_dispatch_grant_ref):
    return DISPATCH_KEY_PREFIX + digest(internal_dispatch_identity(workspace_ref,
        production_run_ref, generation_dispatch_grant_ref))


def create_generation_dispatch_job(coordinator, *, verified_grant, request, envelope):
    """Internal V5 call after its stored-Grant/current-source verification under gate.

    The Grant is not an operator command and this function is not a public route.
    It binds and reserves only; original repository.create owns durability/replay.
    """
    _validate_method_aware_video_request(request)
    if request["schemaVersion"] != DISPATCH_REQUEST_SCHEMA:
        raise MediaJobError("Grant-bound request v2 is required")
    validate_envelope(envelope, request)
    binding = validate_dispatch_grant_binding(request["dispatchGrantBinding"])
    expected = {"generationDispatchGrantRef": verified_grant["generationDispatchGrantRef"],
        "generationDispatchGrantDigest": verified_grant["payloadDigest"],
        "subjectDigest": verified_grant["subjectDigest"],
        "approvedPlanDigest": verified_grant["approval"]["approvedPlanDigest"]}
    if (binding != expected or any(request[k] != verified_grant[k] for k in
            ("workspaceRef", "projectRef", "seriesRef", "episodeRef", "productionRunRef"))
            or request["createdAt"] != verified_grant["createdAt"]
            or envelope["backendBinding"] != verified_grant["executionBinding"]["backendDecision"]
            or envelope["outputConstraints"] != verified_grant["subject"]["outputConstraints"]):
        raise BackendValidationError("V5 Grant/request/envelope binding mismatch")
    subject = verified_grant["subject"]
    exact_source = {}
    for request_prefix, subject_key in (("methodAwareInputPlan", "methodAwareInputPlanVersion"),
            ("executionMethodPlan", "executionMethodPlanVersion")):
        exact_source[request_prefix + "VersionRef"] = subject[subject_key]["ref"]
        exact_source[request_prefix + "Digest"] = subject[subject_key]["digest"]
    for request_prefix, subject_key in (("visualExecutionRequirement", "visualExecutionRequirement"),
            ("creativeShotVersion", "creativeShotVersion"), ("beat", "actionExecutionBeat")):
        exact_source[request_prefix + "Ref"] = subject[subject_key]["ref"]
        exact_source[request_prefix + "Digest"] = subject[subject_key]["digest"]
    asset = subject["inputAsset"]
    exact_source.update(sourceImageAssetRef=asset["assetRef"], sourceImageAssetVersionRef=asset["assetVersionRef"],
        sourceImageAssetVersionDigest=asset["assetVersionDigest"], sourceImageContentDigest=asset["contentDigest"],
        sourceImageMediaType=asset["mediaType"])
    exact_source.update({key: subject[key] for key in
        ("sourceAction", "cameraInstruction", "frameRange", "executionClass", "executionMethod")})
    if (any(request[key] != value for key, value in exact_source.items())
            or envelope["sourceAsset"] != {key: value for key, value in asset.items() if key != "inputRole"}):
        raise BackendValidationError("request source is not the exact V5-verified Grant subject")
    key = internal_dispatch_key(verified_grant["workspaceRef"], verified_grant["productionRunRef"],
        verified_grant["generationDispatchGrantRef"])
    now = coordinator._clock()
    job = {"schemaVersion": DISPATCH_JOB_SCHEMA_VERSION,
        "workspaceRef": verified_grant["workspaceRef"],
        "productionRunRef": verified_grant["productionRunRef"],
        "jobRef": coordinator._ref_factory("media-job"), "idempotencyKey": key,
        "requestDigest": request["payloadDigest"], "request": deepcopy(request),
        "state": "QUEUED", "revision": 0, "attempts": [], "lease": None,
        "artifact": None, "artifactCommitIntent": None, "maxAttempts": 1,
        "executionScope": "SINGLE_EPISODE", "batchProductionAllowed": False,
        "createdAt": now, "updatedAt": now,
        "backendBinding": deepcopy(envelope["backendBinding"]),
        "executionContext": {"sourceText": envelope["semanticIntent"]["sourceAction"]["sourceText"],
            "outputConstraints": deepcopy(envelope["outputConstraints"])},
        "executionEnvelope": deepcopy(envelope), "dispatchGrantBinding": binding}
    return coordinator.repository.create(job)


# Storage handshake belongs below V5: original adapters participate even before
# a control domain exists. Sidecars are cooperative leases, never authority facts.
import os
from pathlib import Path
from threading import RLock, local

_STORAGE_MUTEX = RLock()
_CONTROLLED_STORAGE = {}
_ACCESS_COUNTS = {}
_ACCESS_OBSERVER = None
_UNCERTAIN = b"UNCERTAIN\n"


def _access_event(phase, path, **facts):
    if _ACCESS_OBSERVER is not None:
        _ACCESS_OBSERVER({"phase": phase, "path": str(path), **facts})


def storage_key(path):
    return Path(path).resolve()


def storage_lock_open(path, *, exclusive):
    """Take SH/EX on the same persistent inode, including the first access."""
    import fcntl
    key = storage_key(path)
    lock_path = key.with_name(key.name + ".dispatch-lock")
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        import stat
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise RuntimeError("storage lease identity is unavailable")
        fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        current = lock_path.lstat()
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise RuntimeError("storage lease inode changed")
        marker = os.pread(fd, 64, 0)
        if marker not in (b"", _UNCERTAIN) or (exclusive and marker):
            raise RuntimeError("storage takeover requires independently resolved uncertainty")
        return lock_path, fd, (info.st_dev, info.st_ino)
    except BaseException:
        os.close(fd)
        raise


def storage_access_snapshot(path):
    key = str(storage_key(path))
    with _STORAGE_MUTEX:
        return {"activeAccesses": _ACCESS_COUNTS.get(key, 0),
            "controlledRegistered": key in _CONTROLLED_STORAGE}


class _StorageAccess:
    def __init__(self, path, owner):
        self.path = storage_key(path)
        self._key = str(self.path)
        self._closed = False
        self._lock_release_unknown = False
        self._permit = None
        self._lock = None
        with _STORAGE_MUTEX:
            callback = _CONTROLLED_STORAGE.get(self._key)
            if callback is not None:
                self._permit = callback(owner)
                if self._permit is None:
                    raise RuntimeError("storage control has no lifetime permit")
            else:
                self._lock = storage_lock_open(self.path, exclusive=False)
            _ACCESS_COUNTS[self._key] = _ACCESS_COUNTS.get(self._key, 0) + 1
        _access_event("ACCESS_ENTER", self.path, controlled=self._permit is not None)

    def check(self):
        if self._closed or self._lock_release_unknown:
            raise RuntimeError("storage access has ended")
        if self._permit is not None:
            self._permit.check()
        elif self._lock is not None:
            path, fd, identity = self._lock
            current, opened = path.lstat(), os.fstat(fd)
            if (current.st_dev, current.st_ino) != identity or (opened.st_dev, opened.st_ino) != identity:
                self.unknown()
                raise RuntimeError("storage lease identity changed during access")

    def unknown(self):
        if self._permit is not None:
            self._permit.unknown()
        elif self._lock is not None:
            # This marker blocks takeover, not legacy reads/recovery. It is never
            # silently erased by successful rereads or by a new control epoch.
            os.pwrite(self._lock[1], _UNCERTAIN, 0)
        _access_event("ACCESS_OUTCOME_UNKNOWN", self.path)

    def close(self):
        if self._closed:
            return
        if self._lock_release_unknown:
            raise RuntimeError("storage lease close outcome is unknown")
        with _STORAGE_MUTEX:
            if self._permit is not None:
                self._permit.close()
            elif self._lock is not None:
                try:
                    os.close(self._lock[1])
                except BaseException:
                    self._lock_release_unknown = True
                    raise
            self._closed = True
            _ACCESS_COUNTS[self._key] -= 1
            if not _ACCESS_COUNTS[self._key]:
                del _ACCESS_COUNTS[self._key]
        _access_event("ACCESS_EXIT", self.path)

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, *args):
        self.close()
        return False


def storage_access(path, owner):
    return _StorageAccess(path, owner)


class StorageAccessRLock:
    """Acquire an access lifetime before the original RLock, also before takeover."""
    def __init__(self, owner, path_attribute):
        self.owner, self.path_attribute = owner, path_attribute
        self._inner = RLock()
        self._thread = local()

    def acquire(self, blocking=True, timeout=-1):
        access = storage_access(getattr(self.owner, self.path_attribute), self.owner)
        try:
            acquired = self._inner.acquire(blocking, timeout)
        except BaseException:
            access.close()
            raise
        if not acquired:
            access.close()
            return False
        self._thread.accesses = [*getattr(self._thread, "accesses", ()), access]
        return True

    def release(self):
        self._inner.release()
        access = self._thread.accesses.pop()
        access.close()

    def _is_owned(self):
        return self._inner._is_owned()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()
        return False


def storage_access_lock(owner, path_attribute):
    return StorageAccessRLock(owner, path_attribute)


class _StorageCursor:
    def __init__(self, cursor, connection):
        object.__setattr__(self, "_inner", cursor)
        object.__setattr__(self, "connection", connection)

    def __getattr__(self, name):
        value = getattr(self._inner, name)
        if name == "row_factory" or not callable(value):
            return value
        def call(*args, **kwargs):
            self.connection._access.check()
            result = value(*args, **kwargs)
            return self if result is self._inner else result
        return call

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)

    def __iter__(self):
        return self

    def __next__(self):
        self.connection._access.check()
        return next(self._inner)

    def close(self):
        return self._inner.close()


class _StorageConnection:
    """Forward SQLite semantics; context-manager exit commits/rolls back, not close."""
    def __init__(self, connection, access):
        object.__setattr__(self, "_inner", connection)
        object.__setattr__(self, "_access", access)
        object.__setattr__(self, "_closed", False)

    def __getattr__(self, name):
        value = getattr(self._inner, name)
        if self._closed or name in {"row_factory", "text_factory"} or not callable(value):
            return value
        def call(*args, **kwargs):
            import sqlite3
            self._access.check()
            result = value(*args, **kwargs)
            return _StorageCursor(result, self) if isinstance(result, sqlite3.Cursor) else result
        return call

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)

    def commit(self):
        self._access.check()
        try:
            return self._inner.commit()
        except BaseException:
            self._access.unknown()
            raise

    def rollback(self):
        try:
            return self._inner.rollback()
        except BaseException:
            self._access.unknown()
            raise

    def close(self):
        if self._closed:
            return
        try:
            self._inner.close()
        except BaseException:
            self._access.unknown()
            raise
        self._access.close()
        object.__setattr__(self, "_closed", True)

    def __enter__(self):
        self._access.check()
        self._inner.__enter__()
        return self

    def __exit__(self, *args):
        # Preserve the native SQLite __exit__ algorithm, including rollback if
        # commit itself fails. The connection/access remain live until close.
        try:
            return self._inner.__exit__(*args)
        except BaseException:
            self._access.unknown()
            raise

    def __del__(self):
        if not getattr(self, "_closed", True):
            try:
                self.close()
            except BaseException:
                # Retain the unresolved access; do not call a failed close a drain.
                pass


def connect_storage(path, owner, *args, **kwargs):
    import sqlite3
    access = storage_access(path, owner)
    try:
        access.check()
        connection = sqlite3.connect(path, *args, **kwargs)
        return _StorageConnection(connection, access)
    except BaseException:
        access.close()
        raise


def guard_controlled_storage_open(path, owner):
    # Compatibility name is deliberately not a momentary permit anymore.
    # All supported original adapters use connect_storage or storage_access_lock.
    raise RuntimeError("instantaneous storage guard cannot authorize access")


def register_controlled_storage(path, callback):
    key = str(storage_key(path))
    with _STORAGE_MUTEX:
        if key in _CONTROLLED_STORAGE or _ACCESS_COUNTS.get(key):
            raise RuntimeError("storage registration requires drained ownership")
        _CONTROLLED_STORAGE[key] = callback


def unregister_controlled_storage(path, callback):
    key = str(storage_key(path))
    with _STORAGE_MUTEX:
        if _CONTROLLED_STORAGE.get(key) is callback:
            if _ACCESS_COUNTS.get(key):
                raise RuntimeError("cannot unregister live storage access")
            del _CONTROLLED_STORAGE[key]
