"""Core operator CLI: preflight by default; --apply authorizes one CAS attempt."""

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.creator_workspace_mvp.episode_plan_binding_operator import (
    BindingOperatorError, EpisodePlanBindingOperator, load_operator_json, regular_file_path,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Managed operator configuration (absolute path)")
    parser.add_argument("--input", required=True, help="Closed binding command JSON (absolute path)")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_operator_json(regular_file_path(args.config).read_bytes())
        command = load_operator_json(regular_file_path(args.input).read_bytes())
        result = EpisodePlanBindingOperator(config).execute(command, apply=args.apply)
    except BindingOperatorError as exc:
        print(json.dumps({"ok": False, "error": {"code": exc.code}}))
        return 1
    except Exception:
        print(json.dumps({"ok": False, "error": {"code": "UNRESOLVED_OUTCOME"}}))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
