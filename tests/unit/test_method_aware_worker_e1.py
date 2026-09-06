"""E1 safety regressions, first executed against the unchanged frozen baseline."""
import copy
import importlib.util
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.v4_platform import InMemoryMediaJobAdapter, MediaJobCoordinator
from services.v5_core_os.episode_production import public
from services.v5_core_os.episode_production.foundation import _digest
from tests.unit import test_method_aware_media_m10_m11 as fixtures
from tests.unit.test_method_aware_media_m10_m11 import (
    append_admitted_image, m10_command, m11_command,
    method_service,
)
from scripts.k2_comfyui_runtime_evidence_archive import _validate_attestation
from services.v4_platform.comfyui import REQUIRED_NODES


def ready_route(case):
    admitted = append_admitted_image(case.seed, case.execution_plan)
    plan = case.seed['boundary'].create_method_aware_input_plan(
        m10_command(case.seed, case.execution_plan, [admitted['binding']]))
    return case.seed['boundary'].route_method_aware_videos(m11_command(case.seed, plan))


def i2v_attestation():
    facts = {
        'providerId': 'fake-provider', 'modelId': 'fake-model', 'region': 'test',
        'endpointClass': 'loopback-test', 'comfyuiVersion': 'test',
        'pythonVersion': 'test', 'pytorchVersion': 'test', 'deviceName': 'fake-cuda',
        'deviceType': 'cuda', 'vramTotalBytes': 100,
        'requiredNodes': [*REQUIRED_NODES, 'LoadImage'],
        'startImageCapability': 'LOAD_IMAGE_TO_WAN_START_IMAGE_VERIFIED',
        'modelFiles': [{'role': role, 'name': role+'.bin', 'sha256': '1'*64}
                       for role in ('UNET','TEXT_ENCODER','VAE')],
        'objectInfoDigest': '2'*64,
        'modelDigestVerification': 'LOCAL_FILE_SHA256_VERIFIED',
    }
    value = {'schemaVersion': 'v4.comfyui-runtime-attestation.v2',
             'capabilityMode': 'IMAGE_TO_VIDEO', 'attestationRef': 'fake-attestation',
             'observedAt': '2026-09-06T00:00:00Z', 'facts': facts,
             'factsDigest': _digest(facts), 'authorityState': 'TECHNICAL_EVIDENCE_ONLY',
             'publicationAllowed': False}
    value['payloadDigest'] = _digest(value)
    return value


class WorkerSeamBaselineRegressions(unittest.TestCase):
    def setUp(self):
        # Reuse the existing public domain fixture, not a new production authority.
        self.case = fixtures.MethodAwareMediaTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_production_worker_entrypoint_exists(self):
        self.assertIsNotNone(importlib.util.find_spec(
            'services.v4_platform.method_aware_worker'))

    def test_unique_request_bridge_exists(self):
        self.assertIsNotNone(importlib.util.find_spec(
            'services.v4_platform.method_aware_execution'))

    def test_exact_job_claim_does_not_require_batch_scope_execution(self):
        self.assertTrue(callable(getattr(self.case.coordinator, 'lease_job', None)))
        self.assertTrue(callable(getattr(self.case.coordinator, 'run_one', None)))

    def test_default_composition_has_a_separate_method_seam_injection(self):
        self.assertIn('method_aware_execution', inspect.signature(
            public.create_local_development_boundary).parameters)
        self.assertIn('create_method_aware_coordinator_from_environment',
                      vars(public))

    def test_current_request_failure_is_terminal_before_adapter(self):
        route = ready_route(self.case)
        request = route['videoGenerationRequests'][0]
        queue = self.case.coordinator
        leased = queue.lease_job(request['workspaceRef'], request['productionRunRef'],
                                  route['queuedJobs'][0]['mediaJobRef'], 'explicit-worker')
        caught = None
        try:
            queue.run_leased(leased, 'explicit-worker')
        except Exception as exc:
            caught = exc
        stored = queue.repository.get(request['workspaceRef'],
                                      request['productionRunRef'], leased['jobRef'])
        self.assertEqual(self.case.adapter.generate_calls, 0)
        self.assertEqual(stored['state'], 'FAILED', repr(caught))
        self.assertEqual(stored['attempts'][-1]['failureClass'],
                         'PRE_EXECUTION_VALIDATION_FAILED')

    def test_new_method_job_binds_backend_before_worker_call(self):
        route = ready_route(self.case)
        request = route['videoGenerationRequests'][0]
        stored = self.case.coordinator.list_jobs(request['workspaceRef'],
                                                request['productionRunRef'])[0]
        self.assertEqual(stored['schemaVersion'], 'v4.media-job.v3')
        self.assertIn('backendBinding', stored)
        self.assertEqual(stored['backendBinding']['fallbackAllowed'], False)
        self.assertEqual(self.case.adapter.generate_calls, 0)

    def test_second_backend_route_does_not_use_v5_wan_constant(self):
        self.case.adapter.adapter_identity = 'fake.second-i2v-adapter.v1'
        # A complete resolver is injected by the E1 fixture; the frozen baseline
        # instead consults its V5 Wan constant and fails this public route.
        configure = getattr(self.case, 'configure_backend', None)
        if configure is not None:
            configure(adapter_identity=self.case.adapter.adapter_identity,
                      capability='fake.second-i2v-capability.v1')
        route = ready_route(self.case)
        queued = [r for r in route['routes'] if r['routingState']=='QUEUED_EXISTING_MEDIA_JOB']
        self.assertEqual(queued[0]['adapterIdentity'], 'fake.second-i2v-adapter.v1')
        self.assertEqual(self.case.adapter.generate_calls, 0)

    def test_i2v_archive_preserves_complete_versioned_facts(self):
        value = i2v_attestation()
        before = copy.deepcopy(value)
        facts = _validate_attestation(value)
        self.assertEqual(value, before)
        self.assertIn('LoadImage', facts['requiredNodes'])
        self.assertEqual(facts['startImageCapability'],
                         'LOAD_IMAGE_TO_WAN_START_IMAGE_VERIFIED')

    def test_scope_batch_is_not_the_exact_worker_entrypoint(self):
        # The regression is an actual public worker contract, not permission to
        # change legacy execute_batch semantics.
        operation = getattr(self.case.coordinator, 'run_one', None)
        self.assertTrue(callable(operation))
        self.assertIn('job_ref', inspect.signature(operation).parameters)
        with patch.object(self.case.coordinator, 'execute_batch',
                          side_effect=AssertionError('whole queue is prohibited')):
            with self.assertRaises(Exception):
                operation('workspace-missing', 'run-missing', 'job-missing',
                          'explicit-worker')

    def test_changed_registry_makes_old_route_stale_without_rewriting_jobs(self):
        route=ready_route(self.case)
        request=route['videoGenerationRequests'][0]
        before=self.case.coordinator.list_jobs(request['workspaceRef'],request['productionRunRef'])
        self.case.configure_backend(providerId='new-provider')
        value=self.case.seed['boundary'].get_method_aware_video_route(
            request['workspaceRef'],request['projectRef'],request['seriesRef'],request['episodeRef'],
            request['productionRunRef'],route['videoMethodRouteVersionRef'])
        self.assertEqual(value['currentness'],'STALE')
        self.assertEqual(value['payloadDigest'],route['payloadDigest'])
        self.assertEqual(self.case.coordinator.list_jobs(request['workspaceRef'],request['productionRunRef']),before)

    def test_second_external_fake_backend_needs_no_v5_change(self):
        self.case.adapter.adapter_identity='fake.external-adapter.v1'
        self.case.adapter.provenance='LIVE_PROVIDER'
        self.case.configure_backend(adapter_identity=self.case.adapter.adapter_identity,
            capability='fake.external-i2v.v1',backendType='EXTERNAL_PROVIDER_API')
        route=ready_route(self.case)
        self.assertEqual(route['videoGenerationRequests'][0]['executionMode'],'EXTERNAL_PROVIDER_API')
        self.assertEqual(route['queuedJobCount'],1)
        self.assertFalse(route['wanFallbackUsed'])
        self.assertEqual(self.case.adapter.generate_calls,0)

    def test_browser_cannot_supply_backend_or_profile_authority(self):
        admitted=append_admitted_image(self.case.seed,self.case.execution_plan)
        plan=self.case.seed['boundary'].create_method_aware_input_plan(
            m10_command(self.case.seed,self.case.execution_plan,[admitted['binding']]))
        for field in ('backendRef','providerId','modelId','backendProfileRef','backendBinding'):
            command=m11_command(self.case.seed,plan);command[field]='browser-value'
            with self.assertRaises(fixtures.EpisodeProductionPublicError):
                self.case.seed['boundary'].route_method_aware_videos(command)
        self.assertEqual(self.case.coordinator.list_jobs(plan['workspaceRef'],plan['productionRunRef']),[])


# Fixtures below exercise real queue persistence and ffprobe/FFmpeg media bytes;
# all generation is deterministic fake execution with no external backend.
import json
import os
import signal
import subprocess
from hashlib import sha256
from uuid import uuid4
from services.v4_platform.backend_registry import (
    BackendRegistry, BackendUnavailableError, BackendValidationError, digest,
    attempt_binding, strict_load,
)
from services.v4_platform.method_aware_execution import (
    ContentAddressedSourceImages, MethodAwareExecutionEnvelopeBuilder,
    validate_envelope, validate_execution_result,
)
from services.v4_platform.media_jobs import MediaAdapterResult, MediaJobStateError
from services.v4_platform.method_aware_worker import (
    create_method_aware_coordinator_from_environment, main as worker_main,
    WorkerTerminated,
)


def media_file(path, *, image=False, width=64, height=64, frames=8, fps=24):
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
        f'color=c=0x203040:s={width}x{height}:r={fps}', '-frames:v', '1' if image else str(frames),
        *([] if image else ['-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p']),
        '-y', str(path)], check=True, capture_output=True, timeout=30)


def semantic_request_template():
    case = fixtures.MethodAwareMediaTests()
    case.setUp()
    try:
        route = ready_route(case)
        original = route['videoGenerationRequests'][0]
        job = case.coordinator.list_jobs(original['workspaceRef'], original['productionRunRef'])[0]
        return copy.deepcopy(original), copy.deepcopy(job['executionContext'])
    finally:
        case.doCleanups()


class FakeBoundAdapter:
    adapter_identity = 'v4.comfyui-wan22-image-to-video.v1'
    provenance = 'SELF_HOSTED_AI_GENERATED'

    def __init__(self):
        self.calls = 0
        self.before_call = None
        self.fail = None
        self.change_result = None

    def validate_method_aware_envelope(self, envelope):
        validate_envelope(envelope)

    def generate(self, envelope, path):
        self.calls += 1
        if self.before_call:
            self.before_call(envelope)
        if self.fail:
            raise self.fail
        output = envelope['outputConstraints']
        media_file(path, width=output['width'], height=output['height'],
                   frames=output['durationFrames'], fps=output['frameRate'])
        binding = envelope['backendBinding']
        evidence = {'adapterTestMode': 'FAKE_CPU_BYTES', 'requestCount': self.calls}
        execution = {'schemaVersion': 'v4.method-aware-execution-result.v1',
            'backendBindingDigest': digest(binding),
            **{k:binding[k] for k in ('providerId','modelId','region','endpointClass',
                'adapterIdentity','costCurrency','runtimeAttestationRef','runtimeAttestationDigest')},
            'providerRequestRef': 'fake-request-1', 'costMinor': 0,
            'executionDevice': 'CPU_TEST_FIXTURE', 'gpuUsed': False,
            'executionEvidence': evidence, 'executionEvidenceDigest': digest(evidence)}
        if self.change_result:
            self.change_result(execution)
        return MediaAdapterResult(path, execution)


class ExactWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template, cls.context_template = semantic_request_template()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = self.root/'sources'; self.sources.mkdir()
        image = self.sources/'source.png'
        media_file(image, image=True)
        content = sha256(image.read_bytes()).hexdigest()
        image.rename(self.sources/(content+'.png'))
        self.registry = fixtures.backend_registry_fixture()
        self.adapter = FakeBoundAdapter()
        self.repo = InMemoryMediaJobAdapter()
        self.now = '2026-09-06T00:00:00Z'
        self.queue = self.coordinator()
        self.request = copy.deepcopy(self.template)
        self.request['sourceImageContentDigest'] = content
        self.request['frameRange'] = {'startFrameInclusive':0,'endFrameExclusive':8}
        self.request['payloadDigest'] = digest({k:v for k,v in self.request.items() if k!='payloadDigest'})
        self.context = copy.deepcopy(self.context_template)
        self.context['outputConstraints'].update(width=64,height=64,durationFrames=8,frameRate=24)
        self.binding = self.registry.resolve('MICRO_MOTION','SINGLE_ANCHOR_I2V',
            ['ACTION_READY_ANCHOR'], self.context['outputConstraints'])

    def coordinator(self):
        return MediaJobCoordinator(self.repo, self.adapter, self.root/'artifacts',
            ref_factory=lambda prefix: f'{prefix}-{uuid4().hex}', clock=lambda:self.now,
            backend_resolver=self.registry, source_images=ContentAddressedSourceImages(self.sources))

    def dispatch(self, *, key='target', request=None):
        return self.queue.dispatch(request or self.request, idempotency_key=key,
            backend_binding=self.binding, execution_context=self.context)[0]

    def run_job(self, job):
        return self.queue.run_one(job['workspaceRef'],job['productionRunRef'],job['jobRef'],'worker-instance-1')

    def envelope(self):
        return MethodAwareExecutionEnvelopeBuilder().build(self.request,
            self.queue.source_images.resolve(self.request), self.binding,
            self.registry.profile(self.binding), self.context)

    def test_exact_job_success_binding_before_call_and_other_job_untouched(self):
        first=self.dispatch(); other=self.dispatch(key='other')
        before=copy.deepcopy(other)
        def observed(envelope):
            stored=self.repo.get(first['workspaceRef'],first['productionRunRef'],first['jobRef'])
            self.assertEqual(stored['state'],'RUNNING')
            self.assertEqual(stored['executionEnvelope'],envelope)
            self.assertEqual(stored['attempts'][0]['backendBinding'],attempt_binding(self.binding,'worker-instance-1'))
        self.adapter.before_call=observed
        with patch.object(self.queue,'execute_batch',side_effect=AssertionError('batch forbidden')):
            done=self.run_job(first)
        self.assertEqual(done['state'],'SUCCEEDED')
        self.assertEqual(self.adapter.calls,1)
        self.assertFalse(done['artifact']['gpuUsed'])
        self.assertTrue(Path(done['artifact']['internalPath']).is_file())
        self.assertEqual(self.repo.get(other['workspaceRef'],other['productionRunRef'],other['jobRef']),before)
        self.assertEqual(self.run_job(first),done)
        self.assertEqual(self.adapter.calls,1)

    def test_bound_jobs_cannot_be_consumed_by_batch_or_lease_next(self):
        job=self.dispatch()
        self.assertIsNone(self.queue.lease_next(job['workspaceRef'],job['productionRunRef'],'legacy-worker'))
        self.assertEqual(self.repo.get(job['workspaceRef'],job['productionRunRef'],job['jobRef']),job)

    def test_missing_worker_fields_fail_before_running_or_adapter(self):
        base=self.envelope()
        mutations = [lambda e:e['outputConstraints'].pop('mediaKind'),
            lambda e:e['outputConstraints'].pop('mediaType'), lambda e:e['sourceAsset'].pop('width'),
            lambda e:e['backendBinding'].pop('backendProfileDigest'),
            lambda e:e['backendBinding'].pop('runtimeAttestationDigest'),
            lambda e:e['sourceAsset'].update(width=65),
            lambda e:e['outputConstraints'].update(height=64.5),
            lambda e:e['semanticIntent'].update(unknown=True)]
        for index,change in enumerate(mutations):
            with self.subTest(index=index):
                broken=copy.deepcopy(base);change(broken)
                broken['envelopeDigest']=digest({k:v for k,v in broken.items() if k!='envelopeDigest'})
                job=self.dispatch(key=f'broken-{index}')
                with patch.object(self.queue.envelope_builder,'build',return_value=broken):
                    done=self.run_job(job)
                self.assertEqual(done['state'],'FAILED')
                self.assertEqual(done['attempts'][0]['failureClass'],'PRE_EXECUTION_VALIDATION_FAILED')
                self.assertIsNone(done['executionEnvelope'])
        self.assertEqual(self.adapter.calls,0)

    def test_source_missing_changed_bytes_and_symlink_are_preflight_failures(self):
        path=self.queue.source_images.path_for(self.request); original=path.read_bytes()
        for mode in ('missing','changed','symlink'):
            with self.subTest(mode=mode):
                path.unlink(missing_ok=True)
                if mode=='changed':path.write_bytes(b'changed')
                if mode=='symlink':
                    elsewhere=self.root/'elsewhere.png';elsewhere.write_bytes(original);path.symlink_to(elsewhere)
                done=self.run_job(self.dispatch(key=mode))
                self.assertEqual(done['state'],'FAILED')
                self.assertEqual(done['attempts'][0]['failureClass'],'PRE_EXECUTION_VALIDATION_FAILED')
                self.assertEqual(self.adapter.calls,0)

    def test_adapter_cannot_change_provider_model_or_cost_binding(self):
        for key,value in (('providerId','other'),('modelId','other'),('costMinor',11),('runtimeAttestationDigest','2'*64)):
            with self.subTest(field=key):
                self.adapter.change_result=lambda e:e.update({key:value})
                done=self.run_job(self.dispatch(key=key))
                self.assertEqual(done['state'],'FAILED');self.assertIsNone(done['artifact'])
                self.assertEqual(done['attempts'][0]['backendBinding']['providerId'],self.binding['providerId'])
        self.assertEqual(self.adapter.calls,4)

    def test_binding_immutable_and_worker_mismatch_rejected(self):
        job=self.dispatch()
        altered=copy.deepcopy(job);altered['backendBinding']['providerId']='other'
        with self.assertRaises(Exception):self.repo.save(altered,job['revision'])
        self.adapter.adapter_identity='other-adapter'
        with self.assertRaises(BackendValidationError):self.run_job(job)
        self.assertEqual(self.repo.get(job['workspaceRef'],job['productionRunRef'],job['jobRef'])['state'],'QUEUED')
        self.assertEqual(self.adapter.calls,0)

    def test_adapter_failure_is_terminal_without_retry(self):
        self.adapter.fail=RuntimeError('fake failure')
        job=self.dispatch();done=self.run_job(job)
        self.assertEqual(done['state'],'FAILED')
        self.assertTrue(done['attempts'][0]['nonRetryable'])
        with self.assertRaises(MediaJobStateError):self.queue.retry(job['workspaceRef'],job['productionRunRef'],job['jobRef'])
        self.assertEqual(self.run_job(job),done);self.assertEqual(self.adapter.calls,1)

    def test_unknown_submission_crash_restart_never_resubmits(self):
        class SimulatedProcessDeath(BaseException):pass
        self.adapter.fail=SimulatedProcessDeath()
        job=self.dispatch()
        with self.assertRaises(SimulatedProcessDeath):self.run_job(job)
        self.now='2026-09-06T00:02:00Z'
        restarted=self.coordinator()
        done=restarted.run_one(job['workspaceRef'],job['productionRunRef'],job['jobRef'],'worker-instance-2')
        self.assertEqual(done['state'],'FAILED')
        self.assertEqual(done['attempts'][0]['failureClass'],'REMOTE_SUBMISSION_INDETERMINATE')
        self.assertEqual(self.adapter.calls,1)

    def test_sigterm_during_adapter_call_no_second_attempt(self):
        job=self.dispatch()
        self.adapter.before_call=lambda _:os.kill(os.getpid(),signal.SIGTERM)
        db=self.root/'queue.sqlite3';db.touch()
        args=['run-one','--job-ref',job['jobRef'],'--workspace-ref',job['workspaceRef'],
            '--production-run-ref',job['productionRunRef'],'--worker-ref','worker-instance-1',
            '--queue-db',str(db),'--artifact-root',str(self.root/'artifacts'),
            '--backend-registry-manifest','unused-test-manifest','--backend-registry-sha256','1'*64,'--max-attempts','1']
        with patch('services.v4_platform.method_aware_worker.SqliteMediaJobAdapter',return_value=self.repo), \
             patch('services.v4_platform.method_aware_worker.create_method_aware_coordinator_from_environment',return_value=self.queue):
            self.assertEqual(worker_main(args,environ={}),1)
        done=self.run_job(job)
        self.assertEqual(done['attempts'][0]['failureClass'],'WORKER_TERMINATED_NO_RETRY')
        self.assertEqual(self.adapter.calls,1)

    def test_resolver_registry_digest_methods_resource_shape_and_no_secret(self):
        self.assertEqual(self.registry.registry_digest,fixtures.backend_registry_fixture().registry_digest)
        for pair in [('CONTACT_ACTION','CONTACT_CONDITIONED_VIDEO'),('GAIT_LOCOMOTION','POSE_OR_TRAJECTORY_CONDITIONED_VIDEO'),('MICRO_MOTION','TEXT_TO_VIDEO')]:
            with self.assertRaises(BackendUnavailableError):self.registry.resolve(*pair,['ACTION_READY_ANCHOR'],self.context['outputConstraints'])
        for count in (0,1,4):
            alternative=fixtures.backend_registry_fixture(backendType='CPU_DETERMINISTIC' if count==0 else 'SELF_HOSTED_MULTI_GPU_WORKER_POOL',
                resourceShape={'gpuCount':count,'minimumVramPerGpu':8,'minimumTotalVram':32,
                               'distributionMode':'NONE' if count==0 else 'HORIZONTAL_INDEPENDENT_WORKERS'})
            self.assertNotEqual(alternative.registry_digest,self.registry.registry_digest)
        self.assertNotIn('A100',json.dumps(self.dispatch()))
        with patch.dict(os.environ,{'TEST_CREDENTIAL':'private-test-secret'}):
            self.assertNotIn('private-test-secret',json.dumps(self.dispatch(key='secret-test')))

    def test_envelope_closed_json_strict_integer_nonfinite_and_profile_binding(self):
        valid=self.envelope();self.assertEqual(validate_envelope(valid,self.request),valid)
        for mutate in (lambda v:v['sourceAsset'].update(width=64.1),lambda v:v.update(extra=1),
                       lambda v:v['outputConstraints'].update(frameRate=True),
                       lambda v:v['sourceAsset'].update(contentDigest='2'*64)):
            bad=copy.deepcopy(valid);mutate(bad);bad['envelopeDigest']=digest({k:v for k,v in bad.items() if k!='envelopeDigest'})
            with self.assertRaises(BackendValidationError):validate_envelope(bad,self.request)
        for value in (float('nan'),float('inf'),-float('inf')):
            bad=copy.deepcopy(valid);bad['outputConstraints']['width']=value
            with self.assertRaises(BackendValidationError):validate_envelope(bad)
        with self.assertRaises(BackendValidationError):MethodAwareExecutionEnvelopeBuilder().build(
            self.request,valid['sourceAsset'],self.binding,{},self.context)
        for raw in (b'{"a":1,"a":2}',b'{"value":NaN}',b'{"value":1e999}'):
            with self.assertRaises(BackendValidationError):strict_load(raw)

    def test_unconfigured_composition_is_unavailable_and_shares_repository(self):
        queue=create_method_aware_coordinator_from_environment(self.repo,self.root/'unconfigured',environ={})
        self.assertIs(queue.repository,self.repo)
        self.assertEqual(queue.adapter.adapter_identity,'v4.method-aware-unavailable.v1')
        with self.assertRaises(BackendUnavailableError):queue.backend_resolver.resolve(
            'MICRO_MOTION','SINGLE_ANCHOR_I2V',['ACTION_READY_ANCHOR'],self.context['outputConstraints'])
        self.assertEqual(self.repo.list(self.request['workspaceRef'],self.request['productionRunRef']),[])


class VersionedAttestationArchiveTests(unittest.TestCase):
    def test_exact_i2v_and_unchanged_v1_t2v(self):
        i2v=i2v_attestation();before=copy.deepcopy(i2v)
        self.assertIn('LoadImage',_validate_attestation(i2v)['requiredNodes'])
        self.assertEqual(i2v,before)
        t2v=copy.deepcopy(i2v);t2v['schemaVersion']='v4.comfyui-runtime-attestation.v1'
        t2v.pop('capabilityMode');t2v['facts'].pop('startImageCapability')
        t2v['facts']['requiredNodes']=list(REQUIRED_NODES)
        t2v['factsDigest']=digest(t2v['facts']);t2v['payloadDigest']=digest({k:v for k,v in t2v.items() if k!='payloadDigest'})
        raw=json.dumps(t2v);self.assertEqual(_validate_attestation(t2v),t2v['facts'])
        self.assertEqual(json.dumps(t2v),raw)

    def test_i2v_missing_capability_and_unknown_fields_cannot_be_stripped(self):
        mutations=[lambda v:v['facts']['requiredNodes'].remove('LoadImage'),
            lambda v:v['facts'].pop('startImageCapability'), lambda v:v['facts'].update(extra='unknown'),
            lambda v:v.update(extra='unknown'), lambda v:v.update(capabilityMode='TEXT_TO_VIDEO'),
            lambda v:v['facts']['modelFiles'][0].update(sha256='not-a-digest')]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                bad=i2v_attestation();mutate(bad)
                bad['factsDigest']=digest(bad['facts']);bad['payloadDigest']=digest({k:v for k,v in bad.items() if k!='payloadDigest'})
                before=copy.deepcopy(bad)
                with self.assertRaises(ValueError):_validate_attestation(bad)
                self.assertEqual(bad,before)

    def test_changed_model_digest_and_full_fact_digest_fail_closed(self):
        bad=i2v_attestation();bad['facts']['modelFiles'][0]['sha256']='2'*64
        with self.assertRaises(ValueError):_validate_attestation(bad)
        bad=i2v_attestation();bad['facts']['deviceName']='different-device'
        with self.assertRaises(ValueError):_validate_attestation(bad)

    def test_object_info_requires_both_load_image_and_start_image(self):
        from scripts.k2_comfyui_runtime_evidence_archive import _validate_object_info
        facts=i2v_attestation()['facts']
        objects={node:{} for node in facts['requiredNodes']}
        objects['LoadImage']={'input':{'required':{'image':['STRING']}}}
        objects['Wan22ImageToVideoLatent']={'input':{'optional':{'start_image':['IMAGE']}}}
        facts['objectInfoDigest']=digest(objects)
        _validate_object_info(objects,facts)
        for name in ('LoadImage','Wan22ImageToVideoLatent'):
            bad=copy.deepcopy(objects);bad[name]={};facts['objectInfoDigest']=digest(bad)
            with self.assertRaises(ValueError):_validate_object_info(bad,facts)
