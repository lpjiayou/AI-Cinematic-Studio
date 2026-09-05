# Core Public JSON and Numeric Integrity Hardening — 2026-09-05

Status: `CURRENT / IMPLEMENTED_AND_VERIFIED / FAIL-CLOSED`

Owner: `Project Lead / Creator Public Contract Owner / V5 Domain Owners`

Task: `ACS-CORE-PUBLIC-JSON-AND-NUMERIC-INTEGRITY-HARDENING-A`

## Result

This checkpoint closes three bounded Creator public-input integrity vectors without
changing the public resource set, route set, successful response schemas, database
schema, dependencies, workflows, Frontend or production/runtime authority.

```text
CORE_PUBLIC_JSON_AND_NUMERIC_INTEGRITY=IMPLEMENTED_AND_VERIFIED
B1_NONFINITE_DURABLE_RECORD_VECTOR=CLOSED
B3_INTEGER_COERCION_VECTOR=CLOSED
B4_JSON_PARSER_RESOURCE_ERROR_VECTOR=CLOSED

PUBLIC_JSON_MAX_DEPTH=64
PUBLIC_JSON_MAX_NUMBER_TOKEN_CHARS=128
PUBLIC_JSON_NONFINITE_ALLOWED=false
PUBLIC_JSON_OUTPUT_ALLOW_NAN=false

INVALID_INPUT_DURABLE_MUTATION_COUNT=0
DATABASE_SCHEMA_DIFF=0
```

## Read-only reachability audit

The baseline audit distinguished request-reachable validation from configuration,
provider-output and already-validated record handling.

```text
PUBLIC_JSON_PARSE_ENTRY_COUNT=1
PUBLIC_JSON_RESPONSE_SERIALIZER_COUNT=1
PUBLIC_REACHABLE_COERCIVE_INTEGER_HELPER_COUNT=5
PUBLIC_REACHABLE_NONFINITE_NUMBER_RISK_COUNT=5
```

The five coercive helpers were Project Context `_positive_int`, Series/Episode
`_positive_int`, Script Studio `_positive_int`, and Series Intelligence
`_positive_int` plus `_nonnegative_int`. The five non-finite risk classes were the
raw public request decoder, the public response serializer, AI Director plan
validation/copy, Series/Episode plan JSON copy, and Script Studio positive-number
validation/persistence.

Series Planning, Episode Production, canonical migration and provider-output-only
numeric handling were audited separately. Their relevant public/version validators
were already strict or consumed validated server-owned facts, so this task did not
change those production files.

## Closed behavior

- Raw UTF-8 request text is scanned iteratively and string/escape-aware before
  `json.loads`; nesting above 64 is rejected without recursive pre-validation.
- `NaN`, `Infinity`, `-Infinity`, finite-overflow floats and numeric tokens longer
  than 128 characters return `400 / invalid_request` in the standard envelope.
- Publicly reachable integer helpers require `type(value) is int`; booleans,
  floats, strings, nulls and non-finite numbers are not coerced.
- AI Director storyboard durations and their running total must remain finite and
  positive before a plan can reach confirmation or JSON copy.
- Every touched durable JSON copy and every public HTTP response uses
  `allow_nan=False`; a response serialization violation becomes a complete
  `500 / application_error` response before headers are sent.

The existing request-size limit remains 512000 bytes. Duplicate-key behavior is
unchanged. Existing domain error codes and all valid request/response shapes remain
unchanged.

## Evidence boundary

Regression tests first reproduced all three baseline defects, including a durable
NaN plan record, fractional integer truncation, and an uncaught deep-decoder
`RecursionError`. The repaired suite uses the real request handler, temporary SQLite,
strict response parsing and restart reads. Invalid cases leave every SQLite table and
the relevant domain-call count unchanged; a valid request succeeds after a rejected
25,000-level body.

This checkpoint does not authorize Provider, GPU, M12, M13, asset admission,
publication or Frontend implementation.

```text
B2_SERIES_PLANNING_SCOPE_ERROR=NOT_IN_THIS_PR
F4_CORE_CANDIDATE_SOURCE_BINDING=NOT_IN_THIS_PR
FRONTEND_PIN_IMPACT=NONE_UNLESS_VALID_REQUEST_CONTRACT_DRIFT_IS_PROVEN
NEXT_TASK=ACS-CORE-SERIES-PLANNING-SCOPE-AND-CANDIDATE-BINDING-HARDENING-B
```
