#!/usr/bin/env python3
"""Build a side-by-side source reader with evidence/entity context cards.

The reader is a derived artifact. It loads prepared chapter text, highlights
exact evidence quotes, and shows entities/events evidenced in the same chapter.
Use ``--cutoff`` for a shareable spoiler-safe reader.
"""
from __future__ import annotations
import argparse, html, json
from pathlib import Path
from filter_graph_asof import filter_graph

def load_chapters(index:Path)->list[dict]:
    out=[]
    for line in index.read_text(encoding="utf-8").splitlines():
        if not line.strip():continue
        row=json.loads(line); p=Path(row.get("text_path","")); text=p.read_text(encoding="utf-8",errors="ignore") if p.exists() else ""; out.append({"chapter":row.get("chapter"),"title":row.get("title"),"text":text})
    return out

def payload(graph,chapters):
    names={e.get("id"):e.get("name") for e in graph.get("entities",[]) if isinstance(e,dict)}; evid_by_ch={}
    for e in graph.get("evidence",[]):
        if isinstance(e,dict) and isinstance(e.get("chapter"),int):evid_by_ch.setdefault(e["chapter"],[]).append(e)
    event_by_ch={}
    for e in graph.get("events",[]):
        if isinstance(e,dict) and isinstance(e.get("chapter"),int):event_by_ch.setdefault(e["chapter"],[]).append({"id":e.get("id"),"title":e.get("title"),"type":e.get("type"),"participants":[names.get(x,x) for x in e.get("participant_ids",[]) if isinstance(x,str)]})
    refs={}
    for key in ("entities","relations","state_changes","foreshadowing","commitments","item_roles","romance_routes"):
        for r in graph.get(key,[]):
            if not isinstance(r,dict):continue
            for evid in r.get("evidence_ids",[]) if isinstance(r.get("evidence_ids"),list) else []:refs.setdefault(evid,[]).append({"kind":key,"id":r.get("id"),"label":names.get(r.get("entity_id")) or names.get(r.get("source_id")) or names.get(r.get("character_id")) or r.get("label") or r.get("terms") or r.get("id")})
    return {"chapters":chapters,"evidence":evid_by_ch,"events":event_by_ch,"refs":refs}
def build(data,title):
    raw=json.dumps(data,ensure_ascii=False).replace("</","<\\/")
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>
body{{margin:0;font-family:system-ui;background:#0d1117;color:#e6edf3}}header{{position:sticky;top:0;background:#161b22;padding:10px 18px;border-bottom:1px solid #30363d;z-index:2}}main{{display:grid;grid-template-columns:minmax(0,2fr) minmax(320px,1fr);height:calc(100vh - 58px)}}#text{{overflow:auto;padding:24px;white-space:pre-wrap;line-height:1.9;font-family:ui-serif,serif}}aside{{overflow:auto;border-left:1px solid #30363d;padding:16px}}mark{{background:#8a6d1d;color:#fff;padding:1px 2px}}.card{{border:1px solid #30363d;border-radius:10px;padding:10px;margin:8px 0;background:#161b22}}select{{background:#0d1117;color:#e6edf3;border:1px solid #30363d;padding:6px}}.muted{{color:#8b949e;font-size:13px}}</style></head><body>
<header><strong>{html.escape(title)}</strong>　<select id="chapter"></select> <span class="muted">点击证据可定位原文</span></header><main><div id="text"></div><aside><h3>本章事件</h3><div id="events"></div><h3>证据与实体</h3><div id="evidence"></div></aside></main>
<script>const D={raw};const sel=document.getElementById('chapter');D.chapters.forEach(c=>{{let o=document.createElement('option');o.value=c.chapter;o.textContent=`第${{c.chapter}}章 ${{c.title||''}}`;sel.appendChild(o)}});function esc(s){{return String(s??'').replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]))}}function render(){{let ch=Number(sel.value),c=D.chapters.find(x=>Number(x.chapter)===ch)||{{text:''}};let text=esc(c.text);let evs=D.evidence[String(ch)]||D.evidence[ch]||[];evs.slice().sort((a,b)=>String(b.quote||'').length-String(a.quote||'').length).forEach(e=>{{let q=esc(e.quote||'');if(q)text=text.replace(q,`<mark id="${{esc(e.id)}}">${{q}}</mark>`)}});document.getElementById('text').innerHTML=text;document.getElementById('events').innerHTML=(D.events[String(ch)]||D.events[ch]||[]).map(e=>`<div class=card><b>${{esc(e.title)}}</b><div class=muted>${{esc(e.type)}} · ${{esc((e.participants||[]).join('、'))}}</div></div>`).join('')||'<div class=muted>无结构化事件</div>';document.getElementById('evidence').innerHTML=evs.map(e=>`<div class=card><a href="#${{esc(e.id)}}" onclick="setTimeout(()=>document.getElementById('${{esc(e.id)}}')?.scrollIntoView({{behavior:'smooth',block:'center'}}),0)">${{esc(e.quote)}}</a><div class=muted>${{(D.refs[e.id]||[]).map(r=>esc(r.label)).join(' · ')}}</div></div>`).join('')||'<div class=muted>无证据</div>'}}sel.addEventListener('change',render);if(sel.options.length){{sel.selectedIndex=0;render()}}</script></body></html>'''
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--graph",required=True,type=Path);p.add_argument("--chapters-jsonl",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--cutoff",type=int);a=p.parse_args();g=json.loads(a.graph.read_text(encoding="utf-8"));g=filter_graph(g,a.cutoff) if a.cutoff is not None else g;chs=[c for c in load_chapters(a.chapters_jsonl) if a.cutoff is None or (isinstance(c.get("chapter"),int) and c["chapter"]<=a.cutoff)];title=str(g.get("metadata",{}).get("title") or "Novel reader");a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(build(payload(g,chs),title),encoding="utf-8");print(json.dumps({"output":str(a.output),"chapters":len(chs),"cutoff":a.cutoff},ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
