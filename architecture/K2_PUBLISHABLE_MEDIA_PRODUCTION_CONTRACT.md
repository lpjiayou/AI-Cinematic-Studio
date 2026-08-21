# K2 Publishable Media Production Contract

> Status: `Normative for ACS-K2-P0 → P10`
>
> Scope: the K2 canonical workspace, project, series, episode and production run

`2026-08-21` addendum: the previous durable instance was not found. ADR-0010 and the
K2 Canonical Lineage Bootstrap Contract govern establishment of one replacement
`ROOTS_READY` root. After that root is verified, this contract governs all downstream
facts unchanged. Historical refs/evidence are not silently attached to the new run.

## 1. Definition of publishable

A K2 master is publishable only when all of the following refer to the same exact,
non-stale lineage:

- rights-cleared source and reference inputs;
- approved provider/model execution evidence for selected image, video and audio;
- immutable validated V5 assets and deterministic V3 composition;
- passing machine QC and separate explicit human decisions;
- an immutable master/export with digest, probe, provenance and retention facts;
- a V5 publication-eligibility decision for a named destination and rights territory.

Playable, generated, machine-passing or human-approved alone does not mean
publishable.

## 2. Frozen upstream lineage

The production extension consumes the verified canonical K2 refs:

```text
Workspace → ContentProfile → Project → Series → Episode
→ confirmed ScriptVersion → M6 authority → IdentityLock
→ StoryboardVersion → CreativeShotVersion[*] → ExecutableShotGraph
→ AssetRequirement[*] → GenerationRequest[*]
```

Any changed upstream version makes downstream candidates stale. Display names, route
parameters and local filenames are never used to reconstruct authority.

## 3. Ownership and dependency matrix

| Layer | Owns | Forbidden |
| --- | --- | --- |
| Frontend | user intent, inspection and explicit approval entry | provider calls, secrets, SQL, publication derivation |
| Experience Adapter | server-only public API mapping and response validation | domain facts, worker/GPU access |
| Application | use-case orchestration and principal-derived scope | direct provider or V3 invocation |
| V5 | rights/policy versions, requests, accepted assets, selection, lineage, decisions and publication eligibility | queue leases, provider SDKs, rendering |
| V4 | jobs, attempts, leases, retry, cancellation, provider adapters, object handoff | domain acceptance, approval, publication |
| V3 | deterministic timeline composition and render evidence | candidate selection, rights/provider policy |
| Compute/provider | bounded execution and raw result metadata | authoritative project/asset/master facts |

The only direction is `Frontend → Public API → Application → V5 → V4 → V3/Compute`.

## 4. Pre-dispatch policy facts

### ProductionPolicyVersion

Carries stable ref/version/digest, project/run ownership, target duration, frame rate,
aspect ratio, resolution, codecs, language, quality thresholds, retry/cost ceilings,
retention policy, intended destinations and required decision kinds.

### RightsManifestVersion

Carries stable ref/version/digest and one entry per exact source/reference/input with:
asset digest, owner/licensor, grant basis, permitted uses, provider-processing consent,
territory, term, attribution, likeness/voice/music conditions and evidence reference.
An entry is not valid when required fields are missing, the term is expired, the use
or territory is incompatible, or the evidence reference is not resolvable.

Every grant is resolved through an injected rights-evidence authority and compared
with the complete canonical claim. A request body, filename or upload event cannot
grant rights. If a reference video is selected, its exact content digest and grant
must be present here; the inspected reference-video baseline remains design evidence
only and is not silently introduced as a production input.

### ProviderExecutionPolicyVersion

Carries allowed media type/provider/model/region combinations, approved endpoint
class, safety policy, privacy/retention choice, maximum attempts, timeouts, cost cap,
seed policy and whether GPU/runtime attestation is required.

When GPU/runtime attestation is required, the external provider-policy authority must
also return the exact opaque runtime-attestation ref and SHA-256 digest. Both are
recorded in the immutable provider policy and must match the V4 worker configuration
and returned runtime facts before provider submission or candidate acceptance.

Every selected provider/model/region combination is resolved through an injected
provider-policy authority. The recorded fact carries only opaque safe references to
the approved capability, credential source, usage terms and budget authority plus an
authority-evidence digest and expiry. No secret value enters V5 or the browser.

For the bounded P1 activation, the Creator runtime may load the two external
authority decisions only from operator-managed absolute file paths whose exact
SHA-256 digests are injected separately. Activation is atomic: the rights path,
rights digest, provider path and provider digest must all be present and valid, or
both authorities remain unavailable and startup fails closed. The provider bundle
has a closed field set and permits only an opaque `credentialSourceRef`; bearer
tokens, API keys and endpoint credentials are not authority facts and must remain in
the server/worker secret mechanism. These external files are runtime inputs and must
never be committed as production evidence merely because their schema validates.

All three are immutable and selected explicitly. Changing one stales later execution.

The browser projection of `production-readiness` is read-only. A production-policy
record may enter only through an authenticated server-side client; its `actorRef` is
derived from that credential by the Public API and is never accepted from request
JSON. The rights and provider authorities still verify every external claim before
the bundle can be recorded.

## 5. Candidate-to-asset transition

```text
GenerationRequest
→ V4 Job
→ ProviderAttempt
→ UntrustedCandidate
→ ArtifactValidation
→ CandidateSelection
→ immutable V5 AssetVersion
```

Validation covers digest, path/object-key containment, media probe, request parameter
match, rights/policy compatibility, moderation/safety status, provider provenance and
media-specific checks. Selection identifies the actor/authority and exact candidate
digest. A provider response or object URL alone never becomes an asset.

## 6. Image, video and audio requirements

- Images: dimensions, color space, identity/reference lineage, prompt/config digest,
  visual-quality evidence and selected use.
- Video: exact duration/frame-rate/dimensions, identity and motion continuity,
  temporal corruption checks, source image/shot lineage and synchronization anchors.
- Audio: typed dialogue/voice, ambience, effects and music stems; sample rate,
  channels, loudness/peak, timing, voice/music rights and transcript/cue lineage.

Provider-specific metadata remains in a versioned provenance envelope. Public API
projections expose safe facts, not credentials, private endpoints or storage paths.

## 7. Composition, QC and publication

V3 receives only explicitly selected immutable assets and a V5 `TimelineVersion`.
It returns an untrusted render handoff; V5 independently verifies and records the
preview/master artifact.

M14 machine QC must include technical integrity, A/V synchronization, loudness,
visual identity, shot continuity, subtitle/caption checks and rights/policy coverage.
Local regeneration creates a new request/candidate/selection lineage and never
overwrites an accepted version.

Required human decisions stay separate:

- `CREATIVE_DIRECTION`
- `IDENTITY_CONTINUITY`
- `TECHNICAL_QC`
- `FINAL_MASTER`
- `PUBLICATION_AUTHORIZATION`

Publication eligibility is a V5 derived fact over the exact master, destination,
rights manifest, production policy, QC report and decisions. It fails closed when any
input is stale, missing, rejected, expired or incompatible.

## 8. Runtime and persistence

Production execution requires durable relational facts, durable job/attempt state,
object storage with immutable keys/checksums, scoped service identity, injected
secrets, bounded logs/metrics/traces, retry/recovery and retention/deletion handling.
Restart, duplicate delivery, expired lease, partial upload, checksum mismatch,
provider timeout, budget exhaustion and foreign-workspace access are mandatory
failure tests.

SQLite and local filesystem remain accepted for deterministic tests only unless a
checkpoint explicitly records their bounded environment and non-production status.

## 9. Frontend activation

The existing production workspace is extended through the Experience Adapter. It
shows source class (`LOCAL_EVIDENCE` or live provider), rights/policy state, cost and
attempt facts, candidate/selection state, QC, approvals and next blocking action.
Unavailable capability is disabled with a reason; it is never represented by demo
records. The browser cannot submit workspace scope, provider secrets or a computed
publication flag.

## 10. Acceptance sequence

P0 through P10 execute only in the order frozen in
`K2_PUBLISHABLE_PRODUCTION_EXECUTION_PACKAGE.md`. Each checkpoint requires a committed
and remote-verified tree before the next begins. A blocked external gate may coexist
with completed safe implementation, but it cannot be reported as passed.
