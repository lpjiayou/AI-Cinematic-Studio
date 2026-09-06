"""Current input-image admission; isolated synthetic bytes, never live lineage."""
from copy import deepcopy
from hashlib import sha256
import importlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from apps.creator_workspace_mvp import public_contract
from services.v5_core_os.episode_production import public
from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.media_candidate_review import CanonicalAssetVersionAuthority
from tests.unit.test_execution_method_planning_m8_m9 import seeded_plan, plan_command
from tests.unit.test_method_aware_media_m10_m11 import method_service, m10_command
from services.v4_platform import method_aware_input_artifacts as artifacts
from services.v5_core_os.episode_production import method_aware_input_assets as assets
from services.v5_core_os.episode_production.external_media_selection_approval import (
    MEDIA_SELECTION_APPROVAL_AUTHORITY_BUNDLE_SCHEMA, media_selection_approval_authority_from_environment)
from services.v5_core_os.episode_production.media_candidate_review import VerifiedMediaSelection
from tests.unit import test_k2_media_candidate_review as review_tests


def png_bytes(width=8, height=12, color=40):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind+data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress((b'\0'+bytes([color, 90, 120])*width)*height)) + chunk(b'IEND', b''))


class InputImageFixture:
    def __init__(self, case, *, sqlite=False):
        self.temp = tempfile.TemporaryDirectory(); case.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sqlite = sqlite
        self.seed, validation = seeded_plan()
        if sqlite:
            from tests.unit.test_episode_production_k2 import run_command
            from tests.unit.test_narrative_currentness_m7 import validation_command
            self.seed['boundary'] = self.make_boundary()
            self.seed['run'] = self.seed['boundary'].create_run(run_command(
                self.seed['project'],self.seed['series'],self.seed['episode']))
            validation = self.seed['boundary'].create_narrative_validation(validation_command(self.seed))
        self.boundary = self.seed['boundary']
        self.plan = self.boundary.create_execution_method_plan(plan_command(self.seed, validation))
        self.requirement = next(r for r in self.plan['visualExecutionRequirements'] if r['executionClass']=='MICRO_MOTION')
        self.scope = {k:self.plan[k] for k in ('workspaceRef','projectRef','seriesRef','episodeRef','productionRunRef')}
        self.evidence = method_service(self.boundary).evidence_repository
        self.review = method_service(self.boundary).candidate_review
        self.source_root = self.root/'sources'; self.source_root.mkdir()
        self.content = png_bytes(); self.content_digest = sha256(self.content).hexdigest()
        self.source = self.source_root/(self.content_digest+'.png'); self.source.write_bytes(self.content)

    def make_boundary(self, *, restart=False):
        from tests.unit.test_narrative_currentness_m7 import validation_profiles
        assembly=self.seed['assembly']
        return public.create_local_development_boundary(self.root/'runs.sqlite3',
            project_boundary=assembly.project_context,series_episode_boundary=assembly.series_episode,
            series_planning_boundary=assembly.series_planning,script_studio_boundary=assembly.script_studio,
            narrative_validation_profiles=validation_profiles(),initialize_if_missing=not restart,
            method_aware_input_artifact_evidence=getattr(self,'port',None),
            media_selection_approval_authority=getattr(self,'selection_authority',None))

    def restart(self):
        self.port=artifacts.input_artifact_evidence_from_environment(self.environment)
        if hasattr(self,'selection_environment'):
            self.selection_authority=media_selection_approval_authority_from_environment(self.selection_environment)
        self.boundary=self.make_boundary(restart=True);self.seed['boundary']=self.boundary
        self.evidence=method_service(self.boundary).evidence_repository
        self.review=method_service(self.boundary).candidate_review

    def configure(self, **changes):
        entry={'schemaVersion':artifacts.ENTRY_SCHEMA,**self.scope,
            'executionMethodPlanVersionRef':self.plan['executionMethodPlanVersionRef'],
            'executionMethodPlanDigest':self.plan['payloadDigest'],
            **{k:self.requirement[k] for k in ('visualExecutionRequirementRef','creativeShotVersionRef','creativeShotVersionDigest')},
            'visualExecutionRequirementDigest':self.requirement['payloadDigest'],
            'stagedArtifactRef':'staged-image-e3a','inputRole':'ACTION_READY_ANCHOR',
            'storageKey':self.source.name,'mediaType':'image/png','byteSize':len(self.content),
            'contentDigest':self.content_digest,'usageScope':'TECHNICAL_EVIDENCE_ONLY',
            'providerProcessingAuthorized':False,'publicationAllowed':False,
            'evidenceRef':'synthetic-fixture-evidence','evidenceDigest':'3'*64,**changes}
        self.entry=artifacts.seal(entry);self.entry_digest=self.entry['payloadDigest']
        self.bundle={'schemaVersion':artifacts.BUNDLE_SCHEMA,'authorityRef':'synthetic-operator-authority','artifacts':[self.entry]}
        self.bundle_path=self.root/'bundle.json'
        data=artifacts.canonical(self.bundle);self.bundle_path.write_bytes(data)
        self.environment=dict(zip(artifacts.CONFIG_NAMES,(str(self.bundle_path),sha256(data).hexdigest(),str(self.source_root))))
        self.port=artifacts.input_artifact_evidence_from_environment(self.environment)
        self.boundary._EpisodeProductionPublicBoundary__method_aware_input_assets.artifact_evidence=self.port
        return self.port

    def qc_command(self, intake, **kwargs):
        command=review_tests.InMemoryCandidateReviewTests().qc_command(intake['technicalValidation'],**kwargs)
        return {**command,'workspaceRef':self.scope['workspaceRef'],'productionRunRef':self.scope['productionRunRef']}

    def selection_command(self, qc, **kwargs):
        return {**review_tests.InMemoryCandidateReviewTests.selection_command(qc,**kwargs),
            'workspaceRef':self.scope['workspaceRef'],'productionRunRef':self.scope['productionRunRef']}

    def approve(self,intake,qc,command=None):
        command=command or self.selection_command(qc)
        subject=assets.selection_subject(intake['inputArtifactReceipt'],intake['candidate'],qc)
        authority_ref='synthetic-external-selection-authority';actor='external-human-fixture'
        decision_ref='external-decision-'+qc['visualQcRef'];decided='2026-09-06T10:00:00Z'
        decision_digest=VerifiedMediaSelection.expected_decision_digest(authority_ref=authority_ref,
            approval_ref=command['approvalRef'],actor_ref=actor,actor_kind='HUMAN',decision='SELECTED',
            authority_decision_ref=decision_ref,decided_at=decided,subject_digest=subject.subject_digest)
        bundle={'schemaVersion':MEDIA_SELECTION_APPROVAL_AUTHORITY_BUNDLE_SCHEMA,'authorityRef':authority_ref,
            'approvals':[{'subject':subject.as_dict(),'approvalRef':command['approvalRef'],'actorRef':actor,
                'actorKind':'HUMAN','decision':'SELECTED','authorityDecisionRef':decision_ref,
                'authorityDecisionDigest':decision_digest,'decidedAt':decided}]}
        data=artifacts.canonical(bundle);path=self.root/'selection.json';path.write_bytes(data)
        self.selection_environment={'CREATOR_MEDIA_SELECTION_AUTHORITY_BUNDLE_PATH':str(path),
            'CREATOR_MEDIA_SELECTION_AUTHORITY_BUNDLE_SHA256':sha256(data).hexdigest()}
        self.selection_authority=media_selection_approval_authority_from_environment(self.selection_environment)
        self.review.selection_authority=self.selection_authority
        return command

    def admission_command(self,selection,key='e3a-admission'):
        return {**{k:v for k,v in self.command(key).items() if k not in {'stagedArtifactRef','stagedArtifactDigest'}},
            'humanSelectionRef':selection['selectionRef'],'humanSelectionVersion':selection['selectionVersion'],
            'humanSelectionDigest':selection['payloadDigest']}

    def selected(self):
        self.configure()
        intake=self.boundary.ingest_public_method_aware_input_candidate(self.command())
        qc=self.boundary.record_semantic_visual_qc(self.qc_command(intake))['semanticVisualQc']
        selection=self.boundary.record_human_selection(self.approve(intake,qc))['humanSelection']
        return intake,qc,selection

    def binding(self,asset):
        return {'visualExecutionRequirementRef':self.requirement['visualExecutionRequirementRef'],
            'inputRequirementKey':'action-ready-anchor:'+self.requirement['visualExecutionRequirementRef'],
            'inputRole':'ACTION_READY_ANCHOR','assetVersionRef':asset['assetVersionRef'],
            'assetVersionDigest':asset['payloadDigest']}

    def command(self, key='e3a-intake'):
        return {**self.scope, 'executionMethodPlanVersionRef':self.plan['executionMethodPlanVersionRef'],
            'executionMethodPlanDigest':self.plan['payloadDigest'],
            'visualExecutionRequirementRef':self.requirement['visualExecutionRequirementRef'],
            'visualExecutionRequirementDigest':self.requirement['payloadDigest'],
            'stagedArtifactRef':'staged-image-e3a', 'stagedArtifactDigest':getattr(self,'entry_digest','1'*64),
            'idempotencyKey':key}

    def records(self):
        return self.evidence.list_records(self.scope['workspaceRef'],self.scope['productionRunRef'])


class SingleInputPathBaselineTests(unittest.TestCase):
    def setUp(self): self.f=InputImageFixture(self)

    def test_current_candidate_intake_port_exists(self):
        self.assertTrue(callable(getattr(self.f.boundary,'ingest_public_method_aware_input_candidate',None)))

    def test_current_single_selection_admission_port_exists(self):
        self.assertTrue(callable(getattr(self.f.boundary,'admit_public_method_aware_input_image',None)))

    def test_two_current_public_resources_are_registered(self):
        self.assertIn('method-aware-input-candidates',public_contract.PUBLIC_METHOD_AWARE_RESOURCES)
        self.assertIn('method-aware-input-admission',public_contract.PUBLIC_METHOD_AWARE_RESOURCES)

    def test_legacy_candidate_and_admission_reject_current_plan_without_writes(self):
        before=self.f.records()
        command={k:self.f.scope[k] for k in ('workspaceRef','productionRunRef')}
        for method,extra in ((self.f.boundary.record_real_image_candidates,{}),
                             (self.f.boundary.admit_real_images,{'selections':[]})):
            with self.subTest(method=method.__name__),self.assertRaises(public.EpisodeProductionPublicError):
                method({**command,**extra,'idempotencyKey':'legacy-must-reject'})
        self.assertEqual(self.f.records(),before)

    def test_legacy_four_selection_and_font_kind_remain_closed(self):
        from services.v5_core_os.episode_production.real_media_revision import K2RealMediaRevisionService
        from services.v5_core_os.episode_production.foundation import EpisodeProductionError
        from services.v5_core_os.episode_production.static_resources import CanonicalStaticResourceService,StaticResourceError,DirectoryStaticResourceStorage
        from tests.contract.test_v5_static_font_assets_contract import RootStub,candidate_command
        from services.v5_core_os.episode_production.evidence import InMemoryEpisodeProductionEvidenceAdapter
        with self.assertRaises(EpisodeProductionError):K2RealMediaRevisionService._selection_items([{}])
        service=CanonicalStaticResourceService(RootStub(),InMemoryEpisodeProductionEvidenceAdapter(),
            storage=DirectoryStaticResourceStorage(self.f.source_root,{'font-fixture':self.f.source.name}),
            clock=lambda:'2026-09-06T10:00:00Z',ref_factory=lambda prefix:prefix+'-test')
        with self.assertRaises(StaticResourceError):service.create_candidate(candidate_command(resourceKind='IMAGE'))

    def test_generic_candidate_preparation_is_trusted_not_a_public_artifact_authority(self):
        f=self.f; before=f.records()
        prepared=f.review.prepare_candidate_record({**{k:f.scope[k] for k in ('workspaceRef','productionRunRef')},
            'idempotencyKey':'trusted-low-level-only','candidateRef':'caller-chosen-candidate',
            'revisionRef':'caller-chosen-revision','mediaKind':'IMAGE','slotRef':f.requirement['creativeShotVersionRef'],
            'sourceRequestRef':'caller-request','sourceRequestDigest':'1'*64,'artifactRef':'caller-artifact',
            'artifactDigest':'2'*64,'artifactByteSize':1,'provenance':'IMPORTED','sourceAssetVersions':[]})
        self.assertEqual(prepared.payload['artifactRef'],'caller-artifact')
        self.assertFalse(hasattr(f.boundary,'register_candidate'))
        self.assertEqual(f.records(),before)

    def test_input_plan_rejects_unadmitted_image_and_asset_authority_is_read_only(self):
        f=self.f; before=f.records()
        binding={'visualExecutionRequirementRef':f.requirement['visualExecutionRequirementRef'],
            'inputRequirementKey':'action-ready-anchor:'+f.requirement['visualExecutionRequirementRef'],
            'inputRole':'ACTION_READY_ANCHOR','assetVersionRef':'unadmitted-image','assetVersionDigest':'1'*64}
        with self.assertRaises(public.EpisodeProductionPublicError):
            f.boundary.create_method_aware_input_plan(m10_command(f.seed,f.plan,[binding]))
        self.assertFalse(hasattr(CanonicalAssetVersionAuthority,'create_asset'))
        self.assertEqual(f.records(),before)


class ArtifactAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.f=InputImageFixture(self);self.f.configure()

    def resolve(self,**changes):
        f=self.f
        args={'staged_artifact_ref':f.entry['stagedArtifactRef'],'staged_artifact_digest':f.entry_digest,
              'scope':f.scope,'lineage':{k:f.entry[k] for k in artifacts.LINEAGE_FIELDS}}
        return f.port.resolve(**{**args,**changes})

    def load(self,bundle):
        f=self.f;data=artifacts.canonical(bundle);f.bundle_path.write_bytes(data)
        return artifacts.DigestPinnedMethodAwareInputArtifactEvidence(f.bundle_path,sha256(data).hexdigest(),f.source_root)

    def test_absent_partial_and_complete_configuration(self):
        self.assertIsInstance(artifacts.input_artifact_evidence_from_environment({}),artifacts.RejectingMethodAwareInputArtifactEvidence)
        for name in artifacts.CONFIG_NAMES:
            with self.subTest(name=name),self.assertRaises(artifacts.MethodAwareInputArtifactError):
                artifacts.input_artifact_evidence_from_environment({name:self.f.environment[name]})
        value=self.resolve()
        self.assertEqual(set(value),artifacts.PROJECTION_FIELDS)
        self.assertEqual((value['width'],value['height'],value['format']),(8,12,'png'))
        self.assertNotIn(str(self.f.root),json.dumps(value))

    def test_strict_json_pins_unknown_fields_and_duplicates(self):
        original=artifacts.canonical(self.f.bundle)
        for raw in (original+b' ', b'{"schemaVersion":1,"schemaVersion":2}', b'{"bad":NaN}',b'{"bad":Infinity}',b'{"bad":1e999}',b'['*80+b'0'+b']'*80):
            with self.subTest(raw=raw[:35]),self.assertRaises(artifacts.MethodAwareInputArtifactError):
                self.f.bundle_path.write_bytes(raw)
                pin=self.f.environment[artifacts.CONFIG_NAMES[1]] if raw==original+b' ' else sha256(raw).hexdigest()
                artifacts.DigestPinnedMethodAwareInputArtifactEvidence(self.f.bundle_path,pin,self.f.source_root)
        for mutate in (lambda b:b.update(extra=True),lambda b:b['artifacts'][0].update(extra=True),
                       lambda b:b['artifacts'].append(deepcopy(b['artifacts'][0])),
                       lambda b:b['artifacts'].append(artifacts.seal({**{k:v for k,v in b['artifacts'][0].items() if k!='payloadDigest'},'stagedArtifactRef':'duplicate-scope'}))):
            b=deepcopy(self.f.bundle);mutate(b)
            with self.assertRaises(artifacts.MethodAwareInputArtifactError):self.load(b)

    def test_closed_entry_types_roles_rights_and_payload_digest(self):
        for field,value in [('inputRole','STATIC_PLATE'),('providerProcessingAuthorized',True),('publicationAllowed',True),
                            ('usageScope','PRODUCTION'),('byteSize',True),('byteSize',1.5),('byteSize',0),
                            ('byteSize',artifacts.MAX_IMAGE_BYTES+1),('contentDigest','bad'),('mediaType','video/mp4'),
                            ('storageKey','../escape.png'),('storageKey','/tmp/escape.png'),('storageKey','a//b.png'),
                            ('storageKey','a\\b.png')]:
            b=deepcopy(self.f.bundle);entry={k:v for k,v in b['artifacts'][0].items() if k!='payloadDigest'}
            entry[field]=value;b['artifacts']=[artifacts.seal(entry)]
            with self.subTest(field=field,value=value),self.assertRaises(artifacts.MethodAwareInputArtifactError):self.load(b)
        b=deepcopy(self.f.bundle);b['artifacts'][0]['evidenceRef']='unsealed-change'
        with self.assertRaises(artifacts.MethodAwareInputArtifactError):self.load(b)

    def test_foreign_scopes_unknown_ref_and_wrong_lineage(self):
        for field in self.f.scope:
            with self.subTest(field=field),self.assertRaises(artifacts.MethodAwareInputArtifactError) as caught:
                self.resolve(scope={**self.f.scope,field:'foreign'})
            self.assertEqual(caught.exception.code,'method_aware_input_artifact_not_found')
        with self.assertRaises(artifacts.MethodAwareInputArtifactError):self.resolve(staged_artifact_ref='unknown')
        for field in artifacts.LINEAGE_FIELDS:
            with self.subTest(field=field),self.assertRaises(artifacts.MethodAwareInputArtifactError):
                self.resolve(lineage={**{k:self.f.entry[k] for k in artifacts.LINEAGE_FIELDS},field:'f'*64})
        with self.assertRaises(artifacts.MethodAwareInputArtifactError):self.resolve(staged_artifact_digest='a'*64)

    def test_symlink_bundle_source_parent_and_outside_root_rejected(self):
        f=self.f;target=f.root/'outside.png';target.write_bytes(f.content)
        f.source.unlink();f.source.symlink_to(target)
        with self.assertRaises(artifacts.MethodAwareInputArtifactError):self.resolve()
        f.source.unlink();f.source.write_bytes(f.content)
        link=f.source_root/'linked';link.symlink_to(f.source_root,target_is_directory=True)
        f.configure(storageKey='linked/'+f.source.name)
        with self.assertRaises(artifacts.MethodAwareInputArtifactError):self.resolve()
        saved=f.root/'bundle-original';saved.write_bytes(f.bundle_path.read_bytes());f.bundle_path.unlink();f.bundle_path.symlink_to(saved)
        with self.assertRaises(artifacts.MethodAwareInputArtifactError):self.resolve()

    def test_changed_size_digest_type_and_bundle_fail_on_every_read(self):
        f=self.f
        for data in (f.content+b'x',png_bytes(color=41)):
            f.source.write_bytes(data)
            with self.assertRaises(artifacts.MethodAwareInputArtifactError):self.resolve()
        f.source.write_bytes(f.content);f.configure(mediaType='image/jpeg')
        with self.assertRaises(artifacts.MethodAwareInputArtifactError):self.resolve()
        f.configure();f.bundle_path.write_bytes(f.bundle_path.read_bytes()+b' ')
        with self.assertRaises(artifacts.MethodAwareInputArtifactError):self.resolve()

    def test_animation_concatenation_and_probe_shape_rejected(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        animated=bytearray(self.f.content)
        payload=struct.pack('>II',2,0);kind=b'acTL';chunk=struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload))
        animated=bytes(animated[:33])+chunk+bytes(animated[33:])
        for data in (animated,self.f.content+self.f.content):
            with self.assertRaises(artifacts.MethodAwareInputArtifactError):artifacts.probe_image(data,'image/png')
        base={'codec_type':'video','codec_name':'png','width':8,'height':12,'nb_read_frames':'1'}
        for streams in ([],[base,base],[{**base,'nb_read_frames':'2'}],[{**base,'width':True}],
                        [{**base,'height':1.5}],[{**base,'width':0}],[{**base,'codec_name':'mjpeg'}]):
            with patch.object(artifacts.subprocess,'run',return_value=SimpleNamespace(stdout=artifacts.canonical({'streams':streams}))),self.assertRaises(artifacts.MethodAwareInputArtifactError):
                artifacts.probe_image(self.f.content,'image/png')

    def test_jpeg_is_verified_as_one_image(self):
        import subprocess
        encoded=subprocess.run(['ffmpeg','-v','error','-f','image2pipe','-i','pipe:0','-frames:v','1',
            '-c:v','mjpeg','-f','image2pipe','pipe:1'],input=self.f.content,capture_output=True,check=True).stdout
        self.assertEqual(artifacts.probe_image(encoded,'image/jpeg'),{'width':8,'height':12,'format':'jpeg'})
        with self.assertRaises(artifacts.MethodAwareInputArtifactError):artifacts.probe_image(encoded+encoded,'image/jpeg')

    def test_file_and_manifest_mutation_during_probe_are_detected(self):
        from unittest.mock import patch
        original=artifacts.probe_image
        for target in ('source','manifest'):
            self.f.configure();self.f.source.write_bytes(self.f.content)
            def change(data,media_type):
                result=original(data,media_type)
                if target=='source':self.f.source.write_bytes(png_bytes(color=42))
                else:self.f.bundle_path.write_bytes(self.f.bundle_path.read_bytes()+b' ')
                return result
            with patch.object(artifacts,'probe_image',side_effect=change),self.assertRaises(artifacts.MethodAwareInputArtifactError):self.resolve()

    def test_operator_tool_copies_no_replace_and_never_writes_core_records(self):
        from scripts.method_aware_input_artifact_bundle import build_bundle
        f=self.f;before=f.records();dest=f.root/'operator-sources'
        fields={k:f.entry[k] for k in artifacts.SCOPE_FIELDS|artifacts.LINEAGE_FIELDS|{'stagedArtifactRef','evidenceRef','evidenceDigest'}}
        kwargs=dict(image_path=f.source,source_root=dest,authority_ref='operator-fixture',media_type='image/png',fields=fields)
        one=build_bundle(**kwargs,bundle_path=f.root/'operator-one.json')
        two=build_bundle(**kwargs,bundle_path=f.root/'operator-two.json');self.assertEqual(one,two)
        port=artifacts.DigestPinnedMethodAwareInputArtifactEvidence(f.root/'operator-one.json',one['bundleSha256'],dest)
        self.assertEqual(port.resolve(staged_artifact_ref=one['stagedArtifactRef'],staged_artifact_digest=one['stagedArtifactDigest'],
            scope=f.scope,lineage={k:f.entry[k] for k in artifacts.LINEAGE_FIELDS})['contentDigest'],f.content_digest)
        (dest/one['storageKey']).write_bytes(b'unchanged-corrupt-existing-file')
        with self.assertRaises(artifacts.MethodAwareInputArtifactError):build_bundle(**kwargs,bundle_path=f.root/'operator-three.json')
        self.assertEqual((dest/one['storageKey']).read_bytes(),b'unchanged-corrupt-existing-file');self.assertEqual(f.records(),before)


class CurrentInputLifecycleTests(unittest.TestCase):
    def setUp(self):self.f=InputImageFixture(self)

    def reject(self,method,command,code=None):
        before=self.f.records()
        with self.assertRaises(public.EpisodeProductionPublicError) as caught:method(command)
        if code:self.assertEqual(caught.exception.code,code)
        self.assertEqual(self.f.records(),before)

    def test_intake_three_records_exact_replay_and_no_implicit_rights(self):
        f=self.f;f.configure();before=len(f.records())
        one=f.boundary.ingest_public_method_aware_input_candidate(f.command());self.assertFalse(one['idempotentReplay'])
        added=f.records()[before:];self.assertEqual([r['recordKind'] for r in added],['MethodAwareInputArtifact','Candidate','TechnicalValidation'])
        self.assertEqual(one['candidate']['provenance'],'IMPORTED');self.assertTrue(one['candidate']['candidateRef'].startswith('input-candidate-'))
        self.assertEqual(one['technicalValidation']['result'],'PASS')
        for key in ('e3a-intake','new-intake-key'):
            replay=f.boundary.ingest_public_method_aware_input_candidate(f.command(key));self.assertTrue(replay['idempotentReplay'])
            for field in ('candidate','technicalValidation','inputArtifactReceipt'):self.assertEqual(one[field],replay[field])
        self.assertEqual(len(f.records())-before,3)
        self.assertFalse(any(r['recordKind'] in {'HumanSelectionDecision','AssetVersion','AssetAdmission'} for r in added))
        self.reject(f.boundary.ingest_public_method_aware_input_candidate,{**f.command(),'stagedArtifactRef':'other'},'method_aware_input_candidate_conflict')

    def test_absent_authority_both_commands_are_unavailable(self):
        f=self.f
        self.reject(f.boundary.ingest_public_method_aware_input_candidate,f.command(),'method_aware_input_artifact_unavailable')
        command={**{k:v for k,v in f.command().items() if k not in {'stagedArtifactRef','stagedArtifactDigest'}},
            'humanSelectionRef':'missing','humanSelectionVersion':1,'humanSelectionDigest':'a'*64}
        self.reject(f.boundary.admit_public_method_aware_input_image,command,'method_aware_input_artifact_unavailable')

    def test_scope_plan_requirement_shot_and_execution_class_rejection(self):
        f=self.f;f.configure();method=f.boundary.ingest_public_method_aware_input_candidate
        for field in f.scope:self.reject(method,{**f.command(),field:'foreign'},'method_aware_input_scope_mismatch')
        self.reject(method,{**f.command(),'executionMethodPlanDigest':'a'*64},'method_aware_input_plan_stale')
        self.reject(method,{**f.command(),'visualExecutionRequirementDigest':'a'*64},'method_aware_input_requirement_stale')
        for req in f.plan['visualExecutionRequirements']:
            if req['executionClass'] in {'CONTACT_ACTION','GAIT_LOCOMOTION'}:
                self.reject(method,{**f.command(),'visualExecutionRequirementRef':req['visualExecutionRequirementRef'],
                    'visualExecutionRequirementDigest':req['payloadDigest']},'method_aware_input_requirement_stale')
        f.configure(creativeShotVersionRef='wrong-shot')
        self.reject(method,f.command(),'method_aware_input_artifact_invalid')

    def test_closed_dto_rejects_browser_authority_and_fractional_versions(self):
        f=self.f;f.configure()
        for field in ('artifactRef','candidateRef','storageKey','width','inputRole','providerId','authorityRef','payloadDigest'):
            self.reject(f.boundary.ingest_public_method_aware_input_candidate,{**f.command(),field:'browser'},'invalid_request')
        _,_,selection=f.selected()
        for value in (True,1.5,'1',0):
            self.reject(f.boundary.admit_public_method_aware_input_image,{**f.admission_command(selection),'humanSelectionVersion':value},'invalid_request')

    def test_qc_fail_and_missing_external_selection_do_not_select(self):
        f=self.f;f.configure();intake=f.boundary.ingest_public_method_aware_input_candidate(f.command())
        qc=f.boundary.record_semantic_visual_qc(f.qc_command(intake,result='FAIL'))['semanticVisualQc']
        self.reject(f.boundary.record_human_selection,f.approve(intake,qc))
        self.assertFalse(any(r['recordKind']=='HumanSelectionDecision' for r in f.records()))

    def test_selection_requires_exact_external_subject_and_artifact_revalidation(self):
        from services.v5_core_os.episode_production.media_candidate_review import RejectingMediaSelectionApprovalAuthority
        f=self.f;f.configure();intake=f.boundary.ingest_public_method_aware_input_candidate(f.command())
        qc=f.boundary.record_semantic_visual_qc(f.qc_command(intake))['semanticVisualQc'];command=f.selection_command(qc)
        self.reject(f.boundary.record_human_selection,command,'media_selection_approval_required')
        f.approve(intake,qc)
        self.reject(f.boundary.record_human_selection,{**command,'approvalRef':'wrong-approval'},'media_selection_approval_required')
        f.source.write_bytes(png_bytes(color=41));self.reject(f.boundary.record_human_selection,command,'method_aware_input_artifact_invalid')
        f.source.write_bytes(f.content)
        selection=f.boundary.record_human_selection(command)['humanSelection']
        self.assertEqual(selection['actorRef'],'external-human-fixture')
        f.review.selection_authority=RejectingMediaSelectionApprovalAuthority()
        self.reject(f.boundary.admit_public_method_aware_input_image,f.admission_command(selection),'media_selection_approval_required')

    def test_admission_two_records_reuses_selection_and_grants_no_execution(self):
        f=self.f;_,_,selection=f.selected();before=len(f.records())
        result=f.boundary.admit_public_method_aware_input_image(f.admission_command(selection));asset=result['assetVersion']
        self.assertEqual([r['recordKind'] for r in f.records()[before:]],['AssetAdmission','AssetVersion'])
        self.assertEqual(asset['schemaVersion'],assets.ASSET_SCHEMA);self.assertEqual(asset['version'],1)
        self.assertFalse(asset['providerProcessingAuthorized']);self.assertFalse(asset['publicationAllowed'])
        for key in ('e3a-admission','another-exact-key'):
            replay=f.boundary.admit_public_method_aware_input_image(f.admission_command(selection,key))
            self.assertTrue(replay['idempotentReplay']);self.assertEqual(replay['assetVersion'],asset)
        self.assertEqual(len(f.records())-before,2)
        self.reject(f.boundary.admit_public_method_aware_input_image,{**f.admission_command(selection),'humanSelectionRef':'changed'},'method_aware_input_admission_conflict')

    def test_invalid_selection_stale_plan_and_bytes_prevent_admission(self):
        f=self.f;_,_,selection=f.selected();command=f.admission_command(selection)
        self.reject(f.boundary.admit_public_method_aware_input_image,{**command,'humanSelectionDigest':'f'*64},'method_aware_input_selection_required')
        self.reject(f.boundary.admit_public_method_aware_input_image,{**command,'executionMethodPlanDigest':'f'*64},'method_aware_input_plan_stale')
        self.reject(f.boundary.admit_public_method_aware_input_image,{**command,'workspaceRef':'foreign'},'method_aware_input_scope_mismatch')
        f.source.write_bytes(png_bytes(color=43));self.reject(f.boundary.admit_public_method_aware_input_image,command,'method_aware_input_artifact_invalid')

    def test_superseded_qc_prevents_admission_and_ready_binding(self):
        f=self.f;intake,qc,selection=f.selected()
        admitted=f.boundary.admit_public_method_aware_input_image(f.admission_command(selection))
        old={'visualQcRef':qc['visualQcRef'],'visualQcVersion':qc['visualQcVersion'],'visualQcDigest':qc['payloadDigest'],'staleReason':'superseded-review'}
        f.boundary.record_semantic_visual_qc(f.qc_command(intake,version=2,supersedes=old,result='FAIL'))
        self.reject(f.boundary.admit_public_method_aware_input_image,f.admission_command(selection),'method_aware_input_selection_required')
        self.reject(f.boundary.create_method_aware_input_plan,m10_command(f.seed,f.plan,[f.binding(admitted['assetVersion'])]))

    def test_second_candidate_cannot_create_successor(self):
        f=self.f;_,_,selection=f.selected();f.boundary.admit_public_method_aware_input_image(f.admission_command(selection))
        f.configure(stagedArtifactRef='second-staged-image',evidenceRef='second-operator-evidence')
        command={**f.command('second-intake'),'stagedArtifactRef':'second-staged-image'}
        intake=f.boundary.ingest_public_method_aware_input_candidate(command)
        qc_command=f.qc_command(intake);qc_command.update(idempotencyKey='second-qc',visualQcRef='second-qc')
        qc=f.boundary.record_semantic_visual_qc(qc_command)['semanticVisualQc']
        selected_command=f.selection_command(qc,suffix='second');f.approve(intake,qc,selected_command)
        second=f.boundary.record_human_selection(selected_command)['humanSelection']
        self.reject(f.boundary.admit_public_method_aware_input_image,f.admission_command(second,'second-admission'),
            'method_aware_input_asset_successor_not_implemented')

    def test_new_asset_resolves_exactly_one_ready_target_and_no_job(self):
        f=self.f;_,_,selection=f.selected();result=f.boundary.admit_public_method_aware_input_image(f.admission_command(selection))
        binding=f.binding(result['assetVersion'])
        plan=f.boundary.create_method_aware_input_plan(m10_command(f.seed,f.plan,[binding]))
        ready=[p for p in plan['methodInputPlans'] if p['inputPlanningState']=='READY']
        self.assertEqual(len(ready),1);self.assertEqual(ready[0]['executionClass'],'MICRO_MOTION')
        self.assertEqual(plan['resolvedAssetBindingCount'],1)
        for field,value in [('inputRole','STATIC_PLATE'),('visualExecutionRequirementRef',f.plan['visualExecutionRequirements'][0]['visualExecutionRequirementRef']),('assetVersionDigest','f'*64),('inputRequirementKey','wrong')]:
            self.reject(f.boundary.create_method_aware_input_plan,m10_command(f.seed,f.plan,[{**binding,field:value}],key='wrong-'+field))
        self.assertFalse(any(r['recordKind'] in {'VideoMethodRoute','MediaJob'} for r in f.records()))

    def test_closed_asset_authority_rejects_mutated_self_sealed_rows(self):
        f=self.f;_,_,selection=f.selected();f.boundary.admit_public_method_aware_input_image(f.admission_command(selection))
        records=f.records();authority=f.review.asset_versions
        for field,value in [('extra',True),('byteSize',True),('inputRole','STATIC_PLATE'),('sha256','a'*64),
            ('immutable',False),('publicationAllowed',True),('providerProcessingAuthorized',True),
            ('probe',{'width':8,'height':12,'format':'png','streamCount':True,'frameCount':1}),
            ('humanSelectionDigest','a'*64),('executionMethodPlanDigest','a'*64)]:
            changed=deepcopy(records);row=next(r for r in changed if r['recordKind']=='AssetVersion')
            payload={k:v for k,v in row['payload'].items() if k!='payloadDigest'};payload[field]=value
            row['payload']=assets.sealed(payload);row['payloadDigest']=row['payload']['payloadDigest']
            with self.subTest(field=field),self.assertRaises(assets.MethodAwareInputAssetError):
                authority.list_asset_versions(f.scope['workspaceRef'],f.scope['productionRunRef'],records=changed)

    def test_current_second_qc_version_can_be_selected_and_admitted(self):
        f=self.f;f.configure();intake=f.boundary.ingest_public_method_aware_input_candidate(f.command())
        qc=f.boundary.record_semantic_visual_qc(f.qc_command(intake,result='FAIL'))['semanticVisualQc']
        prior={'visualQcRef':qc['visualQcRef'],'visualQcVersion':qc['visualQcVersion'],
            'visualQcDigest':qc['payloadDigest'],'staleReason':'new-review'}
        current=f.boundary.record_semantic_visual_qc(f.qc_command(intake,version=2,supersedes=prior))['semanticVisualQc']
        selection=f.boundary.record_human_selection(f.approve(intake,current))['humanSelection']
        result=f.boundary.admit_public_method_aware_input_image(f.admission_command(selection))
        self.assertEqual(result['assetVersion']['semanticVisualQcRef'],current['visualQcRef'])
        self.assertEqual(result['assetVersion']['semanticVisualQcDigest'],current['payloadDigest'])

    def test_newer_narrative_validation_makes_intake_and_admission_stale(self):
        from tests.unit.test_narrative_currentness_m7 import validation_command
        f=self.f;_,_,selection=f.selected()
        f.boundary.create_narrative_validation(validation_command(f.seed,key='newer-e3a-validation'))
        self.reject(f.boundary.ingest_public_method_aware_input_candidate,f.command(),'method_aware_input_plan_stale')
        self.reject(f.boundary.admit_public_method_aware_input_image,f.admission_command(selection),'method_aware_input_plan_stale')
