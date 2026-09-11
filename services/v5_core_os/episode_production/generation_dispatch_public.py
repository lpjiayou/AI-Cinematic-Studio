"""Explicit V5 boundary. Not exported/composed by any existing application."""
from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from . import generation_dispatch_contracts as c
from .generation_dispatch_foundation import GenerationDispatchFoundation


class GenerationDispatchPublicBoundary:
    def __init__(self, foundation: GenerationDispatchFoundation | None = None, *, preparation=None):
        self._foundation = foundation if foundation is not None else GenerationDispatchFoundation()
        self._preparation = preparation

    def prepare(self, command: Mapping) -> dict:
        try:
            c.validate_command("PREPARE", command)
            c.require(self._preparation is not None, "CURRENTNESS_FENCE_UNAVAILABLE")
            return deepcopy(self._preparation.prepare(command))
        except c.DispatchError as exc:
            return {"schemaVersion": c.PREFIX + "error.v1", "operation": "PREPARE_ONLY",
                "code": exc.code, "writesCommitted": 0, "sendPermission": "NONE"}
        except Exception:
            return {"schemaVersion": c.PREFIX + "error.v1", "operation": "PREPARE_ONLY",
                "code": "PERSISTENCE_UNAVAILABLE", "writesCommitted": 0, "sendPermission": "NONE"}

    def _call(self, operation: str, command: Mapping) -> dict:
        try:
            return deepcopy(getattr(self._foundation, operation.lower())(command))
        except c.CommitOutcomeUnknown:
            return {"schemaVersion": c.PREFIX + "indeterminate.v1", "operation": operation,
                "code": "COMMIT_OUTCOME_UNKNOWN", "sendPermission": "NONE"}
        except c.DispatchError as exc:
            return {"schemaVersion": c.PREFIX + "error.v1", "operation": operation,
                "code": exc.code, "writesCommitted": 0, "sendPermission": "NONE"}
        except Exception:
            # A non-contract failure may have followed an append or a context exit.
            # It is never sanitized into a false zero-write receipt.
            if operation != "INSPECT":
                return {"schemaVersion": c.PREFIX + "indeterminate.v1", "operation": operation,
                    "code": "COMMIT_OUTCOME_UNKNOWN", "sendPermission": "NONE"}
            return {"schemaVersion": c.PREFIX + "error.v1", "operation": operation,
                "code": "PERSISTENCE_UNAVAILABLE", "writesCommitted": 0, "sendPermission": "NONE"}

    def issue(self, command: Mapping) -> dict:
        return self._call("ISSUE", command)

    def inspect(self, command: Mapping) -> dict:
        return self._call("INSPECT", command)

    def revoke(self, command: Mapping) -> dict:
        return self._call("REVOKE", command)
