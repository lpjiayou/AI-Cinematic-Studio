import json
import unittest

from apps.creator_workspace_mvp import (
    AI_DIRECTOR_SCHEMA_VERSION,
    PROJECT_DRAFT_INPUT_SCHEMA_VERSION,
    AiDirectorService,
    ProjectDraftInputError,
    build_session_project_draft_input,
)
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


class AiDirectorProjectDraftFlowIntegrationTests(unittest.TestCase):
    def test_validated_plan_requires_confirmation_then_maps_without_free_text_bridge(self):
        capability = FakeTextGenerationCapability([json.dumps(valid_plan(), ensure_ascii=False)])
        plan = AiDirectorService(capability).generate(valid_brief())

        with self.assertRaises(ProjectDraftInputError):
            build_session_project_draft_input(
                plan,
                valid_brief(),
                plan_version=1,
                project_ref="local-project-wanlight-001",
                confirmed=False,
            )

        draft = build_session_project_draft_input(
            plan,
            valid_brief(),
            plan_version=1,
            project_ref="local-project-wanlight-001",
            confirmed=True,
        )

        self.assertEqual(draft["schemaVersion"], PROJECT_DRAFT_INPUT_SCHEMA_VERSION)
        self.assertEqual(draft["sourcePlanSchemaVersion"], AI_DIRECTOR_SCHEMA_VERSION)
        self.assertEqual(draft["sourcePlanRef"], "local-ai-director-plan-1")
        self.assertEqual(draft["sourcePlanVersion"], 1)
        self.assertEqual(draft["sourcePlan"], plan)
        self.assertEqual(draft["story"]["direction"], plan["storyDirection"])
        self.assertEqual(draft["story"]["script"], plan["scriptDraft"])
        self.assertEqual(draft["characters"], plan["productionPlan"]["characters"])
        self.assertEqual(draft["scenes"], plan["productionPlan"]["scenes"])
        self.assertEqual(draft["storyboard"], plan["storyboardPlan"])
        self.assertEqual(draft["visualStyle"], plan["visualStyle"])
        self.assertEqual(draft["productionPlan"], plan["productionPlan"])
        self.assertEqual(draft["persistence"], "session-only")
        self.assertFalse(draft["domainFact"])
        self.assertNotIn("projectId", draft)


if __name__ == "__main__":
    unittest.main()
