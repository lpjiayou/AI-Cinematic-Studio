"""E2 result handoff regressions; first run against the frozen E1 baseline."""
from copy import deepcopy
from hashlib import sha256
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from services.v4_platform import InMemoryMediaJobAdapter, MediaJobCoordinator, SqliteMediaJobAdapter
from services.v4_platform.method_aware_execution import ContentAddressedSourceImages
from services.v5_core_os.episode_production import public
from services.v5_core_os.episode_production.foundation import _digest
from tests.unit import test_method_aware_media_m10_m11 as plans
from tests.unit import test_method_aware_worker_e1 as worker
from tests.unit.test_episode_production_k2 import WORKSPACE, run_command
from tests.unit.test_execution_method_planning_m8_m9 import plan_command
from tests.unit.test_narrative_currentness_m7 import seed_m7, validation_command, validation_profiles


class ResultFixture:
    """Real domain lineage and artifact bytes, with only a fake CPU adapter."""
    def __init__(self, case, *, sqlite=False, external=False, run=True):
        self.temp = tempfile.TemporaryDirectory()
        case.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = seed_m7()
        self.sqlite = sqlite
        self.sources = self.root / 'sources'
        self.sources.mkdir()
        image = self.sources / 'source.png'
        worker.media_file(image, image=True)
        self.source_digest = sha256(image.read_bytes()).hexdigest()
        image.rename(self.sources / (self.source_digest + '.png'))
        self.adapter = worker.FakeBoundAdapter()
        options = {}
        if external:
            self.adapter.adapter_identity = 'fake.external-adapter.v1'
            self.adapter.provenance = 'LIVE_PROVIDER'
            options = {'adapter_identity': self.adapter.adapter_identity,
                       'capability': 'fake.external-i2v.v1',
                       'backendType': 'EXTERNAL_PROVIDER_API', 'providerId': 'external-fake'}
        self.registry = plans.backend_registry_fixture(**options)
        self.jobs = SqliteMediaJobAdapter(self.root/'jobs.sqlite3') if sqlite else InMemoryMediaJobAdapter()
        self.coordinator = self.make_coordinator()
        self.boundary = self.make_boundary()
        created = self.boundary.create_run(run_command(
            self.seed['project'], self.seed['series'], self.seed['episode']))
        self.seed.update(boundary=self.boundary, run=created)
        validation = self.boundary.create_narrative_validation(validation_command(self.seed, key='e2-m7'))
        self.plan = self.boundary.create_execution_method_plan(plan_command(self.seed, validation, key='e2-m8'))
        admitted = plans.append_admitted_image(self.seed, self.plan, content_digest=self.source_digest)
        self.admitted = admitted
        self.input_plan = self.boundary.create_method_aware_input_plan(
            plans.m10_command(self.seed, self.plan, [admitted['binding']], key='e2-m10'))
        self.route = self.boundary.route_method_aware_videos(plans.m11_command(self.seed, self.input_plan, key='e2-m11'))
        self.request = self.route['videoGenerationRequests'][0]
        self.job_ref = self.route['queuedJobs'][0]['mediaJobRef']
        self.scope = {k:self.request[k] for k in ('workspaceRef','projectRef','seriesRef','episodeRef','productionRunRef')}
        self.run_ref = self.request['productionRunRef']
        self.evidence = plans.method_service(self.boundary).evidence_repository
        if run:
            self.done = self.coordinator.run_one(WORKSPACE, self.run_ref, self.job_ref, 'e2-worker')
            case.assertEqual(self.done['state'], 'SUCCEEDED')

    def make_coordinator(self):
        return MediaJobCoordinator(self.jobs, self.adapter, self.root/'artifacts',
            backend_resolver=self.registry, source_images=ContentAddressedSourceImages(self.sources),
            clock=lambda:'2026-09-06T07:45:00Z', ref_factory=lambda p:f'{p}-{uuid4().hex}')

    def make_boundary(self, *, restart=False):
        assembly = self.seed['assembly']
        kwargs = dict(project_boundary=assembly.project_context,
            series_episode_boundary=assembly.series_episode, series_planning_boundary=assembly.series_planning,
            script_studio_boundary=assembly.script_studio, method_aware_execution=self.coordinator,
            narrative_validation_profiles=validation_profiles())
        if self.sqlite:
            return public.create_local_development_boundary(self.root/'runs.sqlite3',
                **kwargs, initialize_if_missing=not restart)
        return public.create_in_memory_boundary(**kwargs)

    def reader(self):
        module = importlib.import_module('services.v4_platform.method_aware_results')
        return module.MethodAwareMediaJobResultReader(self.jobs, self.root/'artifacts')

    def result(self):
        return self.reader().require_verified_succeeded_result(WORKSPACE, self.run_ref, self.job_ref,
            self.request['generationRequestRef'], self.request['payloadDigest'],
            self.route['capabilityRegistryVersion'], self.route['capabilityRegistryDigest'])

    def command(self, *, key='e2-intake', result_digest=None):
        return {**self.scope, 'videoMethodRouteVersionRef':self.route['videoMethodRouteVersionRef'],
            'videoMethodRouteDigest':self.route['payloadDigest'], 'mediaJobRef':self.job_ref,
            'mediaJobResultDigest':result_digest or self.result()['payloadDigest'], 'idempotencyKey':key}

    def projection(self):
        return self.boundary.get_public_method_aware_video_jobs(
            WORKSPACE, self.scope['projectRef'], self.scope['seriesRef'], self.scope['episodeRef'],
            self.run_ref, self.route['videoMethodRouteVersionRef'])

    def records(self):
        return self.evidence.list_records(WORKSPACE, self.run_ref)


class ResultIntakeBaselineTests(unittest.TestCase):
    def setUp(self):
        self.f = ResultFixture(self)

    def test_succeeded_job_enters_existing_candidate_lifecycle_atomically(self):
        self.assertTrue(callable(getattr(self.f.boundary, 'ingest_public_method_aware_video_result', None)))
        before = len(self.f.records())
        result = self.f.boundary.ingest_public_method_aware_video_result(self.f.command())
        self.assertEqual(len(self.f.records())-before, 3)
        self.assertEqual({r['recordKind'] for r in self.f.records()[-3:]},
                         {'MethodAwareMediaJobResult','Candidate','TechnicalValidation'})
        self.assertEqual(result['candidate']['schemaVersion'], 'v5.method-aware-video-candidate.v1')
        self.assertEqual(result['technicalValidation']['lifecycleState'], 'TECHNICALLY_VERIFIED')
        self.assertFalse(result['publicationAllowed'])

    def test_status_projection_keeps_route_queue_snapshot_immutable(self):
        self.assertEqual(self.f.done['state'], 'SUCCEEDED')
        restored = self.f.boundary.get_method_aware_video_route(
            *[self.f.scope[k] for k in ('workspaceRef','projectRef','seriesRef','episodeRef','productionRunRef')],
            self.f.route['videoMethodRouteVersionRef'])
        self.assertEqual(restored['queuedJobs'][0]['queueState'], 'QUEUED')
        self.assertEqual(restored['payloadDigest'], self.f.route['payloadDigest'])
        projected = self.f.projection()
        self.assertEqual(projected['jobs'][0]['jobState'], 'SUCCEEDED')
        self.assertEqual(projected['jobs'][0]['candidateIntakeState'], 'READY_FOR_INTAKE')

    def test_safe_reader_does_not_expose_raw_job_or_execute_adapter(self):
        self.assertIn('internalPath', self.f.done['artifact'])
        self.assertIn('credentialSourceRef', self.f.done['backendBinding'])
        calls = self.f.adapter.calls
        value = self.f.reader().project_statuses(WORKSPACE, self.f.run_ref, [self.f.job_ref])
        serialized = json.dumps(value)
        for field in ('internalPath','leaseToken','credentialSourceRef','providerRequestRef','backendBinding'):
            self.assertNotIn(field, serialized)
        self.assertEqual(self.f.adapter.calls, calls)

    def test_legacy_intake_rejects_current_job_without_writes(self):
        before = self.f.records()
        with self.assertRaises(public.EpisodeProductionPublicError):
            self.f.boundary.record_real_video_candidates({'workspaceRef':WORKSPACE,
                'productionRunRef':self.f.run_ref, 'idempotencyKey':'e2-legacy-rejection'})
        self.assertEqual(self.f.records(), before)

    def test_changed_registry_blocks_intake_without_candidate_write(self):
        self.assertTrue(callable(getattr(self.f.boundary, 'ingest_public_method_aware_video_result', None)))
        command = self.f.command()
        self.f.coordinator.backend_resolver = plans.backend_registry_fixture(providerId='changed')
        before = self.f.records()
        with self.assertRaises(public.EpisodeProductionPublicError) as caught:
            self.f.boundary.ingest_public_method_aware_video_result(command)
        self.assertEqual(caught.exception.code, 'method_aware_job_route_stale')
        self.assertEqual(self.f.records(), before)

    def test_second_fake_backend_uses_same_candidate_schema(self):
        external = ResultFixture(self, external=True)
        self.assertTrue(callable(getattr(external.boundary, 'ingest_public_method_aware_video_result', None)))
        result = external.boundary.ingest_public_method_aware_video_result(external.command())
        candidate = result['candidate']
        self.assertEqual(candidate['schemaVersion'], 'v5.method-aware-video-candidate.v1')
        self.assertEqual(candidate['provenance'], 'AI_GENERATED')
        self.assertFalse({'providerId','modelId','adapterIdentity','consumedRealVideoRevision'} & candidate.keys())


class ResultReaderSafetyTests(unittest.TestCase):
    def setUp(self):
        self.f = ResultFixture(self)
        self.command = self.f.command()

    def assert_invalid_without_writes(self, code='method_aware_job_result_invalid'):
        before = self.f.records()
        jobs = deepcopy(self.f.jobs._jobs)
        calls = self.f.adapter.calls
        with self.assertRaises(public.EpisodeProductionPublicError) as caught:
            self.f.boundary.ingest_public_method_aware_video_result(self.command)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.f.records(), before)
        self.assertEqual(self.f.jobs._jobs, jobs)
        self.assertEqual(self.f.adapter.calls, calls)

    def test_durable_job_tampering_is_rejected(self):
        original = deepcopy(self.f.done)
        key = (WORKSPACE, self.f.run_ref, self.f.job_ref)
        mutations = {
            'byte-size':lambda j:j['artifact'].__setitem__('byteSize', j['artifact']['byteSize']+1),
            'sha256':lambda j:j['artifact'].__setitem__('sha256', '0'*64),
            'probe':lambda j:j['artifact']['probe']['streams'][0].__setitem__('width', 999),
            'request-digest':lambda j:j.__setitem__('requestDigest', '0'*64),
            'request-body':lambda j:j['request'].__setitem__('projectRef', 'foreign-project'),
            'envelope':lambda j:j['executionEnvelope']['outputConstraints'].__setitem__('width', 128),
            'backend':lambda j:j['backendBinding'].__setitem__('registryDigest', '0'*64),
            'attempt-binding':lambda j:j['attempts'][0]['backendBinding'].__setitem__('providerId', 'foreign'),
            'commit-intent':lambda j:j.__setitem__('artifactCommitIntent', {}),
            'lease':lambda j:j.__setitem__('lease', {'leaseToken':'secret'}),
            'attempt-ref':lambda j:j['artifact'].__setitem__('attemptRef', 'foreign-attempt'),
            'request-version':lambda j:j['artifact'].__setitem__('generationRequestVersionRef', 'foreign-version'),
            'publication':lambda j:j['artifact'].__setitem__('publicationAllowed', True),
            'execution-facts':lambda j:j['attempts'][0]['providerExecution'].__setitem__('providerRequestRef', 'other'),
            'fractional-size':lambda j:j['artifact'].__setitem__('byteSize', 12.5),
            'multiple-attempts':lambda j:j['attempts'].append(deepcopy(j['attempts'][0])),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                job = deepcopy(original); mutate(job); self.f.jobs._jobs[key] = job
                self.assert_invalid_without_writes()
        self.f.jobs._jobs[key] = original

    def test_artifact_bytes_must_be_rehashed_even_with_same_length(self):
        path = Path(self.f.done['artifact']['internalPath'])
        value = path.read_bytes(); path.write_bytes(bytes([value[0]^1])+value[1:])
        self.assert_invalid_without_writes()

    def test_artifact_symlink_and_outside_root_are_rejected(self):
        path = Path(self.f.done['artifact']['internalPath'])
        other = self.f.root/'outside.mp4'; path.rename(other); path.symlink_to(other)
        self.assert_invalid_without_writes()
        path.unlink()
        key = (WORKSPACE,self.f.run_ref,self.f.job_ref)
        self.f.jobs._jobs[key]['artifact']['internalPath'] = str(other)
        self.assert_invalid_without_writes()

    def test_missing_or_nonregular_artifact_is_rejected(self):
        path = Path(self.f.done['artifact']['internalPath']); path.unlink()
        self.assert_invalid_without_writes()
        path.mkdir(); self.assert_invalid_without_writes()

    def test_every_verification_uses_fresh_restricted_probe(self):
        from services.v4_platform import media_jobs
        original = media_jobs.subprocess.run
        with patch.object(media_jobs.subprocess, 'run', wraps=original) as probe:
            first = self.f.result(); second = self.f.result()
        self.assertEqual(first, second)
        self.assertEqual(probe.call_count, 2)
        for call in probe.call_args_list:
            args = call.args[0]
            self.assertEqual(args[args.index('-protocol_whitelist')+1], 'file,pipe')
            self.assertEqual(args[args.index('-f')+1], 'mov')

    def test_exact_expected_request_registry_and_scope_are_required(self):
        from services.v4_platform.method_aware_results import MethodAwareJobResultError
        args = [WORKSPACE,self.f.run_ref,self.f.job_ref,self.f.request['generationRequestRef'],
            self.f.request['payloadDigest'],self.f.route['capabilityRegistryVersion'],self.f.route['capabilityRegistryDigest']]
        for index in range(len(args)):
            with self.subTest(index=index):
                wrong = list(args); wrong[index] = '0'*64 if index in (4,6) else 'foreign'
                with self.assertRaises(MethodAwareJobResultError):
                    self.f.reader().require_verified_succeeded_result(*wrong)


class ResultStateTests(unittest.TestCase):
    def test_all_non_success_states_project_safely_and_cannot_be_intaken(self):
        f = ResultFixture(self, run=False)
        command = f.command(result_digest='0'*64)
        def check(state, code):
            before = f.records(); calls = f.adapter.calls
            value = f.projection()['jobs'][0]
            self.assertEqual(value['jobState'], state)
            self.assertIsNone(value['artifactSummary']); self.assertIsNone(value['resultDigest'])
            self.assertNotIn('leaseToken',json.dumps(value))
            with self.assertRaises(public.EpisodeProductionPublicError) as caught:
                f.boundary.ingest_public_method_aware_video_result(command)
            self.assertEqual(caught.exception.code,code)
            self.assertEqual(f.records(),before);self.assertEqual(f.adapter.calls,calls)
        check('QUEUED','method_aware_job_not_terminal')
        leased = f.coordinator.lease_job(WORKSPACE,f.run_ref,f.job_ref,'e2-worker')
        check('LEASED','method_aware_job_not_terminal')
        f.adapter.before_call = lambda envelope:check('RUNNING','method_aware_job_not_terminal')
        f.adapter.fail = RuntimeError('credential-value /private/provider-error')
        f.adapter.fail.code = 'REMOTE_SUBMISSION_INDETERMINATE'
        f.coordinator.run_leased(leased,'e2-worker')
        check('FAILED','method_aware_job_failed')
        projection = f.projection()['jobs'][0]
        self.assertEqual(projection['failureClass'],'REMOTE_SUBMISSION_INDETERMINATE')
        self.assertNotIn('credential-value',json.dumps(projection))
        cancelled = ResultFixture(self, run=False)
        cancelled.coordinator.cancel(WORKSPACE,cancelled.run_ref,cancelled.job_ref)
        self.assertEqual(cancelled.projection()['jobs'][0]['candidateIntakeState'],'CANCELLED')
        with self.assertRaises(public.EpisodeProductionPublicError) as caught:
            cancelled.boundary.ingest_public_method_aware_video_result(cancelled.command(result_digest='0'*64))
        self.assertEqual(caught.exception.code,'method_aware_job_cancelled')


class ResultCurrentnessAndAtomicTests(unittest.TestCase):
    def setUp(self):
        self.f = ResultFixture(self)
        self.command = self.f.command()

    def ingest(self, command=None):
        return self.f.boundary.ingest_public_method_aware_video_result(command or self.command)

    def reject(self, command, code):
        before=self.f.records(); jobs=deepcopy(self.f.jobs._jobs)
        with self.assertRaises(public.EpisodeProductionPublicError) as caught:
            self.ingest(command)
        self.assertEqual(caught.exception.code,code)
        self.assertEqual(self.f.records(),before);self.assertEqual(self.f.jobs._jobs,jobs)

    def test_foreign_scopes_and_unreferenced_job_are_concealed(self):
        for field in self.f.scope:
            with self.subTest(field=field):
                self.reject({**self.command,field:'foreign'},'method_aware_job_scope_mismatch')
        self.reject({**self.command,'mediaJobRef':'foreign-job'},'method_aware_job_not_found')
        self.reject({**self.command,'mediaJobResultDigest':'0'*64},'method_aware_job_result_digest_mismatch')

    def test_stale_route_token_has_no_writes(self):
        self.reject({**self.command,'videoMethodRouteDigest':'0'*64},'method_aware_job_route_stale')

    def test_new_input_plan_stales_old_route(self):
        self.f.boundary.create_method_aware_input_plan(plans.m10_command(
            self.f.seed,self.f.plan,[self.f.admitted['binding']],key='e2-new-input'))
        self.reject(self.command,'method_aware_job_route_stale')
        self.assertEqual(self.f.projection()['jobs'][0]['candidateIntakeState'],'BLOCKED_STALE_ROUTE')

    def test_new_method_plan_stales_old_route(self):
        validation=self.f.boundary.create_narrative_validation(validation_command(self.f.seed,key='e2-next-m7'))
        self.f.boundary.create_execution_method_plan(plan_command(self.f.seed,validation,key='e2-next-m8'))
        self.reject(self.command,'method_aware_job_route_stale')

    def test_superseded_source_asset_stales_old_route(self):
        plans.append_admitted_image(self.f.seed,self.f.plan,suffix='v2',
            asset_ref=self.f.admitted['asset']['assetRef'],version=2,content_digest=self.f.source_digest)
        self.reject(self.command,'method_aware_job_route_stale')

    def test_same_key_replay_and_different_key_reuse_have_no_new_records(self):
        result=self.ingest(); records=self.f.records()
        for key in (self.command['idempotencyKey'],'another-client-key'):
            replay=self.ingest({**self.command,'idempotencyKey':key})
            self.assertTrue(replay['idempotentReplay'])
            for k in ('resultReceipt','candidate','technicalValidation'):self.assertEqual(replay[k],result[k])
        self.assertEqual(self.f.records(),records)
        lifecycle=result['candidateLifecycle']
        self.assertEqual(lifecycle['technicalState'],'TECHNICALLY_VERIFIED')
        self.assertEqual(lifecycle['visualQcState'],'NOT_STARTED')
        self.assertEqual(lifecycle['selectionState'],'UNSELECTED')
        self.assertEqual(lifecycle['admissionState'],'NOT_ADMITTED')
        self.assertIsNone(lifecycle['assetVersionRef'])
        self.assertEqual(self.f.projection()['jobs'][0]['candidateIntakeState'],'RECORDED')

    def test_changed_key_content_and_job_result_conflicts(self):
        self.ingest()
        self.reject({**self.command,'mediaJobRef':'other-job'},'idempotency_conflict')
        self.reject({**self.command,'mediaJobResultDigest':'0'*64},'idempotency_conflict')
        self.reject({**self.command,'idempotencyKey':'different-key','mediaJobResultDigest':'0'*64},
                    'method_aware_job_result_conflict')

    def test_concurrent_double_submit_commits_one_complete_batch(self):
        before=len(self.f.records()); barrier=Barrier(2); original=self.f.evidence.append_records
        def race(records,**kwargs):
            self.assertEqual(len(records),3)
            self.assertIsNotNone(kwargs.get('expected_record_journal_head'))
            barrier.wait(timeout=10)
            return original(records,**kwargs)
        with patch.object(self.f.evidence,'append_records',side_effect=race), ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(self.ingest,{**self.command,'idempotencyKey':key}) for key in ('race-a','race-b')]
            results=[f.result(timeout=20) for f in futures]
        self.assertEqual(len(self.f.records())-before,3)
        self.assertEqual(results[0]['candidate'],results[1]['candidate'])
        self.assertEqual(sorted(r['idempotentReplay'] for r in results),[False,True])

    def test_newer_job_for_same_slot_stales_previous_candidate_without_rewrite(self):
        old=self.ingest(); original=deepcopy(self.f.records()[-3:])
        self.f.input_plan=self.f.boundary.create_method_aware_input_plan(plans.m10_command(
            self.f.seed,self.f.plan,[self.f.admitted['binding']],key='e2-new-input'))
        self.f.route=self.f.boundary.route_method_aware_videos(plans.m11_command(self.f.seed,self.f.input_plan,key='e2-new-route'))
        self.f.request=self.f.route['videoGenerationRequests'][0]
        self.f.job_ref=self.f.route['queuedJobs'][0]['mediaJobRef']
        self.f.coordinator.run_one(WORKSPACE,self.f.run_ref,self.f.job_ref,'e2-worker')
        new=self.ingest(self.f.command(key='e2-next-result'))
        self.assertNotEqual(old['candidate']['candidateRef'],new['candidate']['candidateRef'])
        lifecycle=plans.method_service(self.f.boundary).candidate_review.get_projection(WORKSPACE,self.f.run_ref)
        old_item=next(i for i in lifecycle['candidates'] if i['candidateRef']==old['candidate']['candidateRef'])
        self.assertEqual(old_item['applicabilityState'],'STALE')
        self.assertEqual(new['candidateLifecycle']['applicabilityState'],'CURRENT')
        for record in original:self.assertIn(record,self.f.records())
