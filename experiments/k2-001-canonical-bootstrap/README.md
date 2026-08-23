# K2-001 canonical lineage bootstrap specification

This directory contains the exact, Project-Lead-authorized input for one new K2-001
canonical root after the previous durable lineage was not found.

The specification is input to the bounded Operator Application. It is not proof that
the canonical directory exists, and it grants no M6, Identity Lock, Rights, Provider,
budget, P1 or publication authority.

Validation is write-free:

```bash
python scripts/k2_canonical_lineage_bootstrap.py \
  --spec experiments/k2-001-canonical-bootstrap/k2-001-canonical-bootstrap.v1.json \
  --target-dir /data/k2-core/k2-001-canonical-v1
```

Formal apply must follow the GPU-host section of the K2 P1 runbook and requires the
exact `NEW_CANONICAL_K2_LINEAGE_NOT_RECOVERY` acknowledgement.

After apply and the independent read-only scan, the same runbook starts a loopback
Creator server with a workspace-scoped server credential and invokes
`scripts/k2_canonical_lineage_api_verify.py`. That verifier performs authenticated
GET-only exact-match checks and emits a secret-free verification receipt. It does not
advance M6, Identity Lock, P1 or publication.
