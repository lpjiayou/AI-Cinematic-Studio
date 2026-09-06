"""E2 real HTTP/SQLite result intake with synthetic CPU artifacts only."""
import json
import socket
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import RemoteDisconnected
from threading import Barrier
from unittest.mock import patch
from urllib import request, parse
from urllib.error import HTTPError
from apps.creator_workspace_mvp.server import CreatorRequestHandler
from services.v4_platform import SqliteMediaJobAdapter
from tests.unit import test_method_aware_media_m10_m11 as plans
from tests.unit.test_method_aware_job_result_intake_e2 import ResultFixture
from tests.unit.test_episode_production_k2 import WORKSPACE
from tests.integration.test_creator_method_aware_cutover_http import _serve_public_boundary


class MethodAwareResultHttpTests(unittest.TestCase):
    def setUp(self):
        self.f = ResultFixture(self, sqlite=True)
        self.client = self.enterContext(_serve_public_boundary(
            self.f.boundary, self.f.seed['assembly'], WORKSPACE))
        self.path = '/creator/api/v1/episode-production-runs/'+self.f.run_ref
        self.query = {k:self.f.scope[k] for k in ('projectRef','seriesRef','episodeRef')}
        self.query['versionRef'] = self.f.route['videoMethodRouteVersionRef']

    def body(self):
        return {k:v for k,v in self.f.command().items() if k not in {'workspaceRef','productionRunRef'}}

    def assert_http_error(self, operation, status, code=None):
        with self.assertRaises(HTTPError) as caught:
            operation()
        with caught.exception as response:
            self.assertEqual(response.code,status)
            body=json.loads(response.read())
        self.assertFalse(body['ok'])
        if code is not None:self.assertEqual(body['error']['code'],code)
        return body

    def raw(self, *, body=None, query='', resource='method-aware-video-candidates'):
        req=request.Request(self.client.base+self.path+'/'+resource+query,
            data=body.encode() if body is not None else None,
            headers={'Content-Type':'application/json','Authorization':'Bearer '+self.client.token})
        with request.urlopen(req,timeout=10) as response:
            return response.status,json.loads(response.read())

    def test_http_status_then_intake_then_replay(self):
        status, value = self.client.get(self.path+'/method-aware-video-jobs', **self.query)
        self.assertEqual(status, 200)
        self.assertEqual(value['jobProjection']['jobs'][0]['jobState'], 'SUCCEEDED')
        command = self.f.command()
        body = {k:v for k,v in command.items() if k not in {'workspaceRef','productionRunRef'}}
        status, result = self.client.post(self.path+'/method-aware-video-candidates', body)
        self.assertEqual(status, 201)
        status, replay = self.client.post(self.path+'/method-aware-video-candidates', body)
        self.assertEqual(status, 200)
        self.assertTrue(replay['idempotentReplay'])
        self.assertEqual(replay['candidate'], result['candidate'])

    def test_result_resource_rejects_browser_artifact_authority(self):
        before = self.f.records()
        with self.assertRaises(HTTPError) as caught:
            self.client.post(self.path+'/method-aware-video-candidates', {'artifactRef':'browser-artifact'})
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        self.assertEqual(self.f.records(), before)

    def test_browser_claims_and_invalid_scalar_types_are_closed_before_write(self):
        body=self.body();before=self.f.records()
        for field in ('workspaceRef','productionRunRef','candidateRef','artifactRef','providerId','modelId',
                'adapterIdentity','attemptRef','checks','provenance','publicationAllowed','storageKey','unknown'):
            with self.subTest(field=field):
                self.assert_http_error(lambda:self.client.post(self.path+'/method-aware-video-candidates',
                    {**body,field:'browser-value'}),400)
        for field in body:
            with self.subTest(fractional_field=field):
                self.assert_http_error(lambda:self.client.post(self.path+'/method-aware-video-candidates',
                    {**body,field:1.5}),400)
        self.assertEqual(self.f.records(),before)

    def test_nonstandard_json_and_duplicate_keys_are_rejected(self):
        body=self.body();before=self.f.records()
        for number in ('NaN','Infinity','-Infinity'):
            malformed=json.dumps(body).replace(json.dumps(body['idempotencyKey']),number)
            self.assert_http_error(lambda:self.raw(body=malformed),400)
        duplicate=json.dumps(body)[:-1]+',"idempotencyKey":"duplicate"}'
        self.assert_http_error(lambda:self.raw(body=duplicate),400)
        self.assertEqual(self.f.records(),before)

    def test_query_closed_shape_duplicate_parameters_and_methods(self):
        query='?'+parse.urlencode(self.query)
        for suffix in ('&unknown=x','&projectRef=duplicate','&projectRef=','&workspaceRef=foreign'):
            self.assert_http_error(lambda:self.raw(query=query+suffix,resource='method-aware-video-jobs'),400)
        self.assert_http_error(lambda:self.raw(resource='method-aware-video-jobs'),400)
        self.assert_http_error(lambda:self.raw(),405,'method_not_allowed')
        self.assert_http_error(lambda:self.raw(body='{}',resource='method-aware-video-jobs'),405,'method_not_allowed')

    def test_foreign_scope_stale_route_and_invalid_artifact_have_safe_errors(self):
        body=self.body(); before=self.f.records()
        self.assert_http_error(lambda:self.client.post(self.path+'/method-aware-video-candidates',
            {**body,'projectRef':'foreign'}),404,'method_aware_job_scope_mismatch')
        self.assert_http_error(lambda:self.client.post(self.path+'/method-aware-video-candidates',
            {**body,'videoMethodRouteDigest':'0'*64}),409,'method_aware_job_route_stale')
        from pathlib import Path
        artifact=Path(self.f.done['artifact']['internalPath']);artifact.write_bytes(b'not-video')
        value=self.assert_http_error(lambda:self.client.post(self.path+'/method-aware-video-candidates',body),
                                    409,'method_aware_job_result_invalid')
        self.assertNotIn(str(self.f.root),json.dumps(value));self.assertEqual(self.f.records(),before)

    def test_read_and_intake_unavailable_without_read_port_are_stable(self):
        body=self.body();service=self.f.boundary._EpisodeProductionPublicBoundary__method_aware_result_intake
        with patch.object(service,'reader',None):
            self.assert_http_error(lambda:self.client.post(self.path+'/method-aware-video-candidates',body),
                                    503,'method_aware_job_result_unavailable')
            self.assert_http_error(lambda:self.client.get(self.path+'/method-aware-video-jobs',**self.query),
                                    503,'method_aware_job_result_unavailable')

    def test_public_result_is_neutral_and_old_route_snapshot_remains_queued(self):
        _,result=self.client.post(self.path+'/method-aware-video-candidates',self.body())
        _,projection=self.client.get(self.path+'/method-aware-video-jobs',**self.query)
        for value in (result,projection):
            text=json.dumps(value)
            for field in ('internalPath','leaseToken','credentialSourceRef','providerRequestRef','workerRef',
                          'providerId','modelId','adapterIdentity','executionEnvelope','backendBinding'):
                self.assertNotIn('"'+field+'"',text)
            self.assertNotIn(str(self.f.root),text)
        route=self.f.boundary.get_method_aware_video_route(
            *[self.f.scope[k] for k in ('workspaceRef','projectRef','seriesRef','episodeRef','productionRunRef')],
            self.f.route['videoMethodRouteVersionRef'])
        self.assertEqual(route['payloadDigest'],self.f.route['payloadDigest'])
        self.assertEqual(route['queuedJobs'][0]['queueState'],'QUEUED')

    def test_connection_loss_after_commit_replays_the_same_three_records(self):
        body=self.body();before=len(self.f.records());original=CreatorRequestHandler._send_json
        def lose_response(handler,status,payload,**kwargs):
            if status == 201 and 'resultReceipt' in payload:
                handler.connection.shutdown(socket.SHUT_RDWR)
                handler.connection.close()
                return
            return original(handler,status,payload,**kwargs)
        with patch.object(CreatorRequestHandler,'_send_json',new=lose_response):
            with self.assertRaises(RemoteDisconnected):
                self.client.post(self.path+'/method-aware-video-candidates',body)
        committed=self.f.records()
        self.assertEqual(len(committed)-before,3)
        status,replay=self.client.post(self.path+'/method-aware-video-candidates',body)
        self.assertEqual(status,200);self.assertTrue(replay['idempotentReplay'])
        self.assertEqual(self.f.records(),committed)

    def test_sqlite_failure_during_second_insert_rolls_back_entire_batch(self):
        body=self.body();before=self.f.records();original=self.f.evidence._connect
        inserted=[]
        class FailingConnection:
            def __init__(self):self.connection=original()
            def __getattr__(self,name):return getattr(self.connection,name)
            def execute(self,sql,params=()):
                if sql.startswith('INSERT INTO v5_episode_production_records'):
                    if params[3]=='Candidate':raise sqlite3.OperationalError('injected second insert failure')
                    inserted.append(params[3])
                return self.connection.execute(sql,params)
        with patch.object(self.f.evidence,'_connect',side_effect=FailingConnection):
            self.assert_http_error(lambda:self.client.post(self.path+'/method-aware-video-candidates',body),503)
        self.assertEqual(inserted,['MethodAwareMediaJobResult'])
        self.assertEqual(self.f.records(),before)
        status,_=self.client.post(self.path+'/method-aware-video-candidates',body)
        self.assertEqual(status,201);self.assertEqual(len(self.f.records())-len(before),3)

    def test_concurrent_sqlite_http_submits_append_only_one_batch(self):
        body=self.body();before=len(self.f.records());barrier=Barrier(2);original=self.f.evidence.append_records
        def race(records,**kwargs):
            barrier.wait(timeout=10)
            return original(records,**kwargs)
        with patch.object(self.f.evidence,'append_records',side_effect=race),ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(self.client.post,self.path+'/method-aware-video-candidates',body) for _ in range(2)]
            results=[f.result(timeout=20) for f in futures]
        self.assertEqual(sorted(status for status,_ in results),[200,201])
        self.assertEqual(results[0][1]['candidate'],results[1][1]['candidate'])
        self.assertEqual(len(self.f.records())-before,3)


class MethodAwareResultRestartTests(unittest.TestCase):
    def test_closed_server_and_new_sqlite_adapters_preserve_result_and_replay(self):
        f=ResultFixture(self,sqlite=True)
        path='/creator/api/v1/episode-production-runs/'+f.run_ref
        body={k:v for k,v in f.command().items() if k not in {'workspaceRef','productionRunRef'}}
        query={k:f.scope[k] for k in ('projectRef','seriesRef','episodeRef')}
        with _serve_public_boundary(f.boundary,f.seed['assembly'],WORKSPACE) as client:
            _,first=client.post(path+'/method-aware-video-candidates',body)
        records=f.records();job=f.jobs.get(WORKSPACE,f.run_ref,f.job_ref);old_boundary=f.boundary
        f.jobs=SqliteMediaJobAdapter(f.root/'jobs.sqlite3',initialize_if_missing=False)
        f.coordinator=f.make_coordinator();f.boundary=f.make_boundary(restart=True)
        self.assertIsNot(f.boundary,old_boundary)
        f.evidence=plans.method_service(f.boundary).evidence_repository
        with _serve_public_boundary(f.boundary,f.seed['assembly'],WORKSPACE) as client:
            status,replay=client.post(path+'/method-aware-video-candidates',body)
            self.assertEqual(status,200)
            for k in ('candidate','technicalValidation','resultReceipt'):self.assertEqual(first[k],replay[k])
            status,projection=client.get(path+'/method-aware-video-jobs',**query)
            self.assertEqual(status,200)
            self.assertEqual(projection['jobProjection']['jobs'][0]['candidateIntakeState'],'RECORDED')
        self.assertEqual(f.records(),records)
        self.assertEqual(f.jobs.get(WORKSPACE,f.run_ref,f.job_ref),job)
