#!/usr/bin/env python3
"""Build a spoiler-safe source reader with overlap-aware evidence highlighting."""
from __future__ import annotations
import argparse, html, json
from pathlib import Path
from typing import Any
from filter_graph_asof import filter_graph


def load_chapters(index:Path, cutoff:int|None=None)->list[dict[str,Any]]:
    out=[]; missing=[]
    for line_no,line in enumerate(index.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip(): continue
        try: row=json.loads(line)
        except json.JSONDecodeError as exc: raise ValueError(f'chapters jsonl line {line_no}: {exc}') from exc
        ch=row.get('chapter')
        if not isinstance(ch,int): raise ValueError(f'chapters jsonl line {line_no}: chapter must be integer')
        if cutoff is not None and ch>cutoff: continue
        p=Path(row.get('text_path',''))
        if not p.is_file(): missing.append({'chapter':ch,'text_path':str(p)}); continue
        out.append({'chapter':ch,'title':row.get('title'),'text':p.read_text(encoding='utf-8')})
    if missing: raise FileNotFoundError('missing prepared chapter text: '+json.dumps(missing,ensure_ascii=False))
    return out


def highlight(text:str,evidence:list[dict[str,Any]])->str:
    intervals=[]
    for e in evidence:
        q=e.get('quote'); eid=e.get('id')
        if not isinstance(q,str) or not q or not isinstance(eid,str): continue
        start=0
        while True:
            pos=text.find(q,start)
            if pos<0: break
            intervals.append((pos,pos+len(q),eid)); start=pos+max(1,len(q))
    if not intervals: return html.escape(text)
    cuts={0,len(text)}
    for a,b,_ in intervals: cuts.add(a); cuts.add(b)
    points=sorted(cuts); pieces=[]
    for a,b in zip(points,points[1:]):
        if a==b: continue
        ids=sorted({eid for x,y,eid in intervals if x < b and y > a})
        chunk=html.escape(text[a:b])
        if ids: pieces.append(f'<mark data-eids="{html.escape(" ".join(ids),quote=True)}">{chunk}</mark>')
        else: pieces.append(chunk)
    return ''.join(pieces)


def payload(graph:dict[str,Any],chapters:list[dict[str,Any]])->dict[str,Any]:
    names={e.get('id'):e.get('name') for e in graph.get('entities',[]) if isinstance(e,dict)}; evid_by_ch={}
    for e in graph.get('evidence',[]):
        if isinstance(e,dict) and isinstance(e.get('chapter'),int): evid_by_ch.setdefault(e['chapter'],[]).append(e)
    event_by_ch={}
    for e in graph.get('events',[]):
        if isinstance(e,dict) and isinstance(e.get('chapter'),int): event_by_ch.setdefault(e['chapter'],[]).append({'id':e.get('id'),'title':e.get('title'),'type':e.get('type'),'participants':[names.get(x,x) for x in e.get('participant_ids',[]) if isinstance(x,str)]})
    refs={}
    for key in ('entities','relations','state_changes','foreshadowing','commitments','item_roles','romance_routes'):
        for r in graph.get(key,[]):
            if not isinstance(r,dict): continue
            for evid in r.get('evidence_ids',[]) if isinstance(r.get('evidence_ids'),list) else []:
                refs.setdefault(evid,[]).append({'kind':key,'id':r.get('id'),'label':names.get(r.get('entity_id')) or names.get(r.get('source_id')) or names.get(r.get('character_id')) or r.get('label') or r.get('terms') or r.get('id')})
    rendered=[]
    for c in chapters:
        ev=evid_by_ch.get(c['chapter'],[]); rendered.append({'chapter':c['chapter'],'title':c.get('title'),'html':highlight(c['text'],ev)})
    return {'chapters':rendered,'evidence':evid_by_ch,'events':event_by_ch,'refs':refs}


def build(data:dict[str,Any],title:str)->str:
    raw=json.dumps(data,ensure_ascii=False).replace('</','<\\/')
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>body{{margin:0;font-family:system-ui;background:#0d1117;color:#e6edf3}}header{{position:sticky;top:0;background:#161b22;padding:10px 18px;border-bottom:1px solid #30363d;z-index:2}}main{{display:grid;grid-template-columns:minmax(0,2fr) minmax(320px,1fr);height:calc(100vh - 58px)}}#text{{overflow:auto;padding:24px;white-space:pre-wrap;line-height:1.9;font-family:ui-serif,serif}}aside{{overflow:auto;border-left:1px solid #30363d;padding:16px}}mark{{background:#8a6d1d;color:#fff;padding:1px 0}}mark[data-eids*=" "]{{box-shadow:inset 0 -3px #58a6ff}}.card{{border:1px solid #30363d;border-radius:10px;padding:10px;margin:8px 0;background:#161b22}}select{{background:#0d1117;color:#e6edf3;border:1px solid #30363d;padding:6px}}.muted{{color:#8b949e;font-size:13px}}a{{color:#79c0ff}}</style></head><body><header><strong>{html.escape(title)}</strong>　<select id="chapter"></select> <span class="muted">重叠证据会共享高亮区；点击证据定位原文</span></header><main><div id="text"></div><aside><h3>本章事件</h3><div id="events"></div><h3>证据与实体</h3><div id="evidence"></div></aside></main><script>const D={raw};const sel=document.getElementById('chapter');const esc=s=>String(s??'').replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));D.chapters.forEach(c=>{{let o=document.createElement('option');o.value=c.chapter;o.textContent=`第${{c.chapter}}章 ${{c.title||''}}`;sel.appendChild(o)}});function focusEvidence(id){{const q=`mark[data-eids~="${{CSS.escape(id)}}"]`;document.querySelector(q)?.scrollIntoView({{behavior:'smooth',block:'center'}})}}function render(){{const ch=Number(sel.value),c=D.chapters.find(x=>Number(x.chapter)===ch)||{{html:''}},evs=D.evidence[String(ch)]||D.evidence[ch]||[];document.getElementById('text').innerHTML=c.html;document.getElementById('events').innerHTML=(D.events[String(ch)]||D.events[ch]||[]).map(e=>`<div class=card><b>${{esc(e.title)}}</b><div class=muted>${{esc(e.type)}} · ${{esc((e.participants||[]).join('、'))}}</div></div>`).join('')||'<div class=muted>无结构化事件</div>';document.getElementById('evidence').innerHTML=evs.map(e=>`<div class=card><a href="javascript:void(0)" data-eid="${{esc(e.id)}}">${{esc(e.quote)}}</a><div class=muted>${{(D.refs[e.id]||[]).map(r=>esc(r.label)).join(' · ')}}</div></div>`).join('')||'<div class=muted>无证据</div>';document.querySelectorAll('[data-eid]').forEach(a=>a.onclick=()=>focusEvidence(a.dataset.eid))}}sel.addEventListener('change',render);if(sel.options.length){{sel.selectedIndex=0;render()}}</script></body></html>'''


def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--graph',required=True,type=Path);p.add_argument('--chapters-jsonl',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--cutoff',type=int);a=p.parse_args();g=json.loads(a.graph.read_text(encoding='utf-8'));g=filter_graph(g,a.cutoff,strict=True) if a.cutoff is not None else g;chs=load_chapters(a.chapters_jsonl,a.cutoff);title=str(g.get('metadata',{}).get('title') or 'Novel reader');a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(build(payload(g,chs),title),encoding='utf-8');print(json.dumps({'output':str(a.output),'chapters':len(chs),'cutoff':a.cutoff},ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
