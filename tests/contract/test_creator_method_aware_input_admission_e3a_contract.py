"""Closed current-image authority, composition and public resource contracts."""
import ast
import inspect
from pathlib import Path
import tempfile
import unittest

from apps.creator_workspace_mvp import public_contract, server
from services.v4_platform import method_aware_input_artifacts as artifacts
from services.v5_core_os.episode_production import method_aware_input_assets as assets, public
from scripts import method_aware_input_artifact_bundle as operator


class CurrentInputAdmissionContractTests(unittest.TestCase):
    def test_exact_eight_method_aware_resources_and_34_subresources(self):
        expected={'execution-method-plan','method-aware-input-plan','method-aware-video-route',
            'method-aware-video-jobs','method-aware-video-candidates','explicit-audio-requirement-route',
            'method-aware-input-candidates','method-aware-input-admission'}
        self.assertEqual(set(public_contract.PUBLIC_METHOD_AWARE_RESOURCES),expected)
        self.assertEqual(len(server.EPISODE_PRODUCTION_SUBRESOURCES),34)
        m10=next(c for c in public_contract.CAPABILITY_PROJECTION if c['id']=='M10')
        for resource in ('method-aware-input-candidates','method-aware-input-admission'):
            self.assertIn(resource,server.EPISODE_PRODUCTION_SUBRESOURCES)
            self.assertIn('episode-production-runs/'+resource,m10['publicResources'])
        for resource in ('comfyui','image-upload','voice-profile','voice-lock','consent-grant','source-recording','distance','state','transform','composition','ffmpeg'):
            self.assertNotIn(resource,server.EPISODE_PRODUCTION_SUBRESOURCES)

    def test_v4_read_port_and_v5_lifecycle_have_no_execution_or_second_authority(self):
        for module in (artifacts,assets):
            source=inspect.getsource(module)
            for token in ('providerId','modelId','adapterIdentity','backendRef','ComfyUI','Wan','A100','prompt_id','/prompt','/history','/view','CREATE TABLE','sqlite3','tests.'):
                self.assertNotIn(token,source)
        tree=ast.parse(inspect.getsource(artifacts.DigestPinnedMethodAwareInputArtifactEvidence))
        calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
        for name in ('dispatch','run_one','write_bytes','write_text','unlink','mkdir','request','generate'):self.assertNotIn(name,calls)
        source=inspect.getsource(operator)
        self.assertNotIn('tests.',source);self.assertNotIn('services.v5_core_os',source)
        self.assertNotIn('uuid4',source)

    def test_composition_rejects_partial_config_before_creating_database(self):
        for factory in (public.create_in_memory_boundary,public.create_local_development_boundary):
            self.assertIn('method_aware_input_artifact_evidence',inspect.signature(factory).parameters)
        with tempfile.TemporaryDirectory() as temporary:
            database=Path(temporary)/'must-not-be-created.sqlite3'
            with self.assertRaises(artifacts.MethodAwareInputArtifactError):
                public.create_local_development_boundary_from_environment(project_boundary=None,
                    series_episode_boundary=None,series_planning_boundary=None,script_studio_boundary=None,
                    environ={'CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_PATH':'missing',
                             'CREATOR_DATA_PATH':str(database)})
            self.assertFalse(database.exists())

    def test_input_asset_v1_is_image_anchor_technical_evidence_only(self):
        self.assertEqual(assets.ASSET_SCHEMA,'v5.method-aware-input-image-asset-version.v1')
        self.assertEqual(assets.ADMISSION_SCHEMA,'v5.method-aware-input-asset-admission.v1')
        self.assertEqual(assets.RECEIPT_SCHEMA,'v5.method-aware-input-artifact-receipt.v1')
        self.assertEqual(assets.INPUT_ROLE,'ACTION_READY_ANCHOR')
        self.assertNotIn('assetVersionRef',assets.INTAKE_FIELDS)
        self.assertNotIn('actorRef',assets.ADMIT_FIELDS)
        self.assertNotIn('publicationAllowed',assets.ADMIT_FIELDS)
        self.assertEqual(artifacts.CONFIG_NAMES,('CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_PATH',
            'CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_SHA256','CREATOR_METHOD_AWARE_SOURCE_ROOT'))
