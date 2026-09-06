"""Current single-image intake and admission on the existing evidence journal."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Mapping

from services.v4_platform.method_aware_input_artifacts import (
    MethodAwareInputArtifactError, RejectingMethodAwareInputArtifactEvidence,
    SCOPE_FIELDS, LINEAGE_FIELDS, PROJECTION_FIELDS, PROJECTION_SCHEMA,
    exact, hex_digest, integer, ref, storage_key,
)
from .evidence import EvidenceRecord
from .foundation import (EpisodeProductionError, RecordNotFoundError, StaleInputError,
    IdempotencyConflictError, _digest, _idempotency_key)
from .media_candidate_review import (CANDIDATE,TECHNICAL_VALIDATION,SEMANTIC_VISUAL_QC,
    HUMAN_SELECTION,ASSET_ADMISSION,ASSET_VERSION,MediaSelectionSubject,VerifiedMediaSelection,
    MediaSelectionApprovalRequiredError,VISUAL_QC_PROFILE_DIGEST)

RECEIPT_KIND='MethodAwareInputArtifact'
RECEIPT_SCHEMA='v5.method-aware-input-artifact-receipt.v1'
ADMISSION_SCHEMA='v5.method-aware-input-asset-admission.v1'
ASSET_SCHEMA='v5.method-aware-input-image-asset-version.v1'
INPUT_ROLE='ACTION_READY_ANCHOR'
VALIDATOR_REF='v4-method-aware-input-artifact-verifier-v1'
PLAN_FIELDS=frozenset({'executionMethodPlanVersionRef','executionMethodPlanDigest',
    'visualExecutionRequirementRef','visualExecutionRequirementDigest'})
INTAKE_FIELDS=SCOPE_FIELDS|PLAN_FIELDS|{'stagedArtifactRef','stagedArtifactDigest','idempotencyKey'}
ADMIT_FIELDS=SCOPE_FIELDS|PLAN_FIELDS|{'humanSelectionRef','humanSelectionVersion','humanSelectionDigest','idempotencyKey'}
RECEIPT_FIELDS=SCOPE_FIELDS|LINEAGE_FIELDS|{'schemaVersion','inputArtifactReceiptRef','version',
    'inputRole','inputRequirementKey','stagedArtifactRef','stagedArtifactDigest','artifact',
    'authorityState','providerProcessingAuthorized','publicationAllowed','createdAt','payloadDigest'}
CHAIN_FIELDS=frozenset({'sourceArtifactReceiptRef','sourceArtifactReceiptDigest',
    'technicalValidationRef','technicalValidationDigest','semanticVisualQcRef','semanticVisualQcDigest',
    'humanSelectionRef','humanSelectionDigest'})
ASSET_FIELDS=SCOPE_FIELDS|LINEAGE_FIELDS|CHAIN_FIELDS|{'schemaVersion','assetRef','assetVersionRef','version',
    'inputRequirementKey','inputRole','sourceCandidateRef','sourceCandidateDigest','assetAdmissionRef',
    'mediaKind','mediaType','artifactRef','storageKey','byteSize','sha256','probe','provenance',
    'authorityState','providerProcessingAuthorized','state','immutable','publicationAllowed','createdAt','payloadDigest'}
ADMISSION_FIELDS=SCOPE_FIELDS|LINEAGE_FIELDS|CHAIN_FIELDS|{'schemaVersion','assetAdmissionRef',
    'assetVersionRef','assetVersionDigest','candidateRef','candidateDigest','inputRequirementKey','inputRole',
    'admissionState','publicationAllowed','createdAt','payloadDigest'}
CHECKS=('staged-authority-exact','workspace-run-scope-exact','execution-plan-current',
    'visual-requirement-current','regular-file','no-symlink','root-containment','byte-size-valid',
    'sha256-valid','single-image-stream','media-type-valid','dimensions-valid',
    'technical-evidence-only','publication-disabled')


class MethodAwareInputAssetError(EpisodeProductionError):
    def __init__(self,code='method_aware_input_artifact_invalid',status=None):
        self.code=code
        self.status=status or {'method_aware_input_artifact_unavailable':503,
            'method_aware_input_artifact_not_found':404,'method_aware_input_scope_mismatch':404}.get(code,409)
        super().__init__(code)


def sealed(value):
    result=deepcopy(dict(value)); result['payloadDigest']=_digest(result); return result


def checked(value,fields=None):
    try:
        if fields is not None: exact(value,fields)
        if not isinstance(value,Mapping) or value.get('payloadDigest')!=_digest({k:v for k,v in value.items() if k!='payloadDigest'}):
            raise MethodAwareInputArtifactError()
        return deepcopy(dict(value))
    except (ValueError,TypeError,RecursionError) as exc: raise MethodAwareInputAssetError() from exc


def record_payload(record,kind):
    if not isinstance(record,Mapping) or record.get('recordKind')!=kind: raise MethodAwareInputAssetError()
    payload=checked(record.get('payload'))
    if payload['payloadDigest']!=record.get('payloadDigest'): raise MethodAwareInputAssetError()
    return payload


def exact_record(records,kind,record_ref,digest=None,version=1):
    matches=[r for r in records if r.get('recordKind')==kind and r.get('recordRef')==record_ref
        and (version is None or r.get('recordVersion')==version) and (digest is None or r.get('payloadDigest')==digest)]
    if len(matches)!=1: raise MethodAwareInputAssetError('method_aware_input_selection_required')
    return record_payload(matches[0],kind)


def probe_for(artifact):
    return {'width':artifact['width'],'height':artifact['height'],'format':artifact['format'],
        'streamCount':1,'frameCount':1}


def validate_receipt(value):
    value=checked(value,RECEIPT_FIELDS)
    try:
        if (value['schemaVersion']!=RECEIPT_SCHEMA or type(value['version']) is not int or value['version']!=1
                or value['inputRole']!=INPUT_ROLE or value['authorityState']!='TECHNICAL_EVIDENCE_ONLY'
                or value['publicationAllowed'] is not False or value['providerProcessingAuthorized'] is not False
                or value['inputRequirementKey']!='action-ready-anchor:'+value['visualExecutionRequirementRef']):
            raise MethodAwareInputArtifactError()
        for name in SCOPE_FIELDS|LINEAGE_FIELDS|{'inputArtifactReceiptRef','stagedArtifactRef','stagedArtifactDigest'}:
            (hex_digest if name.endswith('Digest') else ref)(value[name])
        artifact=checked(value['artifact'],PROJECTION_FIELDS)
        if artifact['schemaVersion']!=PROJECTION_SCHEMA or artifact['stagedArtifactRef']!=value['stagedArtifactRef']:
            raise MethodAwareInputArtifactError()
        for name in ('stagedArtifactRef','sourceAuthorityRef','sourceEvidenceRef'):ref(artifact[name])
        for name in ('contentDigest','sourceEvidenceDigest'):hex_digest(artifact[name])
        integer(artifact['byteSize']);integer(artifact['width'],16384);integer(artifact['height'],16384)
        storage_key(artifact['storageKey'])
        if artifact['format']!={'image/png':'png','image/jpeg':'jpeg'}.get(artifact['mediaType']):
            raise MethodAwareInputArtifactError()
        return value
    except (ValueError,TypeError,KeyError) as exc:raise MethodAwareInputAssetError() from exc


def validate_asset_version(value,*,records,workspace_ref,run_ref,root=None):
    """Closed persisted-row validation; no new authority or historical rewrite."""
    asset=checked(value,ASSET_FIELDS)
    try:
        for name in SCOPE_FIELDS|LINEAGE_FIELDS|CHAIN_FIELDS|{'assetRef','assetVersionRef',
                'sourceCandidateRef','sourceCandidateDigest','assetAdmissionRef','artifactRef'}:
            (hex_digest if name.endswith('Digest') else ref)(asset[name])
        if (asset['schemaVersion']!=ASSET_SCHEMA or asset['workspaceRef']!=workspace_ref
                or asset['productionRunRef']!=run_ref or asset['mediaKind']!='image'
                or asset['inputRole']!=INPUT_ROLE or asset['provenance']!='IMPORTED'
                or asset['authorityState']!='TECHNICAL_EVIDENCE_ONLY' or asset['providerProcessingAuthorized'] is not False
                or asset['state']!='REGISTERED' or asset['immutable'] is not True
                or asset['publicationAllowed'] is not False or type(asset['version']) is not int or asset['version']!=1):
            raise MethodAwareInputArtifactError()
        if root is not None and any(asset[k]!=root[k] for k in SCOPE_FIELDS):raise MethodAwareInputArtifactError()
        integer(asset['byteSize']);hex_digest(asset['sha256']);storage_key(asset['storageKey'])
        exact(asset['probe'],{'width','height','format','streamCount','frameCount'})
        for name in ('width','height','streamCount','frameCount'):
            integer(asset['probe'][name],16384)
        receipt=validate_receipt(exact_record(records,RECEIPT_KIND,asset['sourceArtifactReceiptRef'],asset['sourceArtifactReceiptDigest']))
        if any(asset[k]!=receipt[k] for k in SCOPE_FIELDS|LINEAGE_FIELDS|{'inputRole','inputRequirementKey'}):raise MethodAwareInputArtifactError()
        artifact=receipt['artifact']
        if (asset['artifactRef']!=artifact['stagedArtifactRef'] or asset['sha256']!=artifact['contentDigest']
                or asset['probe']!=probe_for(artifact)
                or any(asset[k]!=artifact[k] for k in ('storageKey','mediaType','byteSize'))):raise MethodAwareInputArtifactError()
        candidate=exact_record(records,CANDIDATE,asset['sourceCandidateRef'],asset['sourceCandidateDigest'])
        validation=exact_record(records,TECHNICAL_VALIDATION,asset['technicalValidationRef'],asset['technicalValidationDigest'])
        qc=exact_record(records,SEMANTIC_VISUAL_QC,asset['semanticVisualQcRef'],asset['semanticVisualQcDigest'],version=None)
        selection_matches=[r for r in records if r.get('recordKind')==HUMAN_SELECTION
            and r.get('recordRef')==asset['humanSelectionRef'] and r.get('payloadDigest')==asset['humanSelectionDigest']]
        if len(selection_matches)!=1:raise MethodAwareInputArtifactError()
        selection=record_payload(selection_matches[0],HUMAN_SELECTION)
        admission=checked(exact_record(records,ASSET_ADMISSION,asset['assetAdmissionRef']),ADMISSION_FIELDS)
        validate_candidate_chain(receipt,candidate,validation)
        if (qc['candidateRef']!=asset['sourceCandidateRef'] or qc['candidateDigest']!=asset['sourceCandidateDigest']
                or qc['technicalValidationRef']!=asset['technicalValidationRef'] or qc['technicalValidationDigest']!=asset['technicalValidationDigest']
                or qc['result']!='PASS' or qc['assessmentProfileDigest']!=VISUAL_QC_PROFILE_DIGEST
                or selection['visualQcRef']!=asset['semanticVisualQcRef'] or selection['visualQcDigest']!=asset['semanticVisualQcDigest']
                or selection['candidateRef']!=asset['sourceCandidateRef'] or selection['candidateDigest']!=asset['sourceCandidateDigest']
                or selection['decision']!='SELECTED' or selection['actorKind']!='HUMAN'
                or any(p['publicationAllowed'] is not False for p in (qc,selection,admission))):raise MethodAwareInputArtifactError()
        for name in ('actorRef','authorityRef','authorityDecisionRef','approvalRef','authorityDecidedAt'):
            ref(selection[name])
        expected_decision=VerifiedMediaSelection.expected_decision_digest(
            authority_ref=selection['authorityRef'],approval_ref=selection['approvalRef'],
            actor_ref=selection['actorRef'],actor_kind=selection['actorKind'],decision=selection['decision'],
            authority_decision_ref=selection['authorityDecisionRef'],decided_at=selection['authorityDecidedAt'],
            subject_digest=selection['subjectDigest'])
        if selection['authorityDecisionDigest']!=expected_decision:raise MethodAwareInputArtifactError()
        subject=selection_subject(receipt, candidate, qc)
        if selection['subjectDigest']!=subject.subject_digest:raise MethodAwareInputArtifactError()
        if (admission['schemaVersion']!=ADMISSION_SCHEMA or admission['admissionState']!='ADMITTED'
                or admission['assetVersionRef']!=asset['assetVersionRef'] or admission['assetVersionDigest']!=asset['payloadDigest']
                or admission['candidateRef']!=asset['sourceCandidateRef'] or admission['candidateDigest']!=asset['sourceCandidateDigest']
                or any(admission[k]!=asset[k] for k in SCOPE_FIELDS|LINEAGE_FIELDS|CHAIN_FIELDS|{'inputRole','inputRequirementKey','assetAdmissionRef'})):
            raise MethodAwareInputArtifactError()
        return asset
    except (ValueError,KeyError,TypeError) as exc:raise MethodAwareInputAssetError() from exc


def validate_candidate_chain(receipt,candidate,validation):
    artifact=receipt['artifact']
    try:
        integer(candidate['candidateVersion'],1)
        integer(candidate['artifactByteSize'])
        integer(validation['candidateVersion'],1)
        integer(validation['technicalValidationVersion'],1)
        if any(check.get('passed') is not True for check in validation['checks']):
            raise MethodAwareInputArtifactError()
    except (ValueError,KeyError,TypeError,AttributeError) as exc:
        raise MethodAwareInputAssetError() from exc
    if (candidate.get('schemaVersion')!='v5.k2-media-candidate.v1' or candidate.get('mediaKind')!='IMAGE'
            or candidate.get('provenance')!='IMPORTED' or candidate.get('sourceAssetVersions')!=[]
            or candidate.get('revisionRef')!=receipt['inputArtifactReceiptRef']
            or candidate.get('slotRef')!=receipt['creativeShotVersionRef']
            or candidate.get('sourceRequestRef')!=receipt['visualExecutionRequirementRef']
            or candidate.get('sourceRequestDigest')!=receipt['visualExecutionRequirementDigest']
            or candidate.get('artifactRef')!=artifact['stagedArtifactRef']
            or candidate.get('artifactDigest')!=artifact['contentDigest'] or candidate.get('artifactByteSize')!=artifact['byteSize']
            or candidate.get('storageKey')!=artifact['storageKey'] or candidate.get('publicationAllowed') is not False
            or validation.get('schemaVersion')!='v5.k2-technical-validation.v1'
            or validation.get('candidateRef')!=candidate['candidateRef'] or validation.get('candidateVersion')!=candidate['candidateVersion']
            or validation.get('candidateDigest')!=candidate['payloadDigest'] or validation.get('artifactDigest')!=candidate['artifactDigest']
            or validation.get('validatorRef')!=VALIDATOR_REF or validation.get('result')!='PASS'
            or validation.get('lifecycleState')!='TECHNICALLY_VERIFIED' or validation.get('publicationAllowed') is not False
            or validation.get('checks')!=[{'check':name,'passed':True} for name in CHECKS]):
        raise MethodAwareInputAssetError()


def selection_subject(receipt,candidate,qc):
    return MediaSelectionSubject.create(workspace_ref=receipt['workspaceRef'],production_run_ref=receipt['productionRunRef'],
        revision_ref=candidate['revisionRef'],slot_ref=candidate['slotRef'],source_request_ref=candidate['sourceRequestRef'],
        source_request_digest=candidate['sourceRequestDigest'],candidate_ref=candidate['candidateRef'],
        candidate_version=candidate['candidateVersion'],candidate_digest=candidate['payloadDigest'],
        artifact_digest=candidate['artifactDigest'],visual_qc_ref=qc['visualQcRef'],visual_qc_version=qc['visualQcVersion'],
        visual_qc_digest=qc['payloadDigest'])


class MethodAwareInputAssetService:
    def __init__(self,method_planning,review,artifact_evidence=None):
        self.planning=method_planning;self.review=review;self.evidence=review.evidence
        self.artifact_evidence=artifact_evidence or RejectingMethodAwareInputArtifactEvidence()
        review.input_selection_validator=self.verify_standalone_selection

    @staticmethod
    def _command(command,fields):
        try:
            exact(command,fields)
            for k in fields-{'idempotencyKey','humanSelectionVersion'}:
                (hex_digest if k.endswith('Digest') else ref)(command[k])
            _idempotency_key(command['idempotencyKey'])
            if 'humanSelectionVersion' in fields:integer(command['humanSelectionVersion'],1_000_000)
        except (ValueError,TypeError) as exc:raise MethodAwareInputAssetError('invalid_request',400) from exc
        return dict(command)

    def _current(self,command):
        scope={k:command[k] for k in SCOPE_FIELDS}
        try:
            root=self.review.root_service.verify_run_current(scope['workspaceRef'],scope['productionRunRef'])
            if any(root[k]!=scope[k] for k in SCOPE_FIELDS):raise RecordNotFoundError('scope')
            plan=self.planning.execution_method_planning.require_current_plan(
                *[scope[k] for k in ('workspaceRef','projectRef','seriesRef','episodeRef','productionRunRef')],
                command['executionMethodPlanVersionRef'])
        except RecordNotFoundError as exc:raise MethodAwareInputAssetError('method_aware_input_scope_mismatch') from exc
        except EpisodeProductionError as exc:raise MethodAwareInputAssetError('method_aware_input_plan_stale') from exc
        if plan['payloadDigest']!=command['executionMethodPlanDigest']:raise MethodAwareInputAssetError('method_aware_input_plan_stale')
        requirements=[r for r in plan['visualExecutionRequirements'] if r['visualExecutionRequirementRef']==command['visualExecutionRequirementRef']]
        if len(requirements)!=1 or requirements[0]['payloadDigest']!=command['visualExecutionRequirementDigest']:
            raise MethodAwareInputAssetError('method_aware_input_requirement_stale')
        requirement=requirements[0]
        if (requirement['executionClass'],requirement['executionMethod'])!=('MICRO_MOTION','SINGLE_ANCHOR_I2V'):
            raise MethodAwareInputAssetError('method_aware_input_requirement_stale')
        return scope,plan,requirement

    def _artifact(self,command,requirement):
        lineage={k:command[k] if k in PLAN_FIELDS else requirement[k] for k in LINEAGE_FIELDS}
        try:
            return self.artifact_evidence.resolve(staged_artifact_ref=command['stagedArtifactRef'],
                staged_artifact_digest=command['stagedArtifactDigest'],scope={k:command[k] for k in SCOPE_FIELDS},lineage=lineage)
        except MethodAwareInputArtifactError as exc:raise MethodAwareInputAssetError(exc.code) from exc

    def _record(self,kind,record_ref,key,payload,request_digest=None):
        value=sealed(payload)
        return EvidenceRecord(workspaceRef=value['workspaceRef'],productionRunRef=value['productionRunRef'],
            recordKind=kind,recordRef=record_ref,recordVersion=1,idempotencyKey=key,
            requestDigest=request_digest or value['payloadDigest'],createdAt=value['createdAt'],payload=value,payloadDigest=value['payloadDigest'])

    def _key(self,command,kind):
        request_digest=_digest({k:v for k,v in command.items() if k!='idempotencyKey'})
        keyed=self.evidence.get_record_by_idempotency_key(command['workspaceRef'],command['productionRunRef'],command['idempotencyKey'])
        if keyed is not None and (keyed['recordKind']!=kind or keyed['requestDigest']!=request_digest):
            code='method_aware_input_candidate_conflict' if kind==RECEIPT_KIND else 'method_aware_input_admission_conflict'
            raise MethodAwareInputAssetError(code)
        return request_digest

    def _intake_response(self,receipt_record,replay):
        receipt=validate_receipt(record_payload(receipt_record,RECEIPT_KIND));records=self.evidence.list_records(receipt['workspaceRef'],receipt['productionRunRef'])
        candidates=[record_payload(r,CANDIDATE) for r in records if r['recordKind']==CANDIDATE and r['payload'].get('revisionRef')==receipt['inputArtifactReceiptRef']]
        validations=[record_payload(r,TECHNICAL_VALIDATION) for r in records if r['recordKind']==TECHNICAL_VALIDATION
            and len(candidates)==1 and r['payload'].get('candidateRef')==candidates[0]['candidateRef']]
        if len(candidates)!=1 or len(validations)!=1:raise MethodAwareInputAssetError('method_aware_input_candidate_conflict')
        validate_candidate_chain(receipt,candidates[0],validations[0])
        return {'inputArtifactReceipt':receipt,'candidate':candidates[0],'technicalValidation':validations[0],
            'idempotentReplay':replay,'publicationAllowed':False}

    def ingest(self,command):
        command=self._command(command,INTAKE_FIELDS)
        if isinstance(self.artifact_evidence,RejectingMethodAwareInputArtifactEvidence):
            raise MethodAwareInputAssetError('method_aware_input_artifact_unavailable')
        scope,plan,requirement=self._current(command)
        head=self.evidence.record_journal_head(scope['workspaceRef'],scope['productionRunRef'])
        request_digest=self._key(command,RECEIPT_KIND);artifact=self._artifact(command,requirement)
        identity=_digest({**scope,**{k:command[k] for k in PLAN_FIELDS},'stagedArtifactRef':command['stagedArtifactRef'],'stagedArtifactDigest':command['stagedArtifactDigest']})[:40]
        receipt_ref='input-artifact-'+identity
        existing=self.evidence.get_record(scope['workspaceRef'],scope['productionRunRef'],receipt_ref,1)
        if existing is not None:
            response=self._intake_response(existing,True)
            if response['inputArtifactReceipt']['artifact']!=artifact:raise MethodAwareInputAssetError('method_aware_input_candidate_conflict')
            return response
        created=self.planning._clock()
        receipt=self._record(RECEIPT_KIND,receipt_ref,command['idempotencyKey'],{'schemaVersion':RECEIPT_SCHEMA,
            **scope,**{k:command[k] if k in PLAN_FIELDS else requirement[k] for k in LINEAGE_FIELDS},
            'inputArtifactReceiptRef':receipt_ref,'version':1,'inputRole':INPUT_ROLE,
            'inputRequirementKey':'action-ready-anchor:'+requirement['visualExecutionRequirementRef'],
            'stagedArtifactRef':command['stagedArtifactRef'],'stagedArtifactDigest':command['stagedArtifactDigest'],
            'artifact':artifact,'authorityState':'TECHNICAL_EVIDENCE_ONLY','providerProcessingAuthorized':False,
            'publicationAllowed':False,'createdAt':created},request_digest)
        validate_receipt(receipt.payload)
        candidate=self.review.prepare_candidate_record({**scope,'candidateRef':'input-candidate-'+identity,
            'idempotencyKey':command['idempotencyKey']+':candidate','revisionRef':receipt_ref,'mediaKind':'IMAGE',
            'slotRef':requirement['creativeShotVersionRef'],'sourceRequestRef':requirement['visualExecutionRequirementRef'],
            'sourceRequestDigest':requirement['payloadDigest'],'artifactRef':artifact['stagedArtifactRef'],
            'artifactDigest':artifact['contentDigest'],'artifactByteSize':artifact['byteSize'],'storageKey':artifact['storageKey'],
            'provenance':'IMPORTED','sourceAssetVersions':[]})
        validation=self.review.prepare_technical_validation_record({**scope,'idempotencyKey':command['idempotencyKey']+':validation',
            'candidateRef':candidate.recordRef,'candidateVersion':1,'candidateDigest':candidate.payloadDigest,
            'technicalValidationRef':'input-validation-'+identity,'validatorRef':VALIDATOR_REF,'result':'PASS',
            'checks':[{'check':name,'passed':True} for name in CHECKS]},candidate_record=candidate)
        validate_candidate_chain(receipt.payload,candidate.payload,validation.payload)
        self._current(command)
        try:
            stored,replay=self.evidence.append_records((receipt,candidate,validation),expected_record_journal_head=head)
        except (StaleInputError,IdempotencyConflictError):
            existing=self.evidence.get_record(scope['workspaceRef'],scope['productionRunRef'],receipt_ref,1)
            if existing is None:raise
            self._key(command,RECEIPT_KIND)
            return self._intake_response(existing,True)
        return self._intake_response(stored[0],replay)

    def _selection_chain(self,selection,workspace,run_ref):
        records=self.evidence.list_records(workspace,run_ref)
        candidate=exact_record(records,CANDIDATE,selection['candidateRef'],selection['candidateDigest'],selection['candidateVersion'])
        receipt=validate_receipt(exact_record(records,RECEIPT_KIND,candidate['revisionRef']))
        qc=exact_record(records,SEMANTIC_VISUAL_QC,selection['visualQcRef'],selection['visualQcDigest'],selection['visualQcVersion'])
        validation=exact_record(records,TECHNICAL_VALIDATION,qc['technicalValidationRef'],qc['technicalValidationDigest'],qc['technicalValidationVersion'])
        validate_candidate_chain(receipt,candidate,validation)
        command={**{k:receipt[k] for k in SCOPE_FIELDS|PLAN_FIELDS},'stagedArtifactRef':receipt['stagedArtifactRef'],'stagedArtifactDigest':receipt['stagedArtifactDigest']}
        _,_,requirement=self._current(command)
        if self._artifact(command,requirement)!=receipt['artifact']:raise MethodAwareInputAssetError()
        current_qc=self.review._applicable_visual_qc(workspace,run_ref,candidate['candidateRef'])
        if (selection['decision']!='SELECTED' or qc['result']!='PASS' or selection['publicationAllowed'] is not False
                or qc['publicationAllowed'] is not False or current_qc is None or current_qc[0]['payloadDigest']!=qc['payloadDigest']
                or self.review._current_candidate_record(workspace,run_ref,candidate['candidateRef']) is None):
            raise MethodAwareInputAssetError('method_aware_input_selection_required')
        # Only the accepted digest-pinned external implementation can authorize this new path.
        from .external_media_selection_approval import DigestPinnedMediaSelectionApprovalAuthority
        if not isinstance(self.review.selection_authority,DigestPinnedMediaSelectionApprovalAuthority):
            raise MediaSelectionApprovalRequiredError('an external media selection authority is required')
        subject=selection_subject(receipt,candidate,qc)
        authority=self.review.selection_authority.verify(subject=subject,approval_ref=selection['approvalRef'],decision='SELECTED')
        if (not isinstance(authority,VerifiedMediaSelection) or not authority.matches(subject=subject,approval_ref=selection['approvalRef'],decision='SELECTED')
                or selection['subjectDigest']!=subject.subject_digest
                or any(selection[k]!=getattr(authority,a) for k,a in {'actorRef':'actor_ref','actorKind':'actor_kind',
                    'authorityRef':'authority_ref','authorityDecisionRef':'authority_decision_ref','authorityDecisionDigest':'authority_decision_digest',
                    'authorityDecidedAt':'decided_at'}.items())):raise MediaSelectionApprovalRequiredError('media selection authority changed')
        return receipt,candidate,validation,qc

    def verify_standalone_selection(self,item):
        candidate=self.evidence.get_record(item.workspaceRef,item.productionRunRef,item.payload['candidateRef'],item.payload['candidateVersion'])
        if candidate is None:return False
        receipt=self.evidence.get_record(item.workspaceRef,item.productionRunRef,candidate['payload']['revisionRef'],1)
        if receipt is None or receipt['recordKind']!=RECEIPT_KIND:return False
        self._selection_chain(dict(item.payload),item.workspaceRef,item.productionRunRef)
        return True

    def _admission_response(self,record,replay):
        admission=checked(record_payload(record,ASSET_ADMISSION),ADMISSION_FIELDS)
        workspace,run_ref=record['workspaceRef'],record['productionRunRef']
        records=self.evidence.list_records(workspace,run_ref)
        asset=exact_record(records,ASSET_VERSION,admission['assetVersionRef'],admission['assetVersionDigest'])
        root=self.review.root_service.verify_run_current(workspace,run_ref)
        asset=validate_asset_version(asset,records=records,workspace_ref=workspace,run_ref=run_ref,root=root)
        return {'assetAdmission':admission,'assetVersion':asset,'idempotentReplay':replay,'publicationAllowed':False}

    def admit(self,command):
        command=self._command(command,ADMIT_FIELDS)
        if isinstance(self.artifact_evidence,RejectingMethodAwareInputArtifactEvidence):
            raise MethodAwareInputAssetError('method_aware_input_artifact_unavailable')
        scope,plan,requirement=self._current(command)
        workspace,run_ref=scope['workspaceRef'],scope['productionRunRef']
        head=self.evidence.record_journal_head(workspace,run_ref);request_digest=self._key(command,ASSET_ADMISSION)
        records=self.evidence.list_records(workspace,run_ref)
        selection=exact_record(records,HUMAN_SELECTION,command['humanSelectionRef'],command['humanSelectionDigest'],command['humanSelectionVersion'])
        receipt,candidate,validation,qc=self._selection_chain(selection,workspace,run_ref)
        if any(command[k]!=receipt[k] for k in SCOPE_FIELDS|PLAN_FIELDS):raise MethodAwareInputAssetError('method_aware_input_requirement_stale')
        existing=[r for r in records if r['recordKind']==ASSET_ADMISSION and r['payload'].get('schemaVersion')==ADMISSION_SCHEMA
            and r['payload'].get('visualExecutionRequirementRef')==command['visualExecutionRequirementRef'] and r['payload'].get('inputRole')==INPUT_ROLE]
        if len(existing)>1:raise MethodAwareInputAssetError('method_aware_input_admission_conflict')
        if existing:
            payload=record_payload(existing[0],ASSET_ADMISSION)
            if payload['candidateRef']!=candidate['candidateRef']:raise MethodAwareInputAssetError('method_aware_input_asset_successor_not_implemented')
            if payload['humanSelectionDigest']!=selection['payloadDigest']:raise MethodAwareInputAssetError('method_aware_input_admission_conflict')
            return self._admission_response(existing[0],True)
        identity=_digest({**scope,'visualExecutionRequirementRef':command['visualExecutionRequirementRef'],'inputRole':INPUT_ROLE})[:40]
        admission_ref='input-admission-'+identity;asset_ref='input-image-'+identity;asset_version_ref='input-image-version-'+identity
        common={**scope,**{k:receipt[k] for k in LINEAGE_FIELDS},'inputRole':INPUT_ROLE,'inputRequirementKey':receipt['inputRequirementKey'],
            'sourceArtifactReceiptRef':receipt['inputArtifactReceiptRef'],'sourceArtifactReceiptDigest':receipt['payloadDigest'],
            'technicalValidationRef':validation['technicalValidationRef'],'technicalValidationDigest':validation['payloadDigest'],
            'semanticVisualQcRef':qc['visualQcRef'],'semanticVisualQcDigest':qc['payloadDigest'],
            'humanSelectionRef':selection['selectionRef'],'humanSelectionDigest':selection['payloadDigest'],
            'assetAdmissionRef':admission_ref,'publicationAllowed':False,'createdAt':self.planning._clock()}
        artifact=receipt['artifact']
        asset=self._record(ASSET_VERSION,asset_version_ref,command['idempotencyKey']+':asset',{
            **common,'schemaVersion':ASSET_SCHEMA,'assetRef':asset_ref,'assetVersionRef':asset_version_ref,'version':1,
            'sourceCandidateRef':candidate['candidateRef'],'sourceCandidateDigest':candidate['payloadDigest'],
            'mediaKind':'image','mediaType':artifact['mediaType'],'artifactRef':artifact['stagedArtifactRef'],
            'storageKey':artifact['storageKey'],'byteSize':artifact['byteSize'],'sha256':artifact['contentDigest'],'probe':probe_for(artifact),
            'provenance':'IMPORTED','authorityState':'TECHNICAL_EVIDENCE_ONLY','providerProcessingAuthorized':False,
            'state':'REGISTERED','immutable':True})
        admission=self._record(ASSET_ADMISSION,admission_ref,command['idempotencyKey'],{
            **common,'schemaVersion':ADMISSION_SCHEMA,'assetVersionRef':asset_version_ref,'assetVersionDigest':asset.payloadDigest,
            'candidateRef':candidate['candidateRef'],'candidateDigest':candidate['payloadDigest'],'admissionState':'ADMITTED'},request_digest)
        validate_asset_version(asset.payload,records=[*records,asdict(admission),asdict(asset)],
            workspace_ref=workspace,run_ref=run_ref,
            root=self.review.root_service.verify_run_current(workspace,run_ref))
        self._current(command)
        try:
            stored,replay=self.evidence.append_records((admission,asset),expected_record_journal_head=head)
        except (StaleInputError,IdempotencyConflictError):
            existing=self.evidence.get_record(workspace,run_ref,admission_ref,1)
            if existing is None:raise
            self._key(command,ASSET_ADMISSION)
            if existing['payload'].get('humanSelectionDigest')!=selection['payloadDigest']:
                raise MethodAwareInputAssetError('method_aware_input_admission_conflict')
            return self._admission_response(existing,True)
        return self._admission_response(stored[0],replay)
