"""Read-only, digest-pinned authority for operator-staged input image bytes."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess
from typing import Any, Mapping, Protocol
import zlib

BUNDLE_SCHEMA = 'v4.method-aware-input-artifact-authority-bundle.v1'
ENTRY_SCHEMA = 'v4.method-aware-staged-input-artifact.v1'
PROJECTION_SCHEMA = 'v4.method-aware-input-artifact.v1'
MAX_IMAGE_BYTES = 100 * 1024 * 1024
SCOPE_FIELDS = frozenset({'workspaceRef','projectRef','seriesRef','episodeRef','productionRunRef'})
LINEAGE_FIELDS = frozenset({'executionMethodPlanVersionRef','executionMethodPlanDigest',
    'visualExecutionRequirementRef','visualExecutionRequirementDigest',
    'creativeShotVersionRef','creativeShotVersionDigest'})
ENTRY_FIELDS = SCOPE_FIELDS | LINEAGE_FIELDS | {'schemaVersion','stagedArtifactRef',
    'inputRole','storageKey','mediaType','byteSize','contentDigest','usageScope',
    'providerProcessingAuthorized','publicationAllowed','evidenceRef','evidenceDigest','payloadDigest'}
PROJECTION_FIELDS = frozenset({'schemaVersion','stagedArtifactRef','storageKey','mediaType',
    'byteSize','contentDigest','width','height','format','sourceAuthorityRef',
    'sourceEvidenceRef','sourceEvidenceDigest','payloadDigest'})
CONFIG_NAMES = ('CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_PATH',
    'CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_SHA256','CREATOR_METHOD_AWARE_SOURCE_ROOT')


class MethodAwareInputArtifactError(ValueError):
    def __init__(self, code='method_aware_input_artifact_invalid'):
        self.code=code
        super().__init__(code)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def digest(value): return sha256(canonical(value)).hexdigest()


def seal(value):
    result=deepcopy(dict(value)); result['payloadDigest']=digest(result); return result


def exact(value, fields):
    if not isinstance(value,Mapping) or set(value)!=set(fields): raise MethodAwareInputArtifactError()
    return value


def ref(value):
    if not isinstance(value,str) or not value.strip() or value!=value.strip() or len(value)>512 or any(ord(c)<32 for c in value):
        raise MethodAwareInputArtifactError()
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise MethodAwareInputArtifactError() from exc
    return value


def hex_digest(value):
    if not isinstance(value,str) or re.fullmatch('[0-9a-f]{64}',value) is None: raise MethodAwareInputArtifactError()
    return value


def integer(value, maximum=MAX_IMAGE_BYTES):
    if type(value) is not int or not 0<value<=maximum: raise MethodAwareInputArtifactError()
    return value


def storage_key(value):
    ref(value)
    path=PurePosixPath(value)
    if (path.is_absolute() or path.as_posix()!=value or any(p in {'','.', '..'} for p in value.split('/'))
            or '\\' in value or ':' in value): raise MethodAwareInputArtifactError()
    return value


def strict_json(data):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise MethodAwareInputArtifactError()
            result[key]=value
        return result
    def invalid(value): raise MethodAwareInputArtifactError()
    def number(value):
        if len(value)>128: raise MethodAwareInputArtifactError()
        return int(value)
    try:
        value=json.loads(data,object_pairs_hook=pairs,parse_constant=invalid,parse_int=number)
        def depth(v,n=0):
            if n>64: raise MethodAwareInputArtifactError()
            if isinstance(v,dict):
                for item in v.values(): depth(item,n+1)
            elif isinstance(v,list):
                for item in v: depth(item,n+1)
        depth(value)
        canonical(value)
        return value
    except (ValueError,TypeError,UnicodeError,RecursionError) as exc:
        raise MethodAwareInputArtifactError() from exc


def _open_regular(path: Path):
    """Open each path component without following symlinks, including parents."""
    path=Path(os.path.abspath(path))
    descriptor=os.open(path.anchor,os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
            os.close(descriptor); descriptor=next_fd
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=descriptor)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd); raise MethodAwareInputArtifactError()
        return fd
    finally: os.close(descriptor)


def _read_regular(path, limit):
    try:
        fd=_open_regular(Path(path))
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno()); integer(before.st_size,limit)
            data=stream.read(limit+1)
            after=os.fstat(stream.fileno())
            if len(data)!=before.st_size or any(getattr(before,k)!=getattr(after,k)
                for k in ('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')):
                raise MethodAwareInputArtifactError()
            return data
    except OSError as exc: raise MethodAwareInputArtifactError() from exc


def _png_structure(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'): raise MethodAwareInputArtifactError()
    offset=8; kinds=[]
    while offset+12<=len(data):
        length=struct.unpack('>I',data[offset:offset+4])[0]
        end=offset+length+12
        if end>len(data): raise MethodAwareInputArtifactError()
        kind=data[offset+4:offset+8]; payload=data[offset+8:end-4]
        if struct.unpack('>I',data[end-4:end])[0] != zlib.crc32(kind+payload): raise MethodAwareInputArtifactError()
        if kind in {b'acTL',b'fcTL',b'fdAT'}: raise MethodAwareInputArtifactError()
        kinds.append(kind); offset=end
        if kind==b'IEND': break
    if (offset!=len(data) or not kinds or kinds[0]!=b'IHDR' or kinds.count(b'IHDR')!=1
            or kinds[-1]!=b'IEND' or b'IDAT' not in kinds): raise MethodAwareInputArtifactError()


def probe_image(data, media_type):
    if media_type=='image/png': _png_structure(data)
    elif media_type=='image/jpeg':
        if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'): raise MethodAwareInputArtifactError()
    else: raise MethodAwareInputArtifactError()
    try:
        result=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','pipe',
            '-f',{'image/png':'png_pipe','image/jpeg':'jpeg_pipe'}[media_type],'-count_frames',
            '-show_entries','stream=codec_type,codec_name,width,height,nb_read_frames',
            '-of','json','pipe:0'],input=data,capture_output=True,check=True,timeout=30)
        streams=strict_json(result.stdout)['streams']
        if not isinstance(streams,list) or len(streams)!=1: raise MethodAwareInputArtifactError()
        stream=streams[0]; codec={'image/png':'png','image/jpeg':'mjpeg'}[media_type]
        if stream.get('codec_type')!='video' or stream.get('codec_name')!=codec or stream.get('nb_read_frames')!='1':
            raise MethodAwareInputArtifactError()
        return {'width':integer(stream['width'],16384),'height':integer(stream['height'],16384),
            'format':{'image/png':'png','image/jpeg':'jpeg'}[media_type]}
    except (OSError,KeyError,TypeError,ValueError,subprocess.SubprocessError) as exc:
        raise MethodAwareInputArtifactError() from exc


def verify_image_file(path, media_type, *, byte_size=None, content_digest=None):
    data=_read_regular(path,MAX_IMAGE_BYTES)
    size=len(data); content=sha256(data).hexdigest()
    if byte_size is not None and integer(byte_size)!=size: raise MethodAwareInputArtifactError()
    if content_digest is not None and hex_digest(content_digest)!=content: raise MethodAwareInputArtifactError()
    probe=probe_image(data,media_type)
    after=_read_regular(path,MAX_IMAGE_BYTES)
    if len(after)!=size or sha256(after).hexdigest()!=content: raise MethodAwareInputArtifactError()
    return {'byteSize':size,'contentDigest':content,**probe}


def validate_entry(value):
    exact(value,ENTRY_FIELDS)
    if value['schemaVersion']!=ENTRY_SCHEMA or value['payloadDigest']!=digest({k:v for k,v in value.items() if k!='payloadDigest'}):
        raise MethodAwareInputArtifactError()
    for name in SCOPE_FIELDS|LINEAGE_FIELDS|{'stagedArtifactRef','evidenceRef'}:
        (hex_digest if name.endswith('Digest') else ref)(value[name])
    for name in ('contentDigest','evidenceDigest'): hex_digest(value[name])
    integer(value['byteSize']); storage_key(value['storageKey'])
    if (value['mediaType'] not in {'image/png','image/jpeg'} or value['inputRole']!='ACTION_READY_ANCHOR'
            or value['usageScope']!='TECHNICAL_EVIDENCE_ONLY' or value['publicationAllowed'] is not False
            or value['providerProcessingAuthorized'] is not False): raise MethodAwareInputArtifactError()
    return deepcopy(dict(value))


class MethodAwareInputArtifactEvidencePort(Protocol):
    def resolve(self, *, staged_artifact_ref: str, staged_artifact_digest: str,
                scope: Mapping[str,str], lineage: Mapping[str,str]) -> dict[str,Any]: ...


class RejectingMethodAwareInputArtifactEvidence:
    def resolve(self, **kwargs):
        raise MethodAwareInputArtifactError('method_aware_input_artifact_unavailable')


class DigestPinnedMethodAwareInputArtifactEvidence:
    def __init__(self,bundle_path,expected_sha256,source_root):
        self._bundle_path=Path(bundle_path); self._expected=hex_digest(expected_sha256)
        original=Path(source_root)
        try:
            self._root=original.resolve(strict=True)
            if not self._root.is_dir() or original.is_symlink(): raise MethodAwareInputArtifactError()
        except OSError as exc: raise MethodAwareInputArtifactError() from exc
        self._load()

    def _load(self):
        data=_read_regular(self._bundle_path,4*1024*1024)
        if sha256(data).hexdigest()!=self._expected: raise MethodAwareInputArtifactError()
        bundle=exact(strict_json(data),{'schemaVersion','authorityRef','artifacts'})
        if bundle['schemaVersion']!=BUNDLE_SCHEMA: raise MethodAwareInputArtifactError()
        ref(bundle['authorityRef']); artifacts=bundle['artifacts']
        if not isinstance(artifacts,list) or not artifacts or len(artifacts)>1000: raise MethodAwareInputArtifactError()
        entries={}; identities=set()
        for raw in artifacts:
            value=validate_entry(raw); key=value['stagedArtifactRef']
            identity=tuple(value[k] for k in sorted(SCOPE_FIELDS|LINEAGE_FIELDS|{'inputRole'}))
            if key in entries or identity in identities: raise MethodAwareInputArtifactError()
            entries[key]=value; identities.add(identity)
        return bundle['authorityRef'],entries

    def resolve(self, *, staged_artifact_ref, staged_artifact_digest, scope, lineage):
        authority,entries=self._load()
        entry=entries.get(staged_artifact_ref)
        if entry is None or any(entry.get(k)!=v for k,v in scope.items()) or set(scope)!=SCOPE_FIELDS:
            raise MethodAwareInputArtifactError('method_aware_input_artifact_not_found')
        if (entry['payloadDigest']!=staged_artifact_digest or set(lineage)!=LINEAGE_FIELDS
                or any(entry[k]!=v for k,v in lineage.items())): raise MethodAwareInputArtifactError()
        key=storage_key(entry['storageKey']); path=self._root/key
        try:
            path.resolve(strict=True).relative_to(self._root)
        except (OSError,ValueError) as exc: raise MethodAwareInputArtifactError() from exc
        verified=verify_image_file(path,entry['mediaType'],byte_size=entry['byteSize'],content_digest=entry['contentDigest'])
        # The independently pinned manifest must still be identical after probing.
        self._load()
        return seal({'schemaVersion':PROJECTION_SCHEMA,'stagedArtifactRef':entry['stagedArtifactRef'],
            'storageKey':key,'mediaType':entry['mediaType'],**verified,'sourceAuthorityRef':authority,
            'sourceEvidenceRef':entry['evidenceRef'],'sourceEvidenceDigest':entry['evidenceDigest']})


def input_artifact_evidence_from_environment(environ):
    configured=[str(environ.get(name,'')).strip() for name in CONFIG_NAMES]
    if not any(configured): return RejectingMethodAwareInputArtifactEvidence()
    if not all(configured): raise MethodAwareInputArtifactError('method_aware_input_artifact_unavailable')
    return DigestPinnedMethodAwareInputArtifactEvidence(*configured)
