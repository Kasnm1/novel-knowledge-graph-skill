#!/usr/bin/env python3
"""Create cross-book trope/narrative metrics without mixing entity IDs."""
from __future__ import annotations
import argparse,json,statistics
from pathlib import Path
from collections import Counter
from derive_novel_views import build_views

def metrics(path:Path)->dict:
    g=json.loads(path.read_text(encoding="utf-8")); v=build_views(g); m=g.get("metadata",{}) if isinstance(g.get("metadata"),dict) else {}; analyzed=[x for x in m.get("analyzed_chapters",[]) if isinstance(x,int)]; n=max(1,len(set(analyzed)))
    cliffs=Counter(r.get("cliffhanger_type") for r in v["chapter_rhythm"]["chapters"] if r.get("cliffhanger_type")); payoff_spans=[s["span"] for r in v["payoffs"]["rows"] for s in r["setups"] if isinstance(s.get("span"),int)]; romance_milestones=sum(len(r["milestones"]) for r in v["romance"]["routes"])
    return {"title":m.get("title") or path.parent.name,"chapters":len(set(analyzed)),"event_density_per_100":round(len(g.get("events",[]))*100/n,2),"battle_density_per_100":round(sum(1 for e in g.get("events",[]) if isinstance(e,dict) and e.get("type")=="battle")*100/n,2),"romance_milestones_per_100":round(romance_milestones*100/n,2),"payoff_count":len(v["payoffs"]["rows"]),"median_payoff_span":statistics.median(payoff_spans) if payoff_spans else None,"cliffhangers":dict(cliffs),"commitments":len(v["commitments"]),"relation_gap_candidates":len(v["cooccurrence"]["relation_gap_candidates"])}
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--graph",type=Path,action="append",required=True); p.add_argument("--output",required=True,type=Path); a=p.parse_args(); rows=[metrics(x) for x in a.graph]; a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps({"books":rows},ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps({"output":str(a.output),"books":len(rows)},ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
