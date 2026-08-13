# ACS-ARCH-R1 V5 Text Generation G1-R1 Authorization

> Status: `GOVERNANCE-ONLY CHECKPOINT / CORRECTION AUTHORIZED`
>
> Decision date: `2026-08-13`
>
> Project Lead / Architecture Owner: `蔺鹏`
>
> Base candidate: `0c283eb653e74784301620bdaf64bf451bb687dd`
>
> Architecture authority: [`ADR-0006`](ADR-0006-v5-text-generation-capability-boundary.md)

## 1. Decision

The Project Lead directed the next step after independent re-verification found that
the G1 architecture guard can be bypassed by an aliased Python programmatic-import
primitive. The production dependency migration remains valid, but the candidate is
not ready for Owner Acceptance until the executable guard is corrected.

This checkpoint therefore records:

- G0 is `COMPLETE / REMOTE-VERIFIED` at
  `92d1f3ac9e08c71458af04514baa659555fc55a7`;
- the original G1 implementation is `REMOTE-VERIFIED CANDIDATE / REVISION REQUIRED`
  at `0c283eb653e74784301620bdaf64bf451bb687dd`;
- Application production imports of `services.v4_platform` remain `0`;
- no dynamic import primitive is present in the current Application production tree;
- the remaining defect is in the continuing architecture guard, not the production
  V5-to-V4 boundary;
- a bounded, test-only G1-R1 correction is authorized after this governance checkpoint
  is committed, pushed and remote-verified;
- the original G1 SHA is not Owner Accepted by this decision.

ADR-0006 remains accepted. No new architecture owner, production path, public API or
domain contract is introduced.

## 2. Confirmed defect

The original helper recognizes direct calls named `import_module` or `__import__` and
attributes named `import_module`, but it does not resolve imported local bindings.
For example, this form passes both the current AST helper and the literal target-text
check:

```python
from importlib import import_module as load

load("services" + ".v4_platform")
```

The defect also applies to aliases derived from `builtins.__import__` and simple
assignment aliases. Conversely, the current name-only approach can falsely reject an
unrelated local function or object method named `import_module`.

This means the production migration result is real, but the statement that the guard
mechanically prevents an aliased bypass is not yet proven.

## 3. Authorized sequence

The only authorized automatic sequence is:

```text
G1-R1 governance authorization
→ commit / push / remote verification
→ G1-R1 test-only guard correction
→ complete regression / commit / push / remote verification
→ STOP FOR PROJECT LEAD OWNER REVIEW
```

No other remediation or milestone may be entered automatically.

## 4. Governance checkpoint allowlist

This governance-only checkpoint may change exactly these eight paths:

```text
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
AI_CINEMATIC_STUDIO_UI_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
architecture/V5_TEXT_GENERATION_CAPABILITY_CONTRACT.md
governance/RISK_REGISTER.md
governance/ACS-ARCH-R1-V5-TEXT-GENERATION-G1-R1-AUTHORIZATION.md
```

Production and test source diff must be `0`. ADR-0006 and the historical G0 checkpoint
record must not be rewritten.

## 5. G1-R1 implementation allowlist

The correction may change exactly one path:

```text
tests/contract/test_creator_series_planning_contract.py
```

All production, Application, V5, V4, HTTP, persistence, SQLite, migration and
Frontend source files must have a zero diff.

## 6. Required guard behavior

The corrected guard must use binding-aware AST analysis and must reject access to the
accepted Python programmatic-import primitives through:

- direct built-in `__import__`;
- `importlib.import_module`;
- `importlib.__import__`;
- `builtins.__import__`;
- `import` and `from ... import ...` aliases;
- simple assignment aliases of a resolved primitive;
- constant `getattr` access to those primitives;
- wildcard import from `importlib` or `builtins`, failing closed.

The guard must not reject solely because an unrelated local function or object member
is named `import_module`. The literal target string check may remain only as defense in
depth; it is not proof against aliases, concatenation or reflection.

This is a lightweight static architecture gate, not a Python sandbox. General
`eval`/`exec`, arbitrary reflection, custom import hooks, cross-function container
flows and runtime code generation are not silently claimed as covered.

## 7. Mandatory correction tests

The correction must add positive rejection cases for at least:

- `from importlib import import_module as load`;
- `import importlib as alias` followed by `alias.import_module`;
- assignment aliases of `importlib.import_module` and direct `__import__`;
- `from builtins import __import__ as load`;
- `import builtins as alias` followed by `alias.__import__`;
- at least one multi-step simple alias chain;
- constant `getattr` access;
- target construction that avoids a literal `services.v4_platform` substring.

It must also prove no false positive for at least:

- a local function named `import_module`;
- an unrelated object's `import_module` method;
- an unrelated `importlib` API;
- an unrelated `builtins` API;
- a harmless string mentioning the target.

Existing tests may not be deleted, skipped or weakened.

## 8. Verification gates

After the one-file correction, all of the following are mandatory:

1. focused architecture-guard contract tests;
2. the complete previously reviewed targeted V5/Application set;
3. Unit, Contract and Integration discovery;
4. Full Core discovery without exclusions;
5. M6-P2 strict regression;
6. deletion/lifecycle regression;
7. non-test Python AST parse;
8. Application production V4 imports equal `0`;
9. only `services/v5_core_os/text_generation/public.py` imports V4 within that V5
   package;
10. secret scan and `git diff --check`;
11. one correction commit, non-force push, fetch and Local SHA equals Remote SHA;
12. ahead/behind `0/0` and clean worktree.

No browser or live provider call is required because the correction changes no
production or HTTP behavior.

## 9. Stop conditions

Stop if the correction requires:

- any implementation path outside the one-file allowlist;
- production, prompt, candidate, HTTP, provider, error-product or persistence changes;
- a new dependency or a change to ADR-0006;
- deletion, skip or weakening of an accepted test;
- M6-P3, M7+, formal port-8765, Auth/RBAC, Frontend, V3, GPU, Worker or ComfyUI work;
- force push, history rewrite or unresolved Local/Remote divergence.

After G1-R1 remote verification:

```text
STOP — CORRECTED ARCHITECTURE REMEDIATION CANDIDATE
PROJECT LEAD OWNER REVIEW REQUIRED
```

## 10. Risk and exclusions

`R-CORE-ARCH-001` remains `MITIGATING`. It cannot move to monitoring or closed until
the corrected candidate is remote-verified and separately Owner Accepted.
`R-CORE-GOV-002` remains `OPEN / NON-BLOCKING` and is not part of this work.

M6-P3-G0 remains on HOLD. M6-P3-B1, M6-P3-G1+, M7-M19, formal database deployment,
HTTP/Auth/RBAC expansion and Frontend remain unauthorized. Production Ready remains
`NO`.

## 11. Approval record

| Role | Owner | Decision | Date | Scope |
| --- | --- | --- | --- | --- |
| Project Lead | `蔺鹏` | `APPROVED` | `2026-08-13` | Begin the next step: correct the independently confirmed G1 guard defect |
| Architecture Owner | `蔺鹏` | `PRESERVED` | `2026-08-13` | ADR-0006 and `Application → V5 → V4` remain unchanged |
| Independent guard review | Read-only specialist review | `REVISION REQUIRED` | `2026-08-13` | Alias provenance, false positives and bounded static-analysis coverage |
