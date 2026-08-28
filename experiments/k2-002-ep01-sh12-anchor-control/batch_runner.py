#!/usr/bin/env python3
from __future__ import annotations
import argparse, asyncio, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
from typing import Any, Mapping

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from r6_protocol import AiohttpAdapter, ComfyLifecycle, ProtocolError, canonical_sha256, dry_run_report

ALLOW=("EP01_SH03","EP01_SH04","EP01_SH05","EP01_SH06","EP01_SH07","EP01_SH08","EP01_SH09","EP01_SH10","EP01_SH11","EP01_SH13","EP01_SH14","EP01_SH15","EP01_SH16","EP01_SH17","EP01_SH18")
EXCLUDED={"EP01_SH01","EP01_SH02","EP01_SH12"}
STATES={"NOT_STARTED","RESERVED","PROMPT_ACCEPTED","QUEUED","RUNNING","COMPLETED","FAILED_EXECUTION","FAILED_TECHNICAL_VALIDATION","FAILED_CONTROL_BINDING","OUTPUT_RECOVERY_REQUIRED"}

class BatchError(RuntimeError): pass
def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1048576),b''): h.update(c)
 return h.hexdigest()
def load(p:Path)->Any: return json.loads(p.read_text(encoding='utf-8'))
def put_exclusive(p:Path,v:Any)->None:
 p.parent.mkdir(parents=True,exist_ok=True); data=(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode(); fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(fd,data); os.fsync(fd); os.close(fd)
def validate_manifest(m:Mapping[str,Any])->None:
 if tuple(m.get('exactShotIds',()))!=ALLOW: raise BatchError('exact 15-shot allowlist changed')
 if EXCLUDED & set(m['exactShotIds']): raise BatchError('excluded shot entered allowlist')
 checks={'maxTotalPromptPosts':15,'maxPromptPostsPerShot':1,'automaticRetryAllowed':False,'sequentialOnly':True,'authorityState':'TECHNICAL_EVIDENCE_ONLY','publicationAllowed':False,'canonicalMutations':0}
 for k,v in checks.items():
  if m.get(k)!=v: raise BatchError(f'{k} changed')
 if m.get('sourceShotsJsonSha256')!='52e24c8c781f2c729239d6152246677c8eb633d43d17463550c22bb91c8fd9c9': raise BatchError('shots digest changed')
 if set(m.get('perShotSemanticDigests',{}))!=set(ALLOW): raise BatchError('semantic digest set changed')
def materialize(shot:Mapping[str,Any],template:Mapping[str,Any])->dict[str,Any]:
 w=json.loads(json.dumps(template)); w['5']['inputs']['text']=shot['positivePrompt']; w['6']['inputs']['text']=shot['negativePrompt']; w['8']['inputs']['seed']=shot['seed']; w['11']['inputs']['filename_prefix']='k2-002-ep01-i2v-batch-r2/'+shot['outputPrefix']; w['12']['inputs']['image']='k2-002-ep01-i2v-batch-r2/'+shot['startAnchorSha256']+'.png'; return w
def semantic(w:Mapping[str,Any])->str:return canonical_sha256(w)
def validate_inputs(root:Path,m:Mapping[str,Any])->tuple[dict[str,Any],dict[str,dict[str,Any]]]:
 shots=load(root/'inputs/shots.json'); template=load(root/'inputs/workflow.json')
 if sha(root/'inputs/shots.json')!=m['sourceShotsJsonSha256']: raise BatchError('shots bytes drift')
 by={s['shotId']:s for s in shots['shots']}; out={}
 for sid in ALLOW:
  if sid not in by: raise BatchError(f'missing {sid}')
  shot=by[sid]; anchor=root/'inputs'/shot['startAnchorPath']
  if not anchor.is_file() or sha(anchor)!=shot['startAnchorSha256']: raise BatchError(f'anchor bytes drift {sid}')
  w=materialize(shot,template)
  if semantic(w)!=m['perShotSemanticDigests'][sid]: raise BatchError(f'semantic digest drift {sid}')
  staged=Path(m['comfyuiInputRoot'])/w['12']['inputs']['image']
  if not staged.is_file() or sha(staged)!=shot['startAnchorSha256']: raise BatchError(f'staged anchor binding failed {sid}')
  out[sid]=w
 return template,out
def state_path(e:Path,sid:str)->Path:return e/'shots'/sid/'STATE.json'
def read_state(e:Path,sid:str)->str:
 p=state_path(e,sid)
 if not p.exists(): return 'NOT_STARTED'
 s=load(p).get('state');
 if s not in STATES: raise BatchError(f'invalid state {sid}')
 return s
def reserve(e:Path,sid:str)->None: put_exclusive(state_path(e,sid),{'shotId':sid,'state':'RESERVED','promptAccepted':False})
def replace_state(e:Path,sid:str,v:Mapping[str,Any])->None:
 p=state_path(e,sid); tmp=p.with_suffix('.tmp'); tmp.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n'); os.replace(tmp,p)
def queue(m:Mapping[str,Any],e:Path)->list[str]:
 result=[]
 for sid in m['exactShotIds']:
  s=read_state(e,sid)
  if s=='NOT_STARTED': result.append(sid)
  elif s in {'RESERVED','PROMPT_ACCEPTED','QUEUED','RUNNING','FAILED_CONTROL_BINDING','OUTPUT_RECOVERY_REQUIRED'}: raise BatchError(f'recovery audit required {sid}: {s}')
 return result
def dry(root:Path,m:Mapping[str,Any],workflows:Mapping[str,Any])->dict[str,Any]:
 return {'mode':'DRY_RUN','shotIds':list(ALLOW),'shotCount':15,'promptPostCount':0,'gpuOrProviderCalls':0,'reports':{k:dry_run_report(v) for k,v in workflows.items()},'snapshotSha256':m['executionSnapshotSha256']}
async def execute(root:Path,m:Mapping[str,Any],workflows:Mapping[str,Any])->dict[str,Any]:
 if os.environ.get('K2_EP01_I2V_ACK')!='TECHNICAL_EVIDENCE_ONLY': raise BatchError('missing technical evidence acknowledgement')
 evidence=Path(m['evidenceRoot']); evidence.mkdir(parents=True,exist_ok=True); completed=[]; failed=[]; posts=0
 for sid in queue(m,evidence):
  if posts>=15: raise BatchError('batch POST budget exceeded')
  reserve(evidence,sid); attempt=evidence/'shots'/sid/'attempt'
  try:
   life=ComfyLifecycle(AiohttpAdapter(m['comfyuiBaseUrl']),timeout_seconds=m.get('timeoutSeconds',3600),poll_seconds=2,evidence_dir=attempt)
   result=await life.run(workflows[sid],experiment_id=m['batchId']+':'+sid); posts+=result.prompt_post_count
   replace_state(evidence,sid,{'shotId':sid,'state':'PROMPT_ACCEPTED','promptAccepted':True,'promptId':result.ids.prompt_id,'clientId':result.ids.client_id,'attemptId':result.ids.attempt_id,'correlationId':result.ids.correlation_id})
   if len(result.history.output_records)!=1: raise BatchError('unique output attribution failed')
   o=result.history.output_records[0]; src=Path(m['comfyuiOutputRoot'])/o.get('subfolder','')/o['filename']; dst=evidence/'media'/(sid+'.mp4'); dst.parent.mkdir(parents=True,exist_ok=True)
   if dst.exists(): raise BatchError('evidence media exists')
   shutil.copyfile(src,dst)
   probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_entries','stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration','-of','json',str(dst)],text=True))
   streams=probe.get('streams',[]); videos=[x for x in streams if x.get('codec_type')=='video']; audios=[x for x in streams if x.get('codec_type')=='audio']; video=videos[0] if len(videos)==1 else {}; duration=float(probe.get('format',{}).get('duration',0)); ok=len(videos)==1 and not audios and video.get('codec_name')=='h264' and video.get('width')==704 and video.get('height')==1280 and video.get('r_frame_rate')=='24/1' and video.get('avg_frame_rate')=='24/1' and video.get('nb_read_frames')=='49' and 1.9<=duration<=2.2
   receipt={'shotId':sid,'state':'COMPLETED' if ok else 'FAILED_TECHNICAL_VALIDATION','promptId':result.ids.prompt_id,'clientId':result.ids.client_id,'attemptId':result.ids.attempt_id,'correlationId':result.ids.correlation_id,'sourcePath':str(src),'evidencePath':str(dst),'sourceSha256':sha(src),'evidenceSha256':sha(dst),'sourceCopyByteIdentical':sha(src)==sha(dst),'historyBinding':'PASS','workflowCanonicalBinding':'PASS','ffprobe':probe,'promptPostCount':1,'automaticRetryCount':0}
   put_exclusive(attempt/'RUN_RECEIPT.json',receipt); replace_state(evidence,sid,receipt); (completed if ok else failed).append(sid)
  except ProtocolError as x:
   if getattr(x,'code','') in {'EXECUTION_ERROR','EXECUTION_INTERRUPTED'}: replace_state(evidence,sid,{'shotId':sid,'state':'FAILED_EXECUTION','promptAccepted':True,'error':str(x)}); posts+=1; failed.append(sid); continue
   replace_state(evidence,sid,{'shotId':sid,'state':'FAILED_CONTROL_BINDING','promptAccepted':posts>0,'error':str(x)}); raise
 return {'completed':completed,'failed':failed,'promptPostCount':posts,'automaticRetryCount':0}
def main()->int:
 a=argparse.ArgumentParser(); a.add_argument('manifest',type=Path); g=a.add_mutually_exclusive_group(required=True); g.add_argument('--dry-run',action='store_true'); g.add_argument('--execute',action='store_true'); z=a.parse_args(); m=load(z.manifest); validate_manifest(m); root=z.manifest.resolve().parent.parent; _,w=validate_inputs(root,m)
 if z.dry_run: print(json.dumps(dry(root,m,w),sort_keys=True)); return 0
 print(json.dumps(asyncio.run(execute(root,m,w)),sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
