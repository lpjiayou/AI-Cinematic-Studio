# Creator Public API Authentication and Workspace Isolation Contract

Status: `AUTH-W1 NORMATIVE`

Authority: [`ADR-0007`](../governance/ADR-0007-creator-public-api-authentication-and-workspace-isolation.md)

This contract defines the exact security boundary for the existing Creator Public
HTTP/API v1. It adds no domain capability and changes no M1–M19 authorization state.

## 1. Runtime topology

```text
Browser
  └─ same-origin /api/creator/*
     └─ Frontend Experience Adapter (server only)
        ├─ CREATOR_CORE_BASE_URL
        ├─ CREATOR_CORE_TOKEN
        └─ CREATOR_CONTENT_PROFILE_REF
           └─ Authorization: Bearer <token>
              └─ Creator Public HTTP/API v1
                 └─ authenticated principal.workspaceRef
                    └─ Creator Application → V5 public boundary
```

Core is not a browser API. It must not add CORS or return its bearer credential,
credential digest, token configuration path or authenticated principal metadata.

## 2. Route classes

| Route class | Authentication | Workspace rule | Exposure |
| --- | --- | --- | --- |
| `/health` | none | none | liveness only |
| `/creator/api/v1/*` | bearer required | injected from principal | public server-to-server contract |
| `/creator/internal/*` | not part of public auth | historical request scope | loopback compatibility only |
| unknown path | none beyond class rule | none | stable 404 after required public authentication |

An unauthenticated request under `/creator/api/v1/*` returns 401 before route dispatch.
An authenticated unknown public route returns 404. A non-loopback server must disable
the complete `/creator/internal/*` class and return 404 for it.

## 3. Credential registry

The JSON document named by `CREATOR_PUBLIC_API_TOKEN_CONFIG` has this exact top-level
contract:

```json
{
  "schemaVersion": "creator.public-auth.v1",
  "credentials": [
    {
      "credentialRef": "frontend-deployment-a",
      "workspaceRef": "workspace-a",
      "tokenSha256": "<64 lowercase hexadecimal characters>",
      "enabled": true
    }
  ]
}
```

Rules:

1. the document must be UTF-8 JSON and no larger than 512000 bytes;
2. unknown top-level or credential fields are rejected;
3. `schemaVersion` must equal `creator.public-auth.v1`;
4. `credentialRef` and `workspaceRef` are unique, trimmed, non-empty strings of at most
   200 non-whitespace characters;
5. `tokenSha256` is a unique lowercase 64-character SHA-256 hex digest;
6. `enabled` is a required boolean; disabled credentials never authenticate;
7. at least one enabled credential is required;
8. a raw token is never accepted in the file and never persisted by Core;
9. invalid registry data aborts startup before the socket is opened.

Token hashing is `sha256(raw UTF-8 token bytes).hexdigest()`. Authentication compares
digests using constant-time comparison. Raw tokens should carry at least 256 bits of
entropy. Example values in documentation are placeholders, not usable credentials.

## 4. Public request authentication

The header grammar is exactly one `Authorization` header with scheme `Bearer` and one
non-empty token. Scheme comparison is case-insensitive; extra fields, repeated headers,
control characters or an oversized token are invalid.

All missing, malformed, disabled and unknown credentials return:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Cache-Control: no-store
Content-Type: application/json; charset=utf-8
```

```json
{
  "ok": false,
  "error": {
    "code": "authentication_required",
    "message": "Creator Core 身份验证失败。"
  }
}
```

The response deliberately does not distinguish missing, malformed, disabled or unknown
credentials.

## 5. Workspace authority

After authentication, the request owns exactly
`authenticatedPrincipal.workspaceRef`. Public clients must not provide `workspaceRef`
in either location:

- query parameter, including an empty or repeated value;
- JSON command body, including `null` or an empty value.

Any occurrence returns HTTP `400`:

```json
{
  "ok": false,
  "error": {
    "code": "client_workspace_scope_forbidden",
    "message": "工作区由服务身份确定，客户端不能指定。"
  }
}
```

Only after this check does the HTTP boundary inject the principal workspace into the
existing query/command mapping. All accepted downstream lifecycle and reference-scope
checks continue to run. Core responses may contain the accepted domain `workspaceRef`
where existing public DTOs already expose it; they must not expose credential metadata.

`contentProfileRef` is not an authentication claim in AUTH-W1. The Frontend Adapter
continues to strip browser values and inject its server-owned value only for accepted
Series and Project creation commands.

## 6. Server composition

| Environment variable | Required | Default | Rule |
| --- | --- | --- | --- |
| `CREATOR_PUBLIC_API_TOKEN_CONFIG` | yes | none | readable valid registry file |
| `CREATOR_PUBLIC_API_HOST` | no | `127.0.0.1` | valid bind host |
| `CREATOR_PUBLIC_API_PORT` | no | `8765` | integer `1..65535` |

Startup is fail-closed. Missing registry, invalid JSON/schema, duplicate values, no
enabled credential, invalid host/port or unreadable file produces a sanitized startup
error before listening.

Loopback is `127.0.0.0/8`, `::1` or `localhost`. Only loopback composition may retain
historical internal compatibility routes. Any other bind is public-only.

## 7. Frontend Experience Adapter

Frontend server configuration is:

| Variable | Required | Browser-visible |
| --- | --- | --- |
| `CREATOR_CORE_BASE_URL` | optional local default | no |
| `CREATOR_CORE_TOKEN` | yes | no |
| `CREATOR_CONTENT_PROFILE_REF` | optional local default | no |

`CREATOR_WORKSPACE_REF` is removed. The Adapter must:

1. strip browser `workspaceRef`, `contentProfileRef` and `tenantId` claims;
2. never append `workspaceRef` to a Core query or command;
3. set `Authorization: Bearer <CREATOR_CORE_TOKEN>` server-side;
4. inject only the server-owned `contentProfileRef` on accepted Series/Project creates;
5. preserve Core 401, 403 and stable product envelopes without fixture fallback;
6. never log, serialize to HTML, return, or include the token in a client bundle.

## 8. Status semantics

| Status | Meaning |
| --- | --- |
| `401 / authentication_required` | Frontend/Core service credential missing, invalid or out of sync |
| `400 / client_workspace_scope_forbidden` | a public caller attempted to select workspace scope |
| `403 / authority_unavailable` | authenticated workspace reached an accepted surface whose external authority is absent |
| `404 / not_found` | authenticated public route/resource absent, or internal route disabled |
| `503 / core_disconnected` | Frontend could not reach Core transport |

The UI must not present 401 as “Core disconnected” and must not present M6 403 as a
credential error.

## 9. Required verification

Core tests must prove:

- every declared public endpoint class is unavailable without a bearer credential;
- valid token authentication and principal workspace injection;
- query/body workspace claims are rejected;
- invalid and disabled tokens are indistinguishable;
- `/health` contains liveness only;
- non-loopback composition without a valid registry cannot start;
- internal routes are unavailable in public-only mode;
- no CORS response headers are emitted;
- existing domain, lifecycle, error and Full Core suites remain green.

Frontend tests must prove:

- the bearer header is added server-side;
- no workspace claim is sent to Core;
- browser scope claims remain stripped;
- missing token produces a configuration error without a Core call;
- 401 and 403 remain distinct stable states;
- no `NEXT_PUBLIC_*` security variable exists.

Gate C must use a runtime-generated high-entropy token, write only its digest to an
ephemeral Core registry, start both processes, exercise the browser-origin flow and
delete the ephemeral registry after process termination. Gate output must not print the
raw token or digest.

## 10. Stop conditions

Stop the wave rather than expand it if implementation requires:

- browser-to-Core access or CORS;
- user/session/RBAC/organization domain objects;
- persistent auth tables or schema migrations;
- changes below accepted Creator Application/V5 boundaries;
- M6 external authority or M7–M19 implementation;
- committed credentials, production data or provider secrets;
- weakening historical lifecycle/scope/confirmation protections.
