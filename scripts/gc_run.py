#!/usr/bin/env python3
"""Transactional garbage collection for run workspaces.

Dry-run is the default. ``--apply`` first writes an operation manifest, then
moves only top-level candidates into a recoverable archive. A failed move rolls
back already moved items. ``--restore`` replays the manifest backwards.
``--purge`` permanently removes only a valid, fully-applied GC archive whose
manifest fingerprints still match its contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PATTERNS=("_toolchain-*","_archive","_superseded","__pycache__","*.tmp","*.chk","_tmp*",".tmp*")
SCHEMA_VERSION=2


def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def describe(path:Path,root:Path)->dict[str,Any]:
    if path.is_file(): return {"path":str(path.relative_to(root)),"kind":"file","size":path.stat().st_size,"sha256":sha256(path)}
    files=[]; total=0
    for f in sorted(x for x in path.rglob("*") if x.is_file()):
        total+=f.stat().st_size; files.append({"path":str(f.relative_to(root)),"size":f.stat().st_size,"sha256":sha256(f)})
    return {"path":str(path.relative_to(root)),"kind":"directory","size":total,"files":files}


def _raw_candidates(root:Path)->list[Path]:
    found=[]
    for base in [root,*[p for p in root.iterdir() if p.is_dir() and p.name!="_gc_archive"]]:
        for pat in PATTERNS:
            for p in base.glob(pat):
                if "_gc_archive" in p.parts: continue
                rp=p.resolve()
                if rp not in found: found.append(rp)
    return sorted(found,key=lambda p:(len(p.parts),str(p)))


def candidates(root:Path)->list[Path]:
    """Return only outermost candidates so a parent move never duplicates children."""
    selected=[]
    for p in _raw_candidates(root):
        if any(parent==p or parent in p.parents for parent in selected): continue
        selected.append(p)
    return sorted(selected,key=lambda p:str(p))


def build_plan(root:Path,archive:Path)->dict[str,Any]:
    rows=[describe(x,root) for x in candidates(root)]
    ops=[]
    for row in rows:
        ops.append({"source":row["path"],"destination":str((archive/row["path"]).relative_to(root)),"fingerprint":row,"status":"planned"})
    return {"schema_version":SCHEMA_VERSION,"root":str(root),"archive":str(archive),"status":"planned","created_at":datetime.now(timezone.utc).isoformat(),"bytes":sum(r["size"] for r in rows),"operations":ops}


def _write_manifest(archive:Path,manifest:dict[str,Any])->None:
    archive.mkdir(parents=True,exist_ok=True)
    (archive/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")


def _same_fingerprint(path:Path,record:dict[str,Any])->bool:
    if not path.exists(): return False
    if record.get("kind")=="file": return path.is_file() and sha256(path)==record.get("sha256")
    if not path.is_dir(): return False
    for item in record.get("files",[]):
        if not isinstance(item,dict): return False
        rel=Path(item["path"]); prefix=Path(record["path"])
        try: local=rel.relative_to(prefix)
        except ValueError: return False
        target=path/local
        if not target.is_file() or sha256(target)!=item.get("sha256"): return False
    return True


def apply_plan(root:Path,archive:Path,manifest:dict[str,Any])->dict[str,Any]:
    _write_manifest(archive,manifest)
    moved=[]
    try:
        for op in manifest["operations"]:
            src=root/op["source"]; dst=root/op["destination"]
            if not src.exists(): raise FileNotFoundError(f"planned source disappeared: {src}")
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.move(str(src),str(dst)); op["status"]="moved"; moved.append(op); _write_manifest(archive,manifest)
        manifest["status"]="applied"; manifest["applied_at"]=datetime.now(timezone.utc).isoformat(); _write_manifest(archive,manifest); return manifest
    except Exception as exc:
        rollback_errors=[]
        for op in reversed(moved):
            src=root/op["source"]; dst=root/op["destination"]
            try:
                src.parent.mkdir(parents=True,exist_ok=True)
                if dst.exists(): shutil.move(str(dst),str(src))
                op["status"]="rolled_back"
            except Exception as rollback_exc: rollback_errors.append(str(rollback_exc)); op["status"]="rollback_failed"
        manifest["status"]="rollback_failed" if rollback_errors else "rolled_back"
        manifest["error"]=str(exc); manifest["rollback_errors"]=rollback_errors; _write_manifest(archive,manifest)
        raise


def load_manifest(archive:Path,root:Path)->dict[str,Any]:
    manifest_path=archive/"manifest.json"
    if not manifest_path.is_file(): raise ValueError("GC archive has no manifest.json")
    data=json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema_version")!=SCHEMA_VERSION: raise ValueError("unsupported GC manifest schema")
    if Path(data.get("root","")).resolve()!=root.resolve(): raise ValueError("manifest root does not match --root")
    if Path(data.get("archive","")).resolve()!=archive.resolve(): raise ValueError("manifest archive path mismatch")
    if not isinstance(data.get("operations"),list): raise ValueError("invalid GC manifest operations")
    return data


def restore(root:Path,archive:Path)->dict[str,Any]:
    manifest=load_manifest(archive,root)
    if manifest.get("status") not in {"applied","rollback_failed"}: raise ValueError(f"archive status {manifest.get('status')} is not restorable")
    restored=[]
    for op in reversed(manifest["operations"]):
        src=root/op["destination"]; dst=root/op["source"]
        if not src.exists(): continue
        if dst.exists(): raise FileExistsError(f"restore destination already exists: {dst}")
        dst.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(src),str(dst)); op["status"]="restored"; restored.append(op["source"])
    manifest["status"]="restored"; manifest["restored_at"]=datetime.now(timezone.utc).isoformat(); manifest["restored"]=restored; _write_manifest(archive,manifest); return manifest


def verify_for_purge(root:Path,archive:Path)->dict[str,Any]:
    manifest=load_manifest(archive,root)
    if manifest.get("status")!="applied": raise ValueError("only a fully applied GC archive may be purged")
    for op in manifest["operations"]:
        archived=root/op["destination"]
        if not _same_fingerprint(archived,op["fingerprint"]): raise ValueError(f"archive fingerprint mismatch: {archived}")
    return manifest


def main()->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--root",required=True,type=Path); p.add_argument("--apply",action="store_true"); p.add_argument("--restore",type=Path); p.add_argument("--purge",type=Path); a=p.parse_args(); root=a.root.resolve()
    if sum(bool(x) for x in (a.apply,a.restore,a.purge))>1: raise SystemExit("choose only one of --apply/--restore/--purge")
    if a.restore:
        result=restore(root,a.restore.resolve()); print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
    if a.purge:
        target=a.purge.resolve()
        if root not in target.parents or "_gc_archive" not in target.parts: raise SystemExit("--purge target must be under <root>/_gc_archive")
        verify_for_purge(root,target); shutil.rmtree(target); print(json.dumps({"purged":str(target),"verified_manifest":True},ensure_ascii=False)); return 0
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); archive=root/"_gc_archive"/stamp; plan=build_plan(root,archive)
    if not a.apply:
        report={**plan,"dry_run":True,"candidate_count":len(plan["operations"])}; print(json.dumps(report,ensure_ascii=False,indent=2)); return 0
    result=apply_plan(root,archive,plan); print(json.dumps(result,ensure_ascii=False,indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
