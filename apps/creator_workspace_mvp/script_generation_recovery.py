"""Orchestrate bounded Script recovery only through V5 public operations."""

from .script_studio import ScriptGenerationError, ScriptCandidateValidationError
from services.v5_core_os.script_studio import ScriptStudioPublicError


class ScriptGenerationRecoveryApplication:
    def __init__(self, boundary, generator):
        self.boundary, self.generator = boundary, generator

    def generate(self, command):
        reserved = self.boundary.reserve_generation(command)
        keyed = "idempotencyKey" in command
        if reserved["state"] == "COMPLETED":
            return 200, {**reserved["response"], "idempotentReplay": True}
        ticket = {k: reserved[k] for k in ("scope", "identityDigest")}
        recovered = reserved["state"] == "RESULT_READY"
        if not recovered:
            try:
                content = self.generator.generate(reserved["bootstrap"])
            except (ScriptGenerationError, ScriptCandidateValidationError) as exc:
                # Timeouts and unavailable transports do not prove that remote
                # execution stopped. Keep PENDING and its Episode exclusion.
                if isinstance(exc, ScriptCandidateValidationError) or exc.code == "invalid_provider_output":
                    self.boundary.fail_generation(ticket, "invalid_provider_output")
                    if keyed:
                        raise ScriptStudioPublicError("invalid_provider_output", 409) from None
                raise
            try:
                self.boundary.save_generation_result(ticket, content)
            except ScriptStudioPublicError as exc:
                if exc.code == "invalid_request":
                    self.boundary.fail_generation(ticket, "invalid_provider_output")
                    raise ScriptStudioPublicError("invalid_provider_output", 409) from None
                raise
        result = self.boundary.complete_generation(ticket)
        if keyed:
            result = {**result, "idempotentReplay": False}
            if recovered:
                result["recoveredFromResultReady"] = True
        return (200 if recovered else 201), result
