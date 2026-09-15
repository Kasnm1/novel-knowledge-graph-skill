#!/usr/bin/env python3
"""Fail-closed one-command build for the final artifact set.

Every subprocess result is recorded. A build is successful only when every
required step returns zero and every declared artifact exists. The manifest is
written even on failure so partial output is diagnosable rather than mistaken
for a complete delivery.
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def digest(path:Path)->dict[str,Any]:
    h=hashlib.sha256(); size=0
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): size+=len(chunk); h.update(chunk)
    return {"path":str(path),"size":size,"sha256":h.hexdigest()}


def run_step(name:str,cmd:list[Any],manifest:dict[str,Any])->int:
    proc=subprocess.run([str(x) for x in cmd],capture_output=True,text=True,check=False)
    manifest["steps"].append({"name":name,"command":[str(x) for x in cmd],"returncode":proc.returncode,"stdout":proc.stdout[-6000:],"stderr":proc.stderr[-6000:]})
    return proc.returncode


def write_manifest(path:Path,manifest:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')


def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--graph',required=True,type=Path);p.add_argument('--output-dir',required=True,type=Path);p.add_argument('--manifest',type=Path);p.add_argument('--chapters-jsonl',type=Path);p.add_argument('--collection-manifest',type=Path);p.add_argument('--cutoff',type=int);p.add_argument('--protagonist-id',action='append',default=[]);a=p.parse_args()
    d=Path(__file__).resolve().parent; out=a.output_dir; out.mkdir(parents=True,exist_ok=True); manifest_path=out/'artifact-manifest.json'
    m={"schema_version":1,"status":"running","created_at":datetime.now(timezone.utc).isoformat(),"source_graph":str(a.graph),"cutoff":a.cutoff,"steps":[],"required_artifacts":[],"artifacts":[]}
    def fail(reason:str)->int:
        m["status"]='failed';m["failure_reason"]=reason;m["finished_at"]=datetime.now(timezone.utc).isoformat();write_manifest(manifest_path,m);print(json.dumps({"status":"failed","reason":reason,"manifest":str(manifest_path)},ensure_ascii=False));return 1
    validate=[sys.executable,d/'validate_full_graph.py','--graph',a.graph,'--base-report',out/'validation-base.json','--extension-report',out/'validation-expansion.json']
    if a.manifest: validate += ['--manifest',a.manifest]
    if run_step('validate',validate,m): return fail('validation failed')
    graph=a.graph
    if a.cutoff is not None:
        graph=out/f'graph-asof-{a.cutoff}.json'
        if run_step('spoiler-closure',[sys.executable,d/'filter_graph_asof.py','--graph',a.graph,'--chapter',a.cutoff,'--output',graph],m): return fail('spoiler closure failed')
    views=out/'novel-views.json'
    cmd=[sys.executable,d/'derive_novel_views.py','--graph',graph,'--output',views]
    for pid in a.protagonist_id: cmd += ['--protagonist-id',pid]
    if run_step('derive-views',cmd,m): return fail('view derivation failed')
    dash=[sys.executable,d/'build_unified_dashboard.py','--graph',a.graph,'--output-dir',out]
    if a.cutoff is not None: dash += ['--cutoff',a.cutoff]
    if a.collection_manifest: dash += ['--collection-manifest',a.collection_manifest]
    for pid in a.protagonist_id: dash += ['--protagonist-id',pid]
    if run_step('dashboard',dash,m): return fail('dashboard build failed')
    candidates=[sys.executable,d/'build_expansion_candidates.py','--graph',a.graph,'--output',out/'expansion-candidates.json']
    if a.chapters_jsonl: candidates += ['--chapters-jsonl',a.chapters_jsonl]
    if a.cutoff is not None: candidates += ['--cutoff',a.cutoff]
    if run_step('candidates',candidates,m): return fail('candidate scan incomplete or failed')
    if a.chapters_jsonl:
        reader=[sys.executable,d/'build_reader_overlay.py','--graph',a.graph,'--chapters-jsonl',a.chapters_jsonl,'--output',out/'reader.html']
        if a.cutoff is not None: reader += ['--cutoff',a.cutoff]
        if run_step('reader',reader,m): return fail('reader build failed')
    required=[out/'validation-base.json',out/'validation-expansion.json',views,out/'dashboard.html',out/'expansion-candidates.json']
    if a.cutoff is not None: required.append(graph)
    if a.chapters_jsonl: required.append(out/'reader.html')
    m['required_artifacts']=[str(x) for x in required]
    missing=[str(x) for x in required if not x.is_file()]
    if missing: return fail('missing required artifacts: '+', '.join(missing))
    m['artifacts']=[digest(x) for x in required];m['status']='complete';m['finished_at']=datetime.now(timezone.utc).isoformat();write_manifest(manifest_path,m)
    print(json.dumps({"status":"complete","manifest":str(manifest_path),"dashboard":str(out/'dashboard.html'),"views":str(views)},ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
