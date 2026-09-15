#!/usr/bin/env python3
"""Safely garbage-collect generated run debris.

Default mode is dry-run. ``--apply`` moves candidates into a timestamped,
recoverable archive and writes a manifest with SHA-256 fingerprints. ``--purge``
may permanently delete only from a previously created archive directory.
"""
from __future__ import annotations
import argparse, hashlib, json, shutil
from datetime import datetime, timezone
from pathlib import Path

PATTERNS=("_toolchain-*","_archive","_superseded","__pycache__","*.tmp","*.chk","_tmp*",".tmp*")

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def describe(path:Path,root:Path)->dict:
    if path.is_file(): return {"path":str(path.relative_to(root)),"kind":"file","size":path.stat().st_size,"sha256":sha256(path)}
    files=[]; total=0
    for f in sorted(x for x in path.rglob("*") if x.is_file()):
        total+=f.stat().st_size; files.append({"path":str(f.relative_to(root)),"size":f.stat().st_size,"sha256":sha256(f)})
    return {"path":str(path.relative_to(root)),"kind":"directory","size":total,"files":files}

def candidates(root:Path)->list[Path]:
    found=[]
    for pat in PATTERNS:
        for p in root.glob(pat):
            if p.name=="_gc_archive": continue
            if p not in found: found.append(p)
    # Also scan one level down because run debris is usually per-run.
    for run in [p for p in root.iterdir() if p.is_dir() and p.name!="_gc_archive"]:
        for pat in PATTERNS:
            for p in run.glob(pat):
                if p not in found: found.append(p)
    return sorted(found,key=lambda p:str(p))

def main()->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--root",required=True,type=Path); p.add_argument("--apply",action="store_true"); p.add_argument("--purge",type=Path); a=p.parse_args(); root=a.root.resolve()
    if a.purge:
        target=a.purge.resolve()
        if root not in target.parents or "_gc_archive" not in target.parts: raise SystemExit("--purge target must be under <root>/_gc_archive")
        shutil.rmtree(target); print(json.dumps({"purged":str(target)},ensure_ascii=False)); return 0
    rows=[describe(x,root) for x in candidates(root)]
    report={"root":str(root),"dry_run":not a.apply,"candidate_count":len(rows),"bytes":sum(r["size"] for r in rows),"items":rows}
    if not a.apply:
        print(json.dumps(report,ensure_ascii=False,indent=2)); return 0
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); archive=root/"_gc_archive"/stamp; archive.mkdir(parents=True,exist_ok=True)
    moved=[]
    for row in rows:
        src=root/row["path"]; dest=archive/row["path"]; dest.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(src),str(dest)); moved.append(row["path"])
    report.update({"archive":str(archive),"moved":moved,"dry_run":False}); (archive/"manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps(report,ensure_ascii=False,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
