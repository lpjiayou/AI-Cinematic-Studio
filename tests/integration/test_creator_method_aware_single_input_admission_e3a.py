"""Authenticated E3A HTTP tests; synthetic isolated image inputs only."""
import json
import unittest
from urllib.error import HTTPError
from tests.unit.test_method_aware_input_image_admission_e3a import InputImageFixture
from tests.integration.test_creator_method_aware_cutover_http import _serve_public_boundary


class CurrentInputHttpBaselineTests(unittest.TestCase):
    def setUp(self):
        self.f=InputImageFixture(self)
        self.client=self.enterContext(_serve_public_boundary(self.f.boundary,self.f.seed['assembly'],self.f.scope['workspaceRef']))
        self.path='/creator/api/v1/episode-production-runs/'+self.f.scope['productionRunRef']

    def test_candidate_resource_rejects_client_artifact_claim(self):
        with self.assertRaises(HTTPError) as caught:
            self.client.post(self.path+'/method-aware-input-candidates',{'artifactRef':'client-authority'})
        with caught.exception as response:self.assertEqual(response.code,400)

    def test_admission_resource_rejects_client_asset_authority(self):
        with self.assertRaises(HTTPError) as caught:
            self.client.post(self.path+'/method-aware-input-admission',{'assetVersionRef':'client-authority'})
        with caught.exception as response:self.assertEqual(response.code,400)


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from urllib import request
import sqlite3
from tests.unit.test_method_aware_input_image_admission_e3a import artifacts, m10_command, method_service
from tests.unit.test_narrative_currentness_m7 import validation_command


class CurrentInputSqliteHttpTests(unittest.TestCase):
    def setUp(self):
        self.f=InputImageFixture(self,sqlite=True);self.f.configure()
        self.client=self.enterContext(_serve_public_boundary(self.f.boundary,self.f.seed['assembly'],self.f.scope['workspaceRef']))
        self.path='/creator/api/v1/episode-production-runs/'+self.f.scope['productionRunRef']

    @staticmethod
    def body(command):return {k:v for k,v in command.items() if k not in {'workspaceRef','productionRunRef','reviewerRef'}}

    def post(self,resource,command):
        body=self.body(command)
        if resource=='method-aware-input-plan':
            body.pop('executionMethodPlanVersionRef',None)
            body['assetBindings']=[{k:v for k,v in b.items() if k!='assetVersionDigest'} for b in body['assetBindings']]
        return self.client.post(self.path+'/'+resource,body)

    def rejected(self,operation,status,code=None):
        before=self.f.records()
        with self.assertRaises(HTTPError) as caught:operation()
        with caught.exception as response:
            value=json.loads(response.read());self.assertEqual(response.code,status)
        if code:self.assertIn(code,json.dumps(value))
        self.assertNotIn(str(self.f.root),json.dumps(value));self.assertEqual(self.f.records(),before)

    def selected(self):
        status,intake=self.post('method-aware-input-candidates',self.f.command());self.assertEqual(status,201)
        _,qc_result=self.post('semantic-visual-qc',self.f.qc_command(intake));qc=qc_result['semanticVisualQc']
        command=self.f.approve(intake,qc)
        _,selected=self.post('media-selection',command)
        return intake,qc,selected['humanSelection']

    def test_real_http_chain_exact_replay_ready_and_redaction(self):
        f=self.f;before=len(f.records());intake,qc,selection=self.selected()
        self.assertEqual(len(f.records())-before,5)
        status,result=self.post('method-aware-input-admission',f.admission_command(selection));self.assertEqual(status,201)
        self.assertEqual(len(f.records())-before,7)
        status,replay=self.post('method-aware-input-admission',f.admission_command(selection));self.assertEqual(status,200)
        self.assertEqual(result['assetVersion'],replay['assetVersion'])
        status,replay=self.post('method-aware-input-candidates',f.command());self.assertEqual(status,200)
        self.assertEqual(intake['candidate'],replay['candidate'])
        status,plan=self.post('method-aware-input-plan',m10_command(f.seed,f.plan,[f.binding(result['assetVersion'])]))
        self.assertEqual(status,201)
        self.assertEqual(plan['resolvedAssetBindingCount'],1);self.assertEqual(plan['inputReadyCount'],1)
        for value in (intake,result,plan):
            encoded=json.dumps(value)
            for private in ('storageKey','sourceRoot','absolutePath',str(f.root),'rawBundle'):self.assertNotIn(private,encoded)
        self.assertFalse(result['assetVersion']['publicationAllowed']);self.assertFalse(result['assetVersion']['providerProcessingAuthorized'])
        for resource in ('method-aware-input-candidates','method-aware-input-admission'):
            self.rejected(lambda:self.client.get(self.path+'/'+resource),405)
        self.assertFalse(any(r['recordKind'] in {'VideoMethodRoute','MediaJob'} for r in f.records()))

    def test_unauthenticated_and_duplicate_or_nonstandard_json_rejected(self):
        path=self.client.base+self.path+'/method-aware-input-candidates'
        valid=self.body(self.f.command())
        unauth=request.Request(path,data=json.dumps(valid).encode(),headers={'Content-Type':'application/json'},method='POST')
        self.rejected(lambda:request.urlopen(unauth),401)
        for data in (json.dumps(valid)[:-1]+',"projectRef":"duplicate"}',json.dumps({**valid,'bad':float('nan')}),
                     json.dumps({**valid,'bad':float('inf')})):
            req=request.Request(path,data=data.encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+self.client.token},method='POST')
            self.rejected(lambda:request.urlopen(req),400)

    def test_closed_request_fields_and_integer_are_rejected_before_authority(self):
        f=self.f
        for field in ('workspaceRef','candidateRef','candidateVersion','technicalValidationRef','artifactRef','artifactDigest',
                      'artifactByteSize','storageKey','width','height','mediaType','contentDigest','inputRole','provenance',
                      'usageScope','providerProcessingAuthorized','publicationAllowed','providerId','modelId','backendRef'):
            payload={**self.body(f.command()),field:'client-claim'}
            self.rejected(lambda:self.client.post(self.path+'/method-aware-input-candidates',payload),400)
        _,_,selection=self.selected()
        for value in (True,1.5,'1'):
            self.rejected(lambda:self.post('method-aware-input-admission',{**f.admission_command(selection),'humanSelectionVersion':value}),400)
        for field in ('assetVersionRef','assetAdmissionRef','authorityState','providerProcessingAuthorized'):
            self.rejected(lambda:self.post('method-aware-input-admission',{**f.admission_command(selection),field:'client'}),400)

    def test_missing_bundle_unknown_artifact_foreign_scope_and_stale_plan(self):
        f=self.f
        port=f.boundary._EpisodeProductionPublicBoundary__method_aware_input_assets.artifact_evidence
        f.boundary._EpisodeProductionPublicBoundary__method_aware_input_assets.artifact_evidence=artifacts.RejectingMethodAwareInputArtifactEvidence()
        self.rejected(lambda:self.post('method-aware-input-candidates',f.command()),503,'method_aware_input_artifact_unavailable')
        f.boundary._EpisodeProductionPublicBoundary__method_aware_input_assets.artifact_evidence=port
        self.rejected(lambda:self.post('method-aware-input-candidates',{**f.command(),'stagedArtifactRef':'unknown'}),404,'method_aware_input_artifact_not_found')
        self.rejected(lambda:self.post('method-aware-input-candidates',{**f.command(),'projectRef':'foreign'}),404,'method_aware_input_scope_mismatch')
        f.boundary.create_narrative_validation(validation_command(f.seed,key='newer-validation'))
        self.rejected(lambda:self.post('method-aware-input-candidates',f.command()),409,'method_aware_input_plan_stale')

    def test_external_selection_required_and_browser_authority_forbidden(self):
        f=self.f;_,intake=self.post('method-aware-input-candidates',f.command())
        _,value=self.post('semantic-visual-qc',f.qc_command(intake));qc=value['semanticVisualQc']
        self.rejected(lambda:self.post('media-selection',f.selection_command(qc)),403,'media_selection_approval_required')
        command=f.approve(intake,qc)
        for field in ('actorRef','actorKind','authorityRef','authorityDecisionDigest','subjectDigest'):
            self.rejected(lambda:self.post('media-selection',{**command,field:'browser'}),400)
        self.rejected(lambda:self.post('media-selection',{**command,'approvalRef':'changed-subject'}),403)
        _,selected=self.post('media-selection',command)
        self.assertEqual(selected['humanSelection']['actorRef'],'external-human-fixture')
        self.assertFalse(any(r['recordKind']=='AssetVersion' for r in f.records()))

    def test_sqlite_record_two_and_three_failure_rolls_back_entire_intake(self):
        f=self.f;before=f.records();original=f.evidence._connect
        for failing_kind in ('Candidate','TechnicalValidation'):
            inserted=[]
            class FailingConnection:
                def __init__(self):self.connection=original()
                def __getattr__(self,name):return getattr(self.connection,name)
                def execute(self,sql,params=()):
                    if sql.startswith('INSERT INTO v5_episode_production_records'):
                        if params[3]==failing_kind:raise sqlite3.OperationalError('injected batch failure')
                        inserted.append(params[3])
                    return self.connection.execute(sql,params)
            with patch.object(f.evidence,'_connect',side_effect=FailingConnection):
                self.rejected(lambda:self.post('method-aware-input-candidates',f.command()),503)
            self.assertEqual(inserted,['MethodAwareInputArtifact']+(['Candidate'] if failing_kind=='TechnicalValidation' else []))
            self.assertEqual(f.records(),before)
        self.assertEqual(self.post('method-aware-input-candidates',f.command())[0],201)
        self.assertEqual(len(f.records())-len(before),3)

    def test_sqlite_asset_insert_failure_rolls_back_admission(self):
        f=self.f;_,_,selection=self.selected();before=f.records();original=f.evidence._connect;inserted=[]
        class FailingConnection:
            def __init__(self):self.connection=original()
            def __getattr__(self,name):return getattr(self.connection,name)
            def execute(self,sql,params=()):
                if sql.startswith('INSERT INTO v5_episode_production_records'):
                    if params[3]=='AssetVersion':raise sqlite3.OperationalError('injected asset failure')
                    inserted.append(params[3])
                return self.connection.execute(sql,params)
        with patch.object(f.evidence,'_connect',side_effect=FailingConnection):
            self.rejected(lambda:self.post('method-aware-input-admission',f.admission_command(selection)),503)
        self.assertEqual(inserted,['AssetAdmission']);self.assertEqual(f.records(),before)
        self.assertEqual(self.post('method-aware-input-admission',f.admission_command(selection))[0],201)
        self.assertEqual(len(f.records())-len(before),2)

    def test_concurrent_intake_and_admission_have_one_batch(self):
        f=self.f
        def race(resource,command,count):
            before=len(f.records());barrier=Barrier(2);original=f.evidence.append_records
            def append(records,**kwargs):barrier.wait(timeout=10);return original(records,**kwargs)
            with patch.object(f.evidence,'append_records',side_effect=append),ThreadPoolExecutor(2) as pool:
                futures=[pool.submit(self.post,resource,command) for _ in range(2)]
                results=[future.result(timeout=20) for future in futures]
            self.assertEqual(sorted(s for s,_ in results),[200,201]);self.assertEqual(len(f.records())-before,count)
            return results[0][1]
        intake=race('method-aware-input-candidates',f.command(),3)
        _,value=self.post('semantic-visual-qc',f.qc_command(intake));qc=value['semanticVisualQc']
        _,value=self.post('media-selection',f.approve(intake,qc));selection=value['humanSelection']
        race('method-aware-input-admission',f.admission_command(selection),2)

    def test_response_loss_replays_committed_candidate_and_admission(self):
        from apps.creator_workspace_mvp.server import CreatorRequestHandler
        from http.client import RemoteDisconnected
        import socket
        f=self.f;original=CreatorRequestHandler._send_json
        def lose_response(handler,status,payload,**kwargs):
            if status==201 and ('inputArtifactReceipt' in payload or 'assetAdmission' in payload):
                handler.connection.shutdown(socket.SHUT_RDWR);handler.connection.close();return
            return original(handler,status,payload,**kwargs)
        before=len(f.records())
        with patch.object(CreatorRequestHandler,'_send_json',new=lose_response):
            with self.assertRaises(RemoteDisconnected):self.post('method-aware-input-candidates',f.command())
        status,intake=self.post('method-aware-input-candidates',f.command());self.assertEqual(status,200)
        self.assertEqual(len(f.records())-before,3)
        _,value=self.post('semantic-visual-qc',f.qc_command(intake));qc=value['semanticVisualQc']
        _,value=self.post('media-selection',f.approve(intake,qc));selection=value['humanSelection'];before=len(f.records())
        with patch.object(CreatorRequestHandler,'_send_json',new=lose_response):
            with self.assertRaises(RemoteDisconnected):self.post('method-aware-input-admission',f.admission_command(selection))
        self.assertEqual(self.post('method-aware-input-admission',f.admission_command(selection))[0],200)
        self.assertEqual(len(f.records())-before,2)


class CurrentInputRestartTests(unittest.TestCase):
    def test_closed_server_new_sqlite_adapter_and_repinned_authorities_replay(self):
        f=InputImageFixture(self,sqlite=True);f.configure();path='/creator/api/v1/episode-production-runs/'+f.scope['productionRunRef']
        body=CurrentInputSqliteHttpTests.body
        with _serve_public_boundary(f.boundary,f.seed['assembly'],f.scope['workspaceRef']) as client:
            _,intake=client.post(path+'/method-aware-input-candidates',body(f.command()))
            _,value=client.post(path+'/semantic-visual-qc',body(f.qc_command(intake)));qc=value['semanticVisualQc']
            _,value=client.post(path+'/media-selection',body(f.approve(intake,qc)));selection=value['humanSelection']
            _,admission=client.post(path+'/method-aware-input-admission',body(f.admission_command(selection)))
        before=f.records();old=f.boundary;f.restart();self.assertIsNot(old,f.boundary)
        with _serve_public_boundary(f.boundary,f.seed['assembly'],f.scope['workspaceRef']) as client:
            status,replay=client.post(path+'/method-aware-input-candidates',body(f.command()));self.assertEqual(status,200)
            self.assertEqual(intake['candidate'],replay['candidate'])
            status,replay=client.post(path+'/method-aware-input-admission',body(f.admission_command(selection)));self.assertEqual(status,200)
            self.assertEqual(admission['assetVersion'],replay['assetVersion']);self.assertEqual(f.records(),before)
            status,plan=client.post(path+'/method-aware-input-plan',{**{k:v for k,v in body(m10_command(f.seed,f.plan,[])).items() if k!='executionMethodPlanVersionRef'},'assetBindings':[{k:v for k,v in f.binding(admission['assetVersion']).items() if k!='assetVersionDigest'}]})
            self.assertEqual(status,201);self.assertEqual(plan['resolvedAssetBindingCount'],1);self.assertEqual(plan['inputReadyCount'],1)
        # A changed bundle cannot silently become the authority on a subsequent process start.
        f.bundle_path.write_bytes(f.bundle_path.read_bytes()+b' ')
        with self.assertRaises(artifacts.MethodAwareInputArtifactError):f.restart()
