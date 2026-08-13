# V5 Text Generation Capability Contract

> Status: `ACCEPTED FOR BOUNDED ACS-ARCH-R1-V5-TEXT-GENERATION-G1`
>
> Authority: [`ADR-0006`](../governance/ADR-0006-v5-text-generation-capability-boundary.md)
>
> Decision owner: Project Lead / Architecture Owner `蔺鹏`
>
> Contract date: `2026-08-13`

## 1. Purpose

This contract defines the smallest behavior-preserving boundary that restores the
accepted dependency direction for text generation:

```text
Creator Application → V5 Core OS → V4 Platform → Provider Adapter
```

It replaces the current direct Application-to-V4 production imports. It does not
redesign the AI Director, Script Studio or Series Director use cases and does not add
a provider platform feature.

## 2. Ownership

| Concern | Owner |
| --- | --- |
| Use-case prompts and candidate repair orchestration | Creator Application |
| Candidate schema parsing and local semantic validation | Creator Application |
| Stable generation purpose, command, message, capability port and safe errors | V5 Core OS |
| Purpose-to-execution-policy selection | V5 Core OS |
| Mapping between V5 and V4 types/errors | V5 Core OS boundary implementation |
| Provider-neutral execution port and request | V4 Platform |
| Provider selection, transport and adapter response validation | V4 Platform |
| DeepSeek implementation and credentials | V4 Platform adapter/environment only |

V5 does not own AI Director, Script, Series Plan or provider facts. V4 does not own
candidate or production-domain identity. Application cannot configure or import V4.

## 3. V5 public types

The V5 package path is:

```text
services.v5_core_os.text_generation
```

### 3.1 Purpose

`TextGenerationPurpose` is a string enum with exactly these members and values:

| Member | Stable value |
| --- | --- |
| `AI_DIRECTOR_CANDIDATE` | `ai-director-candidate` |
| `SCRIPT_CANDIDATE` | `script-candidate` |
| `SCRIPT_SCENE_REWRITE` | `script-scene-rewrite` |
| `SERIES_PLAN_CANDIDATE` | `series-plan-candidate` |

No generic caller-controlled profile and no provider/model purpose are accepted.

### 3.2 Message

`TextGenerationMessage` is an immutable V5 DTO containing exactly:

```text
role: str
content: str
```

It is not a subclass or alias of V4 `TextMessage`. Application prompt builders return
tuples of this V5 type.

### 3.3 Command

`TextGenerationCommand` is an immutable V5 DTO containing exactly:

```text
purpose: TextGenerationPurpose
messages: tuple[TextGenerationMessage, ...]
```

It must not contain:

- `response_format`;
- `max_tokens`;
- `temperature`;
- `timeout_seconds`;
- provider, model or endpoint;
- API key, headers or transport configuration;
- retry, queue, worker or lifecycle controls.

### 3.4 Port

`TextGenerationCapability` is a V5-owned protocol:

```text
generate(command: TextGenerationCommand) → str
```

The return value is provider-generated candidate text. Generation success does not
make it a domain fact, confirm it, or bypass Application validation.

## 4. V5 stable errors

The V5 error surface contains:

```text
TextGenerationCapabilityError
├── TextGenerationConfigurationError
├── TextGenerationTimeoutError
└── TextGenerationUnavailableError
```

Every error may expose only:

```text
category: str
status: int | None
```

Its string representation, arguments and exposed exception chain are stable V5
diagnostics and must never contain a credential, Authorization header, endpoint
secret, raw provider output, raw response body or V4 exception text. The V5 boundary
must suppress raw V4 exception chaining at this Application-facing seam.

The mapping is:

| V4 condition | V5 error | Stable Application meaning |
| --- | --- | --- |
| provider configuration cannot be built or used | `TextGenerationConfigurationError` | `provider_unavailable` with safe category `credential_missing` or the safe V4 category |
| `ProviderTimeoutError` | `TextGenerationTimeoutError` | `provider_timeout` |
| any other `TextProviderError`, including unavailable or malformed transport response | `TextGenerationUnavailableError` | `provider_unavailable` |

V4 exception class names do not cross into Application. Application diagnostic fields
may retain the corresponding V5 exception class name only; public HTTP bodies remain
unchanged and contain no internal class name.

## 5. Execution profiles

V5 maps purpose to exactly one closed policy profile:

| Purpose | V4 response format | V4 max tokens | V4 temperature | V4 timeout seconds |
| --- | --- | ---: | ---: | ---: |
| `AI_DIRECTOR_CANDIDATE` | `json_object` | `6000` | `0.4` | `35.0` |
| `SCRIPT_CANDIDATE` | `json_object` | `8000` | `0.35` | `45.0` |
| `SCRIPT_SCENE_REWRITE` | `json_object` | `3500` | `0.35` | `45.0` |
| `SERIES_PLAN_CANDIDATE` | `json_object` | `16000` | `0.3` | `90.0` |

Unknown, missing or invalid purposes fail closed before a V4 provider call. No
Application input can override the profile.

The boundary creates new V4 `TextMessage` values and a new V4
`TextGenerationRequest`. It must not pass a V5 DTO directly based only on structural
similarity.

## 6. Composition and configuration

V5 exports these factories:

```text
create_text_generation_capability_from_environment(environ=None)
create_unconfigured_text_generation_capability()
```

The environment factory delegates provider construction to the existing V4
`create_text_provider_from_environment`. If provider construction fails with a safe
V4 configuration error, V5 returns the fail-closed unconfigured capability. It does
not return a V4 provider, propagate a V4 error or log configuration values.

The unconfigured capability raises `TextGenerationConfigurationError` only when a
generation command is attempted. This preserves server startup without credentials
while keeping each generation request fail-closed.

The Creator server imports only the V5 package. Its environment composition creates
one V5 capability instance and shares that instance with:

- `AiDirectorService`;
- `ScriptStudioApplicationService`;
- `SeriesDirectorApplicationService`.

`create_server` may use one V5 unconfigured capability for any omitted generation
service defaults. The server must not define a V4-compatible provider class, read
provider credentials itself, construct a provider request, or inspect the concrete V4
adapter.

The capability is intentionally not a field of `LifecycleAssembly`:

- it owns no domain fact;
- it performs no persistence transaction;
- it has no SQLite/InMemory parity meaning;
- binding provider credentials to lifecycle storage would create unrelated coupling.

## 7. Application migration contract

### 7.1 AI Director

- `_build_messages` returns V5 messages.
- `AiDirectorService` accepts `TextGenerationCapability`.
- each first or repair call sends purpose `AI_DIRECTOR_CANDIDATE`.
- existing prompt text, schema, one-repair maximum and candidate validation remain
  unchanged.
- V5 timeout maps to the existing `PlanGenerationError("provider_timeout")` and all
  other V5 capability failures map to the existing safe unavailable behavior.

### 7.2 Script Studio

- generation and repair use `SCRIPT_CANDIDATE`;
- single-scene rewrite uses `SCRIPT_SCENE_REWRITE`;
- `ScriptStudioApplicationService` accepts `TextGenerationCapability`;
- existing prompts, schema, validation diagnostics, repair limit and version writes
  remain unchanged;
- timeout/unavailable errors retain the current product-error semantics.

### 7.3 Series Director

- generation and repair use `SERIES_PLAN_CANDIDATE`;
- `SeriesDirectorApplicationService` accepts `TextGenerationCapability`;
- existing prompt, candidate contract, validation and repair behavior remain
  unchanged;
- no SeriesPlan, Episode or M6 ownership changes.

### 7.4 Server

- all `services.v4_platform` imports are removed;
- `_UnconfiguredTextProvider` is removed;
- service and capability environment assembly uses only the V5 public factories;
- endpoint paths, request/response DTOs, status behavior and safe diagnostic fields
  do not change; the internal `exception` diagnostic value necessarily changes from
  the V4 class name to the corresponding V5 class name and must remain secret-free.

## 8. Testing boundary

`services/v5_core_os/text_generation/testing.py` provides one test-only
`FakeTextGenerationCapability`. It:

- implements the V5 protocol;
- accepts deterministic `str | Exception` outcomes;
- records V5 commands in call order;
- raises a V5 unavailable error when outcomes are exhausted;
- imports no V4 type;
- is not re-exported by the production package `__all__`.

Application unit, contract and integration tests inject this V5 fake. Assertions move
from `provider.requests` to the equivalent recorded V5 commands and assert the exact
purpose plus message content.

The existing V4 adapter tests may directly import and test V4 in the existing
`TextProviderAdapterTests` section of `test_ai_director_phase1.py`. Those tests do not
inject V4 objects into an Application service. This is test-layer verification of V4,
not an Application production dependency.

## 9. Architecture guards

G1 adds an AST-based contract guard with these mandatory results:

```text
all apps/**/*.py imports of services.v4_platform = 0
```

The guard examines both `import` and `from ... import ...` forms. A textual target
check also prevents a dynamic/aliased bypass from becoming an accepted substitute.

Within `services/v5_core_os/text_generation`, only the V5-to-V4 implementation module
`public.py` may import `services.v4_platform`. Contracts, errors, package exports and
testing fake must have zero V4 imports.

The guard replaces the existing contract assertion that positively requires
`series_director.py` to import V4. This is an accepted contract correction, not a test
weakening: it changes the assertion from the rejected dependency to the newly accepted
adjacent-layer dependency and expands coverage to every Application source file.

## 10. G1 test matrix

G1 must prove at least:

1. every purpose maps to its exact V4 profile;
2. V5 messages are explicitly copied into new V4 messages;
3. missing provider configuration creates a fail-closed V5 capability;
4. V4 configuration, timeout and unavailable/malformed failures map to safe V5 errors;
5. safe V5 errors, arguments and exposed cause/context contain no raw provider text or
   secret;
6. all three Application services accept only the V5 capability contract;
7. initial and repair calls use the correct purpose and preserve call count;
8. Script candidate and scene rewrite select different profiles;
9. one environment-composed V5 capability is shared by all three services;
10. all four Application production files have no V4 import;
11. the existing HTTP candidate, validation, safe-error and persistence behavior
    remains passing;
12. targeted M1/M3/M5 and relevant lifecycle regression pass;
13. Full Core regression passes without excluding accepted tests.

Tests must not be deleted, skipped, weakened or rewritten only to inspect a private V4
object through Application. V4 tests and V5/Application tests remain semantically
separate.

## 11. Exact G1 allowlist

### Production/source — exactly nine paths

```text
services/v5_core_os/text_generation/__init__.py
services/v5_core_os/text_generation/contracts.py
services/v5_core_os/text_generation/errors.py
services/v5_core_os/text_generation/public.py
services/v5_core_os/text_generation/testing.py
apps/creator_workspace_mvp/ai_director.py
apps/creator_workspace_mvp/script_studio.py
apps/creator_workspace_mvp/series_director.py
apps/creator_workspace_mvp/server.py
```

### Tests — exactly eleven paths

```text
tests/unit/test_v5_text_generation_boundary.py
tests/unit/test_ai_director_phase1.py
tests/unit/test_script_studio_m3.py
tests/unit/test_series_planning_m5.py
tests/integration/test_ai_director_project_draft_flow.py
tests/integration/test_creator_project_context.py
tests/integration/test_creator_script_studio.py
tests/integration/test_creator_series_episode.py
tests/integration/test_creator_series_planning.py
tests/contract/test_creator_core_no_legacy_ui_contract.py
tests/contract/test_creator_series_planning_contract.py
```

## 12. Compatibility and non-goals

G1 must preserve:

- all public HTTP paths and JSON schemas;
- candidate schema versions and domain version schemas;
- current prompt content and repair limits;
- environment names `TEXT_PROVIDER`, `TEXT_MODEL`, `PROVIDER_API_KEY`;
- current V4 public contract and DeepSeek behavior;
- persistence, lineage, lifecycle and accepted M1-M6 behavior;
- Frontend freeze and formal port-8765 non-deployment.

G1 does not add telemetry, quota, tenant policy, content safety, retries, async jobs,
provider routing or model registry. Those may use the boundary later only through
separately accepted work.

## 13. Stop and rollback

Stop immediately if implementation requires:

- any path outside the exact allowlist;
- a V4 public API or provider-adapter behavior change;
- prompt, candidate, HTTP, persistence or domain-contract change;
- a new dependency, schema, migration, credential or external live call;
- weakening/deleting an accepted test;
- an architecture exception instead of the accepted adjacent-layer result;
- work in M6-P3, M7+, Frontend or formal deployment;
- a commit based on an unverified G0 SHA;
- unresolved test, secret, Git or Source-of-Truth conflict.

Rollback uses the isolated G1 commit and branch. No data rollback exists. Revert the
G1 commit normally or abandon the branch while preserving the remote-verified G0 SHA;
never force push. After G1 remote verification, stop for Project Lead owner review.
