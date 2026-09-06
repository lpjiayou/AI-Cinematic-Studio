"""Only the two authorized M11 result resources extend the public contract."""
import unittest
import ast
import inspect
from copy import deepcopy
from apps.creator_workspace_mvp import public_contract, server
from services.v4_platform import method_aware_results
from services.v5_core_os.episode_production import method_aware_result_intake, public
from services.v5_core_os.episode_production.foundation import _digest
from tests.unit.test_method_aware_job_result_intake_e2 import ResultFixture


class MethodAwareResultPublicContractTests(unittest.TestCase):
    def test_two_provider_neutral_resources_are_registered(self):
        m11 = next(v for v in public_contract.CAPABILITY_PROJECTION if v['id']=='M11')
        for resource in ('method-aware-video-jobs','method-aware-video-candidates'):
            self.assertIn(resource, server.EPISODE_PRODUCTION_SUBRESOURCES)
            self.assertIn('episode-production-runs/'+resource, m11['publicResources'])

    def test_new_v5_handoff_has_no_provider_branch_or_worker_write_port(self):
        source=inspect.getsource(method_aware_result_intake)
        for token in ('ComfyUI','A100','providerId','modelId','endpointClass','gpuCount','/prompt','/history','/view'):
            self.assertNotIn(token,source)
        tree=ast.parse(inspect.getsource(method_aware_results.MethodAwareMediaJobResultReader))
        calls={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
        for name in ('dispatch','run_one','run_leased','lease_job','cancel','save','create','generate','unlink','mkdir'):
            self.assertNotIn(name,calls)
        for factory in (public.create_in_memory_boundary,public.create_local_development_boundary):
            self.assertIn('method_aware_result_reader',inspect.signature(factory).parameters)
        environment=inspect.getsource(public.create_local_development_boundary_from_environment)
        self.assertIn('MethodAwareMediaJobResultReader(job_repository, artifact_root)',environment)

    def test_self_hosted_and_external_results_have_identical_closed_neutral_schemas(self):
        result_sets=[]
        for external in (False,True):
            f=ResultFixture(self,external=external)
            result=f.boundary.ingest_public_method_aware_video_result(f.command())
            result_sets.append({k:set(result[k]) for k in ('candidate','resultReceipt','technicalValidation')})
            for name in ('candidate','resultReceipt','technicalValidation'):
                value=deepcopy(result[name]);digest=value.pop('payloadDigest')
                self.assertEqual(digest,_digest(value))
            self.assertEqual(result['candidate']['provenance'],'AI_GENERATED')
            receipt=result['resultReceipt'];candidate=result['candidate']
            self.assertEqual(candidate['methodAwareMediaJobResultDigest'],receipt['payloadDigest'])
            self.assertEqual(candidate['revisionRef'],f.route['videoMethodRouteVersionRef'])
            self.assertEqual(candidate['sourceAssetVersions'],[{'assetVersionRef':receipt['sourceAssetVersionRef'],
                'assetVersionDigest':receipt['sourceAssetVersionDigest']}])
            self.assertEqual({c['check'] for c in result['technicalValidation']['checks']},{
                'media-job-terminal-succeeded','route-request-job-binding-exact','execution-envelope-valid',
                'attempt-backend-binding-valid','artifact-byte-size-valid','artifact-sha256-valid',
                'artifact-probe-matches-output','source-asset-version-current','publication-disabled'})
        self.assertEqual(result_sets[0],result_sets[1])
