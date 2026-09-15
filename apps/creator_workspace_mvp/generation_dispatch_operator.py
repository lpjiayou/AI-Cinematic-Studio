"""D1 trusted-host entry. Default invocation has no enabled deployment.

The existing Core composition host installs an independently approved deployment
object. Command-line fields cannot supply a factory, endpoint, authority record,
observation, database path, or permission. No import-time platform I/O.
"""
import argparse
import json
from contextlib import contextmanager


@contextmanager
def open_generation_workspace_server(*, deployment, media_job_ref, public_authenticator,
        address=("127.0.0.1", 0), allowed_credential_refs=frozenset()):
    """Explicit trusted-host composition for the existing UI; never enabled by CLI.

    Owns the original deployment once, reuses its public participants, and waits
    for in-flight work before releasing the existing store/process boundary.
    Merely opening this context does not prepare, issue, route, or execute a Job.
    """
    from .server import create_server
    from services.v5_core_os.episode_production.generation_workspace import GenerationWorkspaceBoundary
    if address[0] != "127.0.0.1" or public_authenticator is None:
        raise ValueError("An authenticated loopback binding is required")
    with deployment.open() as operator:
        participants = operator.public_boundaries()
        workspace = GenerationWorkspaceBoundary(operator=operator, media_job_ref=media_job_ref,
            run_reader=participants["episode_production_boundary"], allowed_credential_refs=allowed_credential_refs)
        server = None
        try:
            server = create_server(address, object(), **participants,
                public_authenticator=public_authenticator, allow_internal_routes=False,
                generation_workspace_boundary=workspace, generation_only=True)
            yield server
        finally:
            if server is not None:
                server.server_close()
            workspace.close()


def execute_command(operator, operation, target_ref=None):
    """Single application consumer used by the host and isolated vertical tests."""
    if operation == "prepare":
        return operator.prepare()
    if operation == "issue-approved":
        return operator.issue()
    if operation == "inspect":
        return operator.inspect(target_ref)
    if operation == "route-approved":
        return operator.route(target_ref)
    if operation == "execute-one":
        return operator.execute_one(target_ref)
    if operation == "recover":
        return operator.recover(target_ref)
    raise ValueError("unsupported Operator mode")


def main(argv=None, *, deployment=None, host=None):
    parser = argparse.ArgumentParser(description="D1 trusted internal single-subject Operator (default disabled)")
    parser.add_argument("operation", choices=("check-offline", "check-inputs", "prepare", "inspect", "issue-approved",
        "route-approved", "execute-one", "recover"))
    parser.add_argument("--target-ref")
    args = parser.parse_args(argv)
    if host is not None:
        from services.v5_core_os.episode_production.generation_dispatch_host import D1OperatorHost
        if type(host) is not D1OperatorHost or deployment is not None:
            print(json.dumps({"code": "APPROVAL_UNAVAILABLE", "reason": "INVALID_TRUSTED_HOST_BINDING",
                "sendPermission": "NONE"}))
            return 2
    if args.operation == "check-offline":
        print(json.dumps({"operation": "CHECK_OFFLINE", "deploymentConfigured": deployment is not None,
            "storesOpened": False, "sendPermission": "NONE"}))
        return 0
    if args.operation == "check-inputs":
        if host is None:
            print(json.dumps({"code": "APPROVAL_UNAVAILABLE", "reason": "TRUSTED_HOST_DEPLOYMENT_NOT_INSTALLED",
                "sendPermission": "NONE"}))
            return 2
        from services.v5_core_os.episode_production.generation_dispatch_contracts import DispatchError
        try:
            print(json.dumps(host.check_inputs(), ensure_ascii=False))
            return 0
        except (DispatchError, ValueError, OSError) as exc:
            print(json.dumps({"code": getattr(exc, "code", "CONFIG_CHANGED"),
                "reason": "PINNED_INPUT_VALIDATION_FAILED", "sendPermission": "NONE"}))
            return 2
    if host is not None:
        deployment = host
    if deployment is None:
        print(json.dumps({"code": "APPROVAL_UNAVAILABLE", "reason": "TRUSTED_HOST_DEPLOYMENT_NOT_INSTALLED",
            "sendPermission": "NONE"}))
        return 2
    # Opening the host is explicit and separately authorized. It invokes only the
    # V5 public assembly seam; application code never opens an adapter or SQL.
    with deployment.open() as operator:
        result = execute_command(operator, args.operation, args.target_ref)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if "code" not in result else 2


if __name__ == "__main__":
    raise SystemExit(main())
