import json,tempfile,unittest
from pathlib import Path
from batch_runner import ALLOW,EXCLUDED,BatchError,queue,validate_manifest
class T(unittest.TestCase):
 def m(self): return {'exactShotIds':list(ALLOW),'maxTotalPromptPosts':15,'maxPromptPostsPerShot':1,'automaticRetryAllowed':False,'sequentialOnly':True,'authorityState':'TECHNICAL_EVIDENCE_ONLY','publicationAllowed':False,'canonicalMutations':0,'sourceShotsJsonSha256':'52e24c8c781f2c729239d6152246677c8eb633d43d17463550c22bb91c8fd9c9','perShotSemanticDigests':{x:'0'*64 for x in ALLOW}}
 def test_01_exact(self): validate_manifest(self.m())
 def test_02_sh12(self): self.assertNotIn('EP01_SH12',ALLOW)
 def test_03_excluded(self): self.assertFalse(EXCLUDED&set(ALLOW))
 def test_04_post_per_shot(self): self.assertEqual(self.m()['maxPromptPostsPerShot'],1)
 def test_05_post_total(self): self.assertEqual(self.m()['maxTotalPromptPosts'],15)
 def test_06_no_retry(self): self.assertFalse(self.m()['automaticRetryAllowed'])
 def test_07_sequential(self): self.assertTrue(self.m()['sequentialOnly'])
 def test_08_count(self): self.assertEqual(len(ALLOW),15)
 def test_09_order(self): self.assertEqual(ALLOW[0],'EP01_SH03')
 def test_10_last(self): self.assertEqual(ALLOW[-1],'EP01_SH18')
 def test_11_wildcard(self): self.assertNotIn('*',ALLOW)
 def test_12_duplicate(self): self.assertEqual(len(ALLOW),len(set(ALLOW)))
 def test_13_bad_allow(self):
  m=self.m();m['exactShotIds'].append('EP01_SH12');self.assertRaises(BatchError,validate_manifest,m)
 def test_14_bad_budget(self):
  m=self.m();m['maxTotalPromptPosts']=16;self.assertRaises(BatchError,validate_manifest,m)
 def test_15_bad_retry(self):
  m=self.m();m['automaticRetryAllowed']=True;self.assertRaises(BatchError,validate_manifest,m)
 def test_16_bad_semantics(self):
  m=self.m();m['perShotSemanticDigests'].pop(ALLOW[0]);self.assertRaises(BatchError,validate_manifest,m)
 def test_17_resume_complete(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'shots'/ALLOW[0];p.mkdir(parents=True);(p/'STATE.json').write_text(json.dumps({'state':'COMPLETED'}));self.assertNotIn(ALLOW[0],queue(self.m(),Path(d)))
 def test_18_prompt_accepted(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'shots'/ALLOW[0];p.mkdir(parents=True);(p/'STATE.json').write_text(json.dumps({'state':'PROMPT_ACCEPTED'}));self.assertRaises(BatchError,queue,self.m(),Path(d))
 def test_19_recovery(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'shots'/ALLOW[0];p.mkdir(parents=True);(p/'STATE.json').write_text(json.dumps({'state':'OUTPUT_RECOVERY_REQUIRED'}));self.assertRaises(BatchError,queue,self.m(),Path(d))
 def test_20_not_started(self):
  with tempfile.TemporaryDirectory() as d:self.assertEqual(queue(self.m(),Path(d)),list(ALLOW))
if __name__=='__main__':unittest.main()
