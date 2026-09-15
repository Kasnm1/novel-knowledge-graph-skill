#!/usr/bin/env python3
"""Build an index of canonical runs using graph metadata, never directory names."""
from __future__ import annotations
import argparse, html, json
from pathlib import Path

def inspect(run:Path)->dict|None:
    gp=run/"graph.json"
    if not gp.exists(): return None
    try:g=json.loads(gp.read_text(encoding="utf-8"))
    except Exception as e:return {"run":run.name,"error":str(e)}
    m=g.get("metadata") if isinstance(g.get("metadata"),dict) else {}; analyzed=[x for x in m.get("analyzed_chapters",[]) if isinstance(x,int)]
    return {"run":run.name,"title":m.get("title"),"chapter_start":min(analyzed) if analyzed else m.get("chapter_start"),"chapter_end":max(analyzed) if analyzed else m.get("chapter_end"),"analyzed_count":len(set(analyzed)),"entities":len(g.get("entities",[]) if isinstance(g.get("entities"),list) else []),"events":len(g.get("events",[]) if isinstance(g.get("events"),list) else []),"commitments":len(g.get("commitments",[]) if isinstance(g.get("commitments"),list) else []),"graph":str(gp)}
def main()->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--runs-root",required=True,type=Path); p.add_argument("--json",type=Path); p.add_argument("--html",type=Path); a=p.parse_args(); rows=[r for r in (inspect(d) for d in sorted(a.runs_root.iterdir()) if d.is_dir()) if r]
    payload={"runs":rows}
    if a.json:a.json.parent.mkdir(parents=True,exist_ok=True); a.json.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    if a.html:
        trs="".join(f"<tr><td>{html.escape(str(r.get('title') or r.get('run')))}</td><td>{r.get('chapter_start','')}–{r.get('chapter_end','')}</td><td>{r.get('analyzed_count','')}</td><td>{r.get('entities','')}</td><td>{r.get('events','')}</td><td>{r.get('commitments','')}</td></tr>" for r in rows)
        a.html.parent.mkdir(parents=True,exist_ok=True); a.html.write_text(f"<!doctype html><meta charset='utf-8'><title>Novel runs</title><style>body{{font-family:system-ui;margin:32px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px}}</style><h1>Novel run index</h1><table><tr><th>书</th><th>真实覆盖</th><th>已分析章</th><th>实体</th><th>事件</th><th>承诺</th></tr>{trs}</table>",encoding="utf-8")
    print(json.dumps({"runs":len(rows),"json":str(a.json) if a.json else None,"html":str(a.html) if a.html else None},ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
