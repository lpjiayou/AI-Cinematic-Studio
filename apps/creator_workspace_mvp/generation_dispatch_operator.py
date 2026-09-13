"""D1 trusted-host entry. Default invocation has no enabled deployment.

The existing Core composition host installs an independently approved deployment
object. Command-line fields cannot supply a factory, endpoint, authority record,
observation, database path, or permission. No import-time platform I/O.
"""
import argparse
import json


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


def main(argv=None, *, deployment=None):
    parser = argparse.ArgumentParser(description="D1 trusted internal single-subject Operator (default disabled)")
    parser.add_argument("operation", choices=("check-offline", "prepare", "inspect", "issue-approved",
        "route-approved", "execute-one", "recover"))
    parser.add_argument("--target-ref")
    args = parser.parse_args(argv)
    if args.operation == "check-offline":
        print(json.dumps({"operation": "CHECK_OFFLINE", "deploymentConfigured": deployment is not None,
            "storesOpened": False, "sendPermission": "NONE"}))
        return 0
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
