"""E1 real SQLite/CLI/loopback I2V checks; no real ComfyUI, GPU or provider."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from services.v4_platform import SqliteMediaJobAdapter, MediaJobCoordinator
from services.v4_platform.comfyui import (
    build_comfyui_runtime_attestation, ComfyUIWan22ImageToVideoAdapter,
    ComfyUIProviderTimeoutError,
)
from services.v4_platform.backend_registry import canonical, digest
from services.v4_platform.method_aware_worker import (
    create_method_aware_coordinator_from_environment, main as worker_main,
)
from tests.unit import test_method_aware_worker_e1 as worker_fixtures
from tests.unit import test_v4_comfyui_adapter as comfy_fixtures
from tests.unit.test_method_aware_media_m10_m11 import backend_registry_fixture


class MethodAwareWorkerSqliteIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        worker_fixtures.ExactWorkerTests.setUpClass()

    def setUp(self):
        self.case=worker_fixtures.ExactWorkerTests();self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.db=self.case.root/'jobs.sqlite3'
        self.case.repo=SqliteMediaJobAdapter(self.db)
        self.case.queue=self.case.coordinator()

    def test_restart_success_exact_replay_and_no_schema_or_candidate_writes(self):
        job=self.case.dispatch();other=self.case.dispatch(key='unrelated')
        with sqlite3.connect(self.db) as con:
            schema=con.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
        self.case.repo=SqliteMediaJobAdapter(self.db,initialize_if_missing=False)
        self.case.queue=self.case.coordinator()
        done=self.case.run_job(job)
        self.assertEqual(done['state'],'SUCCEEDED');self.assertEqual(self.case.adapter.calls,1)
        reread=SqliteMediaJobAdapter(self.db,initialize_if_missing=False).get(job['workspaceRef'],job['productionRunRef'],job['jobRef'])
        self.assertEqual(done,reread)
        self.assertEqual(self.case.run_job(job),done)
        self.assertEqual(self.case.repo.get(other['workspaceRef'],other['productionRunRef'],other['jobRef']),other)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(schema,con.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall())
        self.assertEqual(set(name for kind,name,_ in schema if kind=='table'),
                         {'v4_media_job_schema','v4_media_jobs','v4_media_job_batches'})

    def test_expired_unknown_submission_restart_has_no_second_call(self):
        class ProcessDeath(BaseException):pass
        job=self.case.dispatch();self.case.adapter.fail=ProcessDeath()
        with self.assertRaises(ProcessDeath):self.case.run_job(job)
        self.case.now='2026-09-06T00:03:00Z'
        self.case.repo=SqliteMediaJobAdapter(self.db,initialize_if_missing=False)
        self.case.queue=self.case.coordinator()
        done=self.case.run_job(job)
        self.assertEqual(done['attempts'][0]['failureClass'],'REMOTE_SUBMISSION_INDETERMINATE')
        self.assertTrue(done['attempts'][0]['nonRetryable']);self.assertEqual(self.case.adapter.calls,1)

    def test_binding_change_is_a_conflict_even_with_identical_public_request(self):
        job=self.case.dispatch()
        changed=backend_registry_fixture(providerId='another-provider')
        self.case.queue.backend_resolver=changed
        decision=changed.resolve('MICRO_MOTION','SINGLE_ANCHOR_I2V',['ACTION_READY_ANCHOR'],self.case.context['outputConstraints'])
        with self.assertRaises(Exception):self.case.queue.dispatch(self.case.request,idempotency_key='target',
            backend_binding=decision,execution_context=self.case.context)
        self.assertEqual(self.case.repo.get(job['workspaceRef'],job['productionRunRef'],job['jobRef']),job)

    def test_recover_committed_artifact_without_second_adapter_call(self):
        # Interrupt the existing durable publication->terminal-save window.
        original=self.case.repo.save
        class ProcessDeath(BaseException):pass
        def save(value, expected):
            if value['state']=='SUCCEEDED':raise ProcessDeath()
            return original(value,expected)
        job=self.case.dispatch()
        with patch.object(self.case.repo,'save',side_effect=save):
            with self.assertRaises(ProcessDeath):self.case.run_job(job)
        self.case.now='2026-09-06T00:03:00Z'
        self.case.repo=SqliteMediaJobAdapter(self.db,initialize_if_missing=False)
        self.case.queue=self.case.coordinator()
        done=self.case.run_job(job)
        self.assertEqual(done['state'],'SUCCEEDED');self.assertEqual(self.case.adapter.calls,1)

    def test_corrupted_committed_artifact_fails_without_retry_or_orphan(self):
        original=self.case.repo.save
        class ProcessDeath(BaseException):pass
        def save(value,expected):
            if value['state']=='SUCCEEDED':raise ProcessDeath()
            return original(value,expected)
        job=self.case.dispatch()
        with patch.object(self.case.repo,'save',side_effect=save):
            with self.assertRaises(ProcessDeath):self.case.run_job(job)
        current=self.case.repo.get(job['workspaceRef'],job['productionRunRef'],job['jobRef'])
        Path(current['artifactCommitIntent']['artifact']['internalPath']).write_bytes(b'corrupt')
        self.case.now='2026-09-06T00:03:00Z'
        self.case.repo=SqliteMediaJobAdapter(self.db,initialize_if_missing=False)
        self.case.queue=self.case.coordinator()
        done=self.case.run_job(job)
        self.assertEqual(done['state'],'FAILED')
        self.assertEqual(done['attempts'][0]['failureClass'],'ARTIFACT_RECOVERY_MISMATCH')
        self.assertTrue(done['attempts'][0]['nonRetryable'])
        self.assertIsNone(done['artifactCommitIntent'])
        self.assertEqual(self.case.adapter.calls,1)


class MethodAwareComfyLoopbackIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        worker_fixtures.ExactWorkerTests.setUpClass()

    def setUp(self):
        self.case=worker_fixtures.ExactWorkerTests();self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.comfy=comfy_fixtures.V4ComfyUIWan22AdapterTests();self.comfy.setUp()
        self.addCleanup(self.comfy.tearDown)
        self.root=self.case.root
        config=self.comfy.config()
        model_root=self.root/'models';files={}
        for field,directory,name in [('unet_sha256','diffusion_models',config.unet_name),
                                    ('clip_sha256','text_encoders',config.clip_name),
                                    ('vae_sha256','vae',config.vae_name)]:
            path=model_root/directory/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(('fake-test-model-'+name).encode());files[field]=sha256(path.read_bytes()).hexdigest()
        config=replace(config,**files,cost_minor_per_attempt=1)
        attestation=build_comfyui_runtime_attestation(config,model_root,
            observed_at='2026-09-06T00:00:00Z',require_start_image=True)
        self.attestation=attestation
        config=replace(config,runtime_attestation_digest=attestation['payloadDigest'])
        profile={'schemaVersion':'v4.comfyui-i2v-backend-profile.v1','parameters':{
            'steps':20,'seed':1,'cfg':5.0,'samplerName':'uni_pc','scheduler':'simple','modelShift':8.0,
            'negativePrompt':'blurry, distorted, extra limbs'},'modelFiles':attestation['facts']['modelFiles']}
        self.registry=backend_registry_fixture(profile=profile,providerId=config.provider_id,modelId=config.model_id,
            region=config.region,endpointClass=config.endpoint_class,costCurrency=config.cost_currency,
            runtimeAttestationRef=config.runtime_attestation_ref,runtimeAttestationDigest=config.runtime_attestation_digest)
        manifest=self.root/'registry.json';manifest.write_bytes(canonical(self.registry._manifest))
        attest=self.root/'attestation.json';attest.write_bytes(canonical(attestation))
        input_root=self.root/'input';input_root.mkdir()
        self.env={'CREATOR_METHOD_AWARE_BACKEND_REGISTRY':str(manifest),
            'CREATOR_METHOD_AWARE_BACKEND_REGISTRY_SHA256':sha256(manifest.read_bytes()).hexdigest(),
            'CREATOR_METHOD_AWARE_SOURCE_ROOT':str(self.case.sources),
            'METHOD_AWARE_COMFYUI_BASE_URL':config.base_url,'METHOD_AWARE_COMFYUI_COST_MINOR_PER_ATTEMPT':'1',
            'METHOD_AWARE_COMFYUI_RUNTIME_ATTESTATION':str(attest),
            'METHOD_AWARE_COMFYUI_INPUT_ROOT':str(input_root),'METHOD_AWARE_COMFYUI_MODEL_ROOT':str(model_root),
            'TEST_CREDENTIAL':'fake-test-secret-never-persist'}
        video=self.root/'provider.mp4';worker_fixtures.media_file(video,frames=9)
        self.comfy.server.video_bytes=video.read_bytes()
        self.db=self.root/'shared-jobs.sqlite3'
        self.case.repo=SqliteMediaJobAdapter(self.db)
        self.queue=create_method_aware_coordinator_from_environment(self.case.repo,self.root/'artifacts',environ=self.env)
        self.case.queue=self.queue
        self.case.binding=self.registry.resolve('MICRO_MOTION','SINGLE_ANCHOR_I2V',['ACTION_READY_ANCHOR'],self.case.context['outputConstraints'])

    def test_production_cli_uses_i2v_shared_store_exactly_once(self):
        job=self.case.dispatch();other=self.case.dispatch(key='other')
        args=['run-one','--job-ref',job['jobRef'],'--workspace-ref',job['workspaceRef'],
            '--production-run-ref',job['productionRunRef'],'--worker-ref','loopback-worker-1',
            '--queue-db',str(self.db),'--artifact-root',str(self.root/'artifacts'),
            '--backend-registry-manifest',self.env['CREATOR_METHOD_AWARE_BACKEND_REGISTRY'],
            '--backend-registry-sha256',self.env['CREATOR_METHOD_AWARE_BACKEND_REGISTRY_SHA256'],'--max-attempts','1']
        output=io.StringIO()
        with contextlib.redirect_stdout(output):code=worker_main(args,environ=self.env)
        self.assertEqual(code,0,output.getvalue())
        done=self.case.repo.get(job['workspaceRef'],job['productionRunRef'],job['jobRef'])
        self.assertEqual(done['state'],'SUCCEEDED')
        self.assertEqual(done['artifact']['adapterIdentity'],ComfyUIWan22ImageToVideoAdapter.adapter_identity)
        self.assertEqual(int(done['artifact']['probe']['streams'][0]['nb_read_frames']),8)
        self.assertIn('LoadImage',{n['class_type'] for n in self.comfy.server.last_prompt['prompt'].values()})
        self.assertEqual(self.case.repo.get(other['workspaceRef'],other['productionRunRef'],other['jobRef']),other)
        self.assertNotIn(self.env['TEST_CREDENTIAL'],json.dumps(done))
        self.assertNotIn(str(self.case.sources),json.dumps(done['executionEnvelope']))
        self.assertEqual(list(self.root.glob('*.sqlite3')),[self.db])

    def test_prompt_response_loss_is_terminal_and_never_reposted(self):
        client=self.queue.adapter.client;original=client.json;post_count=0
        def response_loss(method,path,**kwargs):
            nonlocal post_count
            if method=='POST':
                post_count+=1
                original(method,path,**kwargs)  # The loopback server accepted this request.
                raise ComfyUIProviderTimeoutError('simulated lost response')
            return original(method,path,**kwargs)
        job=self.case.dispatch()
        with patch.object(client,'json',side_effect=response_loss):done=self.case.run_job(job)
        self.assertEqual(done['state'],'FAILED')
        self.assertEqual(done['attempts'][0]['failureClass'],'REMOTE_SUBMISSION_INDETERMINATE')
        restarted=create_method_aware_coordinator_from_environment(
            SqliteMediaJobAdapter(self.db,initialize_if_missing=False),self.root/'artifacts',environ=self.env)
        self.assertEqual(restarted.run_one(job['workspaceRef'],job['productionRunRef'],job['jobRef'],'restart-worker')['state'],'FAILED')
        self.assertEqual(post_count,1)

    def test_model_attestation_profile_and_probe_change_zero_provider_calls(self):
        for mutation in ('model','attestation','profile','probe'):
            with self.subTest(mutation=mutation):
                job=self.case.dispatch(key=mutation)
                adapter=self.queue.adapter
                if mutation=='model':
                    path=Path(self.env['METHOD_AWARE_COMFYUI_MODEL_ROOT'])/'vae'/adapter.config.vae_name
                    original=path.read_bytes();path.write_bytes(b'wrong')
                elif mutation=='attestation':adapter.runtime_attestation['facts']['deviceName']='changed'
                elif mutation=='profile':adapter.backend_registry=backend_registry_fixture()
                else:
                    original_resolve=adapter.source_locator.resolve
                    adapter.source_locator.resolve=lambda req:{**original_resolve(req),'width':65}
                with patch.object(adapter.client,'json',side_effect=AssertionError('provider call forbidden')) as calls:
                    done=self.case.run_job(job)
                self.assertEqual(done['state'],'FAILED');self.assertEqual(calls.call_count,0)
                self.assertEqual(done['attempts'][0]['failureClass'],'PRE_EXECUTION_VALIDATION_FAILED')
                if mutation=='model':path.write_bytes(original)
                elif mutation=='attestation':adapter.runtime_attestation=deepcopy(self.attestation)
                elif mutation=='profile':adapter.backend_registry=self.registry
                else:adapter.source_locator.resolve=original_resolve

    def test_application_environment_composition_shares_exact_job_repository(self):
        from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
        from services.v5_core_os.episode_production.public import create_local_development_boundary_from_environment
        from tests.unit.test_method_aware_media_m10_m11 import method_service
        from tests.unit.test_method_aware_input_image_admission_e3a import InputImageFixture
        life=LifecycleAssembly.in_memory()
        # E3A shares this source root and requires all artifact-authority settings together.
        image=InputImageFixture(self)
        image.source_root=self.case.sources
        image.source=image.source_root/(image.content_digest+'.png')
        image.source.write_bytes(image.content)
        image.configure()
        env={**self.env,**image.environment,'CREATOR_EPISODE_PRODUCTION_DATA_PATH':str(self.root/'episode.sqlite3'),
             'CREATOR_MEDIA_JOB_DATA_PATH':str(self.db),'CREATOR_MEDIA_ARTIFACT_ROOT':str(self.root/'artifacts')}
        boundary=create_local_development_boundary_from_environment(
            project_boundary=life.project_context,series_episode_boundary=life.series_episode,
            series_planning_boundary=life.series_planning,script_studio_boundary=life.script_studio,environ=env)
        execution=method_service(boundary).media_jobs
        self.assertIsInstance(execution.adapter,ComfyUIWan22ImageToVideoAdapter)
        self.assertEqual(execution.repository.path,self.db)
        self.assertEqual(execution.backend_resolver.registry_digest,self.registry.registry_digest)
        self.assertFalse(any('provider-experiments' in p.name for p in self.root.glob('*jobs*')))

    def test_complete_i2v_archive_includes_original_facts_and_rejects_model_digest_change(self):
        import argparse
        import tarfile
        from scripts import k2_comfyui_runtime_evidence_archive as archive
        att=self.root/'archive-attestation.json';att.write_bytes(canonical(self.attestation))
        stats=self.root/'stats.json';stats.write_bytes(canonical(self.queue.adapter.client.json('GET','/system_stats')))
        objects=self.root/'objects.json';objects.write_bytes(canonical(self.queue.adapter.client.json('GET','/object_info')))
        models=self.root/'model-files.sha256';models.write_text(''.join(
            item['sha256']+'  '+item['name']+'\n' for item in self.attestation['facts']['modelFiles']))
        output=self.root/'runtime.tar.gz'
        args=argparse.Namespace(attestation=att,model_digests=models,system_stats=stats,object_info=objects,output=output)
        with patch.object(archive,'_arguments',return_value=args),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(archive.main(),0)
        with tarfile.open(output) as tar:
            archived=tar.extractfile('attestation.json').read()
            self.assertEqual(archived,att.read_bytes())
            manifest=json.loads(tar.extractfile('runtime-evidence-manifest.json').read())
            self.assertEqual(manifest['files']['attestation.json']['sha256'],sha256(archived).hexdigest())
        models.write_text(models.read_text().replace(self.attestation['facts']['modelFiles'][0]['sha256'],'f'*64))
        with patch.object(archive,'_arguments',return_value=args),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(archive.main(),2)
