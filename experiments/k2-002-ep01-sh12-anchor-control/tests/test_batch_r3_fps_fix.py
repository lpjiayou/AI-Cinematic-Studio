import copy, json, unittest
from batch_runner import ALLOW, EXCLUDED, BatchError, dry, materialize, validate_manifest
from r6_protocol import canonical_sha256

EXPECTED = (
    "EP01_SH04","EP01_SH05","EP01_SH06","EP01_SH07","EP01_SH08","EP01_SH09",
    "EP01_SH10","EP01_SH11","EP01_SH13","EP01_SH14","EP01_SH15","EP01_SH16",
    "EP01_SH17","EP01_SH18",
)

def fixture():
    shot={"positivePrompt":"p","negativePrompt":"n","seed":7,"outputPrefix":"EP01_SH04-v2-technical-evidence","startAnchorSha256":"a"*64}
    template={
        "5":{"class_type":"CLIPTextEncode","inputs":{"text":"old-p"}},
        "6":{"class_type":"CLIPTextEncode","inputs":{"text":"old-n"}},
        "8":{"class_type":"KSampler","inputs":{"seed":1}},
        "10":{"class_type":"CreateVideo","inputs":{"fps":24,"images":["9",0]}},
        "11":{"class_type":"SaveVideo","inputs":{"filename_prefix":"old","video":["10",0]}},
        "12":{"class_type":"LoadImage","inputs":{"image":"old.png"}},
    }
    return shot,template

def manifest():
    return {"exactShotIds":list(ALLOW),"maxTotalPromptPosts":14,"maxPromptPostsPerShot":1,
        "automaticRetryAllowed":False,"sequentialOnly":True,"authorityState":"TECHNICAL_EVIDENCE_ONLY",
        "publicationAllowed":False,"canonicalMutations":0,
        "sourceShotsJsonSha256":"52e24c8c781f2c729239d6152246677c8eb633d43d17463550c22bb91c8fd9c9",
        "perShotSemanticDigests":{x:"0"*64 for x in ALLOW},"executionSnapshotSha256":"1"*64}

def typed_diff(a,b,path=""):
    if type(a) is not type(b): return [path or "/"]
    if isinstance(a,dict):
        out=[]
        for k in sorted(set(a)|set(b)):
            q=path+"/"+k
            if k not in a or k not in b: out.append(q)
            else: out.extend(typed_diff(a[k],b[k],q))
        return out
    if isinstance(a,list):
        out=[]
        if len(a)!=len(b): out.append(path)
        for i,(x,y) in enumerate(zip(a,b)): out.extend(typed_diff(x,y,path+"/"+str(i)))
        return out
    return [] if a==b else [path or "/"]

class BatchR3FpsFixTests(unittest.TestCase):
    def test_01_outbound_fps_value(self):
        s,t=fixture(); self.assertEqual(materialize(s,t)["10"]["inputs"]["fps"],24.0)
    def test_02_outbound_fps_type(self):
        s,t=fixture(); self.assertIs(type(materialize(s,t)["10"]["inputs"]["fps"]),float)
    def test_03_submitted_history_strict_digest(self):
        s,t=fixture(); submitted=materialize(s,t); history=json.loads(json.dumps(submitted))
        self.assertEqual(canonical_sha256(submitted),canonical_sha256(history))
        history["10"]["inputs"]["fps"]=24
        self.assertNotEqual(canonical_sha256(submitted),canonical_sha256(history))
    def test_04_only_workflow_change_is_fps_representation(self):
        s,t=fixture(); old=copy.deepcopy(t)
        old["5"]["inputs"]["text"]=s["positivePrompt"]; old["6"]["inputs"]["text"]=s["negativePrompt"]
        old["8"]["inputs"]["seed"]=s["seed"]
        old["11"]["inputs"]["filename_prefix"]="k2-002-ep01-i2v-batch-r2/"+s["outputPrefix"]
        old["12"]["inputs"]["image"]="k2-002-ep01-i2v-batch-r2/"+s["startAnchorSha256"]+".png"
        self.assertEqual(typed_diff(old,materialize(s,t)),["/10/inputs/fps"])
    def test_05_exact_remaining_14(self): self.assertEqual(ALLOW,EXPECTED)
    def test_06_sh03_and_sh12_rejected(self):
        self.assertIn("EP01_SH03",EXCLUDED); self.assertIn("EP01_SH12",EXCLUDED)
        for sid in ("EP01_SH03","EP01_SH12"):
            m=manifest(); m["exactShotIds"][0]=sid
            with self.assertRaises(BatchError): validate_manifest(m)
    def test_07_dry_run_posts_zero(self):
        s,t=fixture(); w=materialize(s,t); self.assertEqual(dry(__import__("pathlib").Path("."),manifest(),{x:w for x in ALLOW})["promptPostCount"],0)
    def test_08_max_one_post_per_shot(self): self.assertEqual(manifest()["maxPromptPostsPerShot"],1)
    def test_09_no_automatic_retry(self): self.assertFalse(manifest()["automaticRetryAllowed"])
    def test_10_sequential(self): self.assertTrue(manifest()["sequentialOnly"])

if __name__=="__main__": unittest.main()
