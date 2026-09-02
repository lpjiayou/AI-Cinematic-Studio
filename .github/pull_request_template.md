# Pull request

## Scope

Describe the bounded change and the authority that permits it.

## Verification

List exact checks and evidence. A work-in-progress result must not be described as a
formal `PASS` or acceptance.

## Document impact

Choose exactly one value and complete every field:

```text
DOC_IMPACT=NONE|STATUS|PUBLIC_CONTRACT|ARCHITECTURE|RUNTIME
DOC_FILES_REQUIRED=
DOC_FILES_UPDATED=
CURRENT_MILESTONE_UPDATE_REQUIRED=
PUBLIC_CONTRACT_UPDATE_REQUIRED=
ADR_REQUIRED=
RISK_REGISTER_UPDATE_REQUIRED=
FRONTEND_PIN_IMPACT=
```

If `DOC_IMPACT=NONE`, explain why no authoritative/current document changes. Do not
mechanically update every document or rewrite historical evidence.

## Boundary confirmation

- [ ] Accepted ADR semantics are unchanged unless this PR is the authorized ADR change.
- [ ] Historical failures and evidence remain truthful and readable.
- [ ] Production, provider, GPU, Approval, Master/Export and publication claims match evidence.
- [ ] Frontend pin impact is explicit and separately authorized when non-`NONE`.
