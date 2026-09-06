"""Stage one local image and emit a pinned technical-evidence bundle, without Core writes."""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import re
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.v4_platform.method_aware_input_artifacts import (
    BUNDLE_SCHEMA, ENTRY_SCHEMA, LINEAGE_FIELDS, SCOPE_FIELDS, MAX_IMAGE_BYTES,
    MethodAwareInputArtifactError, _read_regular, canonical, ref, seal,
    validate_entry, verify_image_file,
)


def build_bundle(*, image_path, source_root, bundle_path, authority_ref, media_type, fields):
    """All production scope and evidence references must be supplied by the operator."""
    ref(authority_ref)
    verified = verify_image_file(image_path, media_type)
    key = verified['contentDigest'] + {'image/png': '.png', 'image/jpeg': '.jpg'}[media_type]
    entry = seal({
        **fields, 'schemaVersion': ENTRY_SCHEMA, 'inputRole': 'ACTION_READY_ANCHOR',
        'storageKey': key, 'mediaType': media_type, 'byteSize': verified['byteSize'],
        'contentDigest': verified['contentDigest'], 'usageScope': 'TECHNICAL_EVIDENCE_ONLY',
        'providerProcessingAuthorized': False, 'publicationAllowed': False,
    })
    validate_entry(entry)
    root = Path(source_root)
    if root.is_symlink():
        raise MethodAwareInputArtifactError()
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve(strict=True)
    target = root / key
    data = _read_regular(image_path, MAX_IMAGE_BYTES)
    if len(data) != verified['byteSize'] or sha256(data).hexdigest() != verified['contentDigest']:
        raise MethodAwareInputArtifactError()
    try:
        with target.open('xb') as stream:
            stream.write(data)
    except FileExistsError:
        if _read_regular(target, MAX_IMAGE_BYTES) != data:
            raise MethodAwareInputArtifactError() from None
    verify_image_file(target, media_type, byte_size=verified['byteSize'], content_digest=verified['contentDigest'])
    verify_image_file(image_path, media_type, byte_size=verified['byteSize'], content_digest=verified['contentDigest'])
    bundle = {'schemaVersion': BUNDLE_SCHEMA, 'authorityRef': authority_ref, 'artifacts': [entry]}
    encoded = canonical(bundle)
    with Path(bundle_path).open('xb') as stream:
        stream.write(encoded)
    return {'bundleSha256': sha256(encoded).hexdigest(), 'stagedArtifactRef': entry['stagedArtifactRef'],
            'stagedArtifactDigest': entry['payloadDigest'], 'storageKey': key}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('image-path', 'source-root', 'bundle-path', 'authority-ref'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--media-type', required=True, choices=('image/png', 'image/jpeg'))
    field_names = SCOPE_FIELDS | LINEAGE_FIELDS | {'stagedArtifactRef', 'evidenceRef', 'evidenceDigest'}
    for field in sorted(field_names):
        parser.add_argument('--' + re.sub(r'([A-Z])', r'-\1', field).lower(), dest=field, required=True)
    values = vars(parser.parse_args(argv))
    fields = {name: values.pop(name) for name in field_names}
    try:
        print(canonical(build_bundle(**values, fields=fields)).decode('utf-8'))
    except (OSError, ValueError):
        parser.exit(1, 'method_aware_input_artifact_invalid\n')


if __name__ == '__main__':
    main()
