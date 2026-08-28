# K2-002 EP01 A100 shutdown archive restore

This archive preserves code-server buffers, authority worktree patches, execution manifests, and requested technical evidence before stopping the A100 compute instance.

## Frozen convergence baseline

- Branch: `feature/k2-002-ep01-batch-r3-convergence`
- Commit: `2a07118fbe962a6a073e62a05a8c70fac583cd66`
- Tree: `976657754417fcea0d5ad62ffcd1d83108836a6f`

## Validate after extraction

```bash
sha256sum -c ARCHIVE_SHA256SUMS.txt
```

The inner checksum file covers every archive payload and metadata file except the checksum file itself. The outer `.tar.zst.sha256` authenticates the complete compressed archive including this checksum file.

Missing requested source paths are recorded in `ARCHIVE_MANIFEST.json`. No missing path is fabricated.
