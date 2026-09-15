#!/usr/bin/env python3
"""Build the canonical unified, chapter-synchronized dashboard.

One slider creates one client-side snapshot object. Legacy graph/repository/arcs/
collections and all expansion panels read only that object. Entity names, prose,
attributes, relation status and derived panels are projected as-of the selected
chapter. A strict ``--cutoff`` closes the embedded payload before rendering.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from typing import Any

from derive_novel_views import build_views
from filter_graph_asof import filter_graph
from io_utils import atomic_write_text


def build_model(graph: dict[str, Any], protagonists=(), gap_threshold: int = 3, collections: dict[str, Any] | None = None, cutoff: int | None = None) -> dict[str, Any]:
    scoped = filter_graph(graph, cutoff, strict=True) if cutoff is not None else graph
    meta = scoped.get("metadata") if isinstance(scoped.get("metadata"), dict) else {}
    return {
        "graph": scoped,
        "views": build_views(scoped, protagonists, max(1, gap_threshold)),
        "collections": collections or {"collections": []},
        "metadata": {
            "title": meta.get("title"),
            "chapter_start": meta.get("chapter_start"),
            "chapter_end": meta.get("chapter_end"),
            "cutoff": cutoff,
            "temporal_provenance_gaps": meta.get("temporal_provenance_gaps", []),
        },
    }


def build_html(model: dict[str, Any]) -> str:
    payload = json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = html.escape(str(model.get("metadata", {}).get("title") or "Novel Knowledge Graph"))
    return TEMPLATE.replace("__PAYLOAD__", payload).replace("__TITLE__", title)


TEMPLATE = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__ · Dashboard</title><style>
:root{--b:#0d1117;--p:#161b22;--l:#30363d;--t:#e6edf3;--m:#8b949e;--a:#58a6ff}*{box-sizing:border-box}body{margin:0;background:var(--b);color:var(--t);font:13px system-ui}header{position:sticky;top:0;z-index:3;background:#0d1117f5;padding:12px 16px;border-bottom:1px solid var(--l)}h1{font-size:19px;margin:0 0 8px}.bar{display:flex;gap:10px;align-items:center}input{flex:1}nav{display:flex;gap:6px;overflow:auto;padding:7px 10px;background:var(--p);position:sticky;top:72px;z-index:2}button{background:#21262d;color:var(--t);border:1px solid var(--l);border-radius:7px;padding:6px 8px;white-space:nowrap}button.on{border-color:var(--a)}main{padding:14px;max-width:1700px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}.card{background:var(--p);border:1px solid var(--l);border-radius:9px;padding:9px;margin:6px 0}.metric{font-size:24px;font-weight:700}.muted{color:var(--m)}.scroll{overflow:auto;max-height:72vh;border:1px solid var(--l);border-radius:8px}table{width:100%;border-collapse:collapse;background:var(--p)}th,td{padding:7px;border-bottom:1px solid var(--l);vertical-align:top;text-align:left}th{position:sticky;top:0;background:#21262d}.graph{height:60vh;min-height:420px;border:1px solid var(--l);border-radius:9px}code{white-space:pre-wrap;font-size:11px}.warn{color:#f2cc60}</style><script src="cytoscape-3.34.3.min.js"></script></head><body>
<header><h1>__TITLE__ · 统一时序 Dashboard</h1><div class="bar"><b>章节 <span id="cl"></span></b><input id="ch" type="range" step="1"><span id="state" class="muted"></span></div></header><nav id="tabs"></nav><main id="main"></main><script>
const B=__PAYLOAD__,G=B.graph||{},V=B.views||{},C=B.collections||{collections:[]},META=G.metadata||{};
const A=x=>Array.isArray(x)?x:[],N=x=>Number.isInteger(x)?x:null,E=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const min=Number(B.metadata?.chapter_start??V.metadata?.chapter_start??0),max=Number(B.metadata?.chapter_end??V.metadata?.chapter_end??0),sl=document.getElementById('ch'),tabsEl=document.getElementById('tabs'),mainEl=document.getElementById('main');sl.min=min;sl.max=max;sl.value=max;let S=null,active='overview',cy=null;
function interval(r,c,a='valid_from',z='valid_to'){const s=N(r?.[a])??0,e=N(r?.[z]);return s<=c&&(e===null||c<=e)}
function nestedChapter(map,id,key){if(!map||typeof map!=='object')return null;const n=map[id];if(n&&typeof n==='object')return N(n[key]);return key==null?N(n):N(map[key])}
function histValue(rows,c,keys){const h=A(rows).filter(x=>(N(x.valid_from)??N(x.chapter)??1e15)<=c).sort((a,b)=>(N(a.valid_from)??N(a.chapter)??0)-(N(b.valid_from)??N(b.chapter)??0));if(!h.length)return undefined;const r=h.at(-1);for(const k of keys)if(Object.hasOwn(r,k))return structuredClone(r[k]);return undefined}
function nameAt(e,c){const h=histValue(e.name_history,c,['name','value']);if(typeof h==='string')return h;const first=N(e.name_first_chapter)??nestedChapter(META.name_first_chapter,e.id,null);if(first!==null)return first<=c?e.name:`[${e.type}:${e.id}]`;return c>=max?e.name:`[${e.type}:${e.id}]`}
function proseAt(e,field,c){const h=histValue(e[`${field}_history`],c,[field,'value','text']);if(h!==undefined)return h;const first=N(e[`${field}_chapter`])??N(e[`${field}_first_chapter`])??nestedChapter(META[`${field}_first_chapter`],e.id,null);if(first!==null)return first<=c?e[field]:undefined;return c>=max?e[field]:undefined}
function attrsAt(e,c){const out={};for(const r of [...A(e.attribute_history),...A(e.attributes_history)].sort((a,b)=>(N(a.chapter)??N(a.valid_from)??0)-(N(b.chapter)??N(b.valid_from)??0))){const at=N(r.chapter)??N(r.valid_from);if(at!==null&&at<=c){const k=r.key??r.attribute;if(typeof k==='string')out[k]=structuredClone(r.value)}}for(const [k,v] of Object.entries(e.attributes||{})){if(Object.hasOwn(out,k))continue;const first=nestedChapter(META.attribute_first_chapter,e.id,k);if((first!==null&&first<=c)||(first===null&&c>=max))out[k]=structuredClone(v)}return out}
function entityAt(e,c){const x={...e,name:nameAt(e,c),attributes:attrsAt(e,c)};const summary=proseAt(e,'summary',c),description=proseAt(e,'description',c);if(summary===undefined)delete x.summary;else x.summary=summary;if(description===undefined)delete x.description;else x.description=description;delete x.current_state;return x}
function safeName(id,names){return names[id]??id??''}function rewriteNames(text,names){let s=String(text??'');for(const e of A(G.entities)){if(typeof e.name==='string'&&e.name&&names[e.id]&&names[e.id]!==e.name)s=s.split(e.name).join(names[e.id])}return s}
function commitAt(x,c){x=structuredClone(x);x.observations=A(x.observations).filter(o=>(N(o.chapter)??0)<=c).sort((a,b)=>(N(a.chapter)??0)-(N(b.chapter)??0));if(N(x.resolved_chapter)!==null&&x.resolved_chapter>c){x.resolved_chapter=null;x.resolution=null}const s=[...x.observations].reverse().find(o=>typeof o.status==='string')?.status;if(s)x.status=s;else if(!x.resolved_chapter)x.status='active';return x}
function relationAt(x,c){x=structuredClone(x);const end=N(x.valid_to);x.observations=A(x.observations).filter(o=>(N(o.chapter)??0)<=c).sort((a,b)=>(N(a.chapter)??0)-(N(b.chapter)??0));if(end!==null&&end>c)delete x.valid_to;const s=[...x.observations].reverse().find(o=>typeof o.status==='string')?.status;if(s)x.status=s;else if(end!==null&&end>c&&!['active','uncertain',null].includes(x.status))x.status='active';return x}
function resourceAt(x,c,names){x=structuredClone(x);x.name=safeName(x.item_id,names)||x.name;x.role_history=A(x.role_history).filter(r=>(N(r.chapter)??0)<=c&&interval(r,c,'chapter','valid_to')).map(r=>({...r,entity:safeName(r.entity_id,names),location:safeName(r.location_id,names)}));x.quantity_history=A(x.quantity_history).filter(r=>(N(r.chapter)??0)<=c);x.current_quantities={};for(const r of x.quantity_history)if(r.entity_id)x.current_quantities[r.entity_id]=r.after;x.acquisition_count=x.role_history.filter(r=>r.action==='gained').length;return x}
function expr(q,s,stack=[]){const all=new Set(s.graph.entities.map(e=>e.id));if(!q||typeof q!=='object')return new Set();if(q.explicit_members)return new Set(A(q.explicit_members).filter(x=>all.has(x)));if(q.type)return new Set(s.graph.entities.filter(e=>e.type===q.type).map(e=>e.id));if(q.arc){const a=s.arcs.find(x=>x.id===q.arc);return new Set(A(a?.entity_ids).filter(x=>all.has(x)))}if(q.collection){if(stack.includes(q.collection))return new Set();const c=A(C.collections).find(x=>x.id===q.collection);return c?expr(c.expression,s,[...stack,q.collection]):new Set()}if(q.and){const ss=A(q.and).map(x=>expr(x,s,stack));return ss.length?new Set([...ss[0]].filter(x=>ss.slice(1).every(z=>z.has(x)))):new Set()}if(q.or){const o=new Set();for(const z of A(q.or).map(x=>expr(x,s,stack)))for(const x of z)o.add(x);return o}if(q.not){const bad=expr(q.not,s,stack);return new Set([...all].filter(x=>!bad.has(x)))}if(q.relation){const spec=typeof q.relation==='string'?{type:q.relation}:q.relation,o=new Set();for(const r of s.graph.relations){if((spec.type||spec.relation_type)&&r.relation_type!==(spec.type||spec.relation_type))continue;o.add(r.source_id);o.add(r.target_id)}return new Set([...o].filter(x=>all.has(x)))}return new Set()}
function snapshotAt(c){
 const entities=A(G.entities).filter(e=>(N(e.first_chapter)??0)<=c).map(e=>entityAt(e,c)),ids=new Set(entities.map(e=>e.id)),names=Object.fromEntries(entities.map(e=>[e.id,e.name]));
 const relations=A(G.relations).filter(r=>(N(r.valid_from)??0)<=c&&ids.has(r.source_id)&&ids.has(r.target_id)&&interval(r,c)).map(r=>relationAt(r,c)),relationById=Object.fromEntries(relations.map(r=>[r.id,r])),events=A(G.events).filter(e=>(N(e.chapter)??0)<=c),arcs=A(G.story_arcs).filter(a=>(N(a.chapter_start)??0)<=c).map(a=>N(a.chapter_end)!==null&&a.chapter_end>c?{...a,chapter_end:null,status:['closed','complete','completed','resolved'].includes(a.status)?'active':a.status}:a);
 const v={...V};
 v.achievements=A(V.achievements).filter(x=>(N(x.chapter)??0)<=c).map(x=>({...x,title:rewriteNames(x.title,names)}));
 v.combat_records=A(V.combat_records).filter(x=>(N(x.chapter)??0)<=c).map(x=>({...x,protagonist:safeName(x.protagonist_id,names),opponents:A(x.opponent_ids).map(id=>safeName(id,names)),location:safeName(x.location_id,names)}));
 v.resources={items:A(V.resources?.items).map(x=>resourceAt(x,c,names)).filter(x=>x.role_history.length||x.quantity_history.length||x.rarity||x.supply)};
 v.skills=A(V.skills).map(x=>({...x,name:safeName(x.skill_id,names)||x.name,holders:A(x.holders).filter(h=>interval(h,c)).map(h=>({...h,entity:safeName(h.entity_id,names)}))}));
 v.commitments=A(V.commitments).filter(x=>(N(x.created_chapter)??0)<=c).map(x=>{const q=commitAt(x,c);q.promisors=A(q.promisor_ids).map(id=>safeName(id,names));q.counterparties=A(q.counterparty_ids).map(id=>safeName(id,names));return q});
 v.favor_ledger=A(V.favor_ledger).filter(x=>(N(x.valid_from)??0)<=c).map(x=>{const r=relationById[x.relation_id];return {...x,debtor:safeName(x.debtor_id,names),creditor:safeName(x.creditor_id,names),status:r?.status??x.status,valid_to:r?.valid_to}});
 v.knowledge={secrets:A(V.knowledge?.secrets).map(s=>({...s,secret:safeName(s.secret_id,names),people:A(s.people).map(p=>({...p,entity:safeName(p.entity_id,names),history:A(p.history).filter(h=>(N(h.chapter)??0)<=c)})).filter(p=>p.history.length)})).filter(s=>s.people.length),propagation:A(V.knowledge?.propagation).filter(x=>(N(x.chapter)??0)<=c).map(x=>({...x,secret:safeName(x.secret_id,names),from:safeName(x.from_id,names),to:safeName(x.to_id,names)}))};
 v.foreshadowing={rows:A(V.foreshadowing?.rows).filter(x=>(N(x.planted_chapter)??0)<=c).map(x=>N(x.payoff_chapter)!==null&&x.payoff_chapter>c?{...x,payoff_chapter:null,span:null,status:'open'}:x)};v.foreshadowing.unresolved=v.foreshadowing.rows.filter(x=>N(x.payoff_chapter)===null);
 v.levels={series:A(V.levels?.series).map(s=>({...s,entity:safeName(s.entity_id,names),facets:Object.fromEntries(Object.entries(s.facets||{}).map(([k,z])=>[k,A(z).filter(x=>(N(x.chapter)??0)<=c)]))})).filter(s=>Object.values(s.facets).some(z=>z.length))};
 v.chapter_rhythm={chapters:A(V.chapter_rhythm?.chapters).filter(x=>(N(x.chapter)??0)<=c).map(x=>({...x,pov:A(x.pov_entity_ids).map(id=>safeName(id,names))}))};
 v.romance={routes:A(V.romance?.routes).map(r=>({...r,character:safeName(r.character_id,names),milestones:A(r.milestones).filter(m=>(N(m.chapter)??0)<=c)})).filter(r=>r.milestones.length)};
 v.mortality={events:A(V.mortality?.events).filter(x=>(N(x.chapter)??0)<=c).map(x=>({...x,entity:safeName(x.entity_id,names),killers:A(x.killer_ids).map(id=>safeName(id,names))}))};
 v.economy={transactions:A(V.economy?.transactions).filter(x=>(N(x.chapter)??0)<=c),wealth_changes:A(V.economy?.wealth_changes).filter(x=>(N(x.chapter)??0)<=c)};
 v.rules={concepts:A(V.rules?.concepts).filter(x=>(N(x.first_chapter)??0)<=c).map(x=>{const e=entities.find(y=>y.id===x.id);return {...x,name:safeName(x.id,names),summary:e?.summary}}),enforcement_events:A(V.rules?.enforcement_events).filter(x=>(N(x.chapter)??0)<=c)};
 v.narrative={character_voice:A(V.narrative?.character_voice).map(x=>({...x,entity:safeName(x.entity_id,names),observations:A(x.observations).filter(o=>{const s=N(o.chapter)??N(o.chapter_start)??N(o.valid_from);return s!==null&&s<=c})})).filter(x=>x.observations.length),author_style:A(V.narrative?.author_style).filter(o=>{const s=N(o.chapter)??N(o.chapter_start)??N(o.valid_from);return s!==null&&s<=c})};
 const s={chapter:c,graph:{entities,relations,events},arcs,views:v,names};s.collections=A(C.collections).map(x=>({id:x.id,label:x.label,members:[...expr(x.expression,s)]}));return s
}
const panels=[['overview','总览'],['graph','关系图'],['repo','仓库'],['arcs','剧情线'],['collections','集合'],['achievements','成就'],['combat','战绩'],['resources','资源'],['skills','技能'],['commitments','承诺'],['knowledge','秘密'],['foreshadowing','伏笔'],['levels','战力'],['rhythm','节奏'],['romance','感情'],['mortality','生死'],['economy','经济'],['rules','规则'],['narrative','写法'],['audit','审计']];
for(const [id,t] of panels){const b=document.createElement('button');b.textContent=t;b.dataset.panel=id;b.onclick=()=>{active=id;document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));render()};if(id==='overview')b.className='on';tabsEl.appendChild(b)}
function table(h,rows){if(!rows.length)return '<div class="card muted">当前章节无数据</div>';return `<div class=scroll><table><thead><tr>${h.map(x=>`<th>${E(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(x=>`<td>${x??''}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}function set(x){mainEl.innerHTML=`<section>${x}</section>`}
function render(){const v=S.views;if(active==='overview'){const open=v.commitments.filter(x=>['active','partially_fulfilled','uncertain'].includes(x.status)),metrics=[[S.graph.entities.length,'实体'],[S.graph.events.length,'事件'],[v.achievements.length,'成就'],[v.combat_records.filter(x=>x.result==='victory').length,'胜场'],[open.length,'未完承诺'],[v.foreshadowing.unresolved.length,'未收伏笔']];set(`<div class=grid>${metrics.map(x=>`<div class=card><div class=metric>${x[0]}</div><div class=muted>${x[1]}</div></div>`).join('')}</div>`);return}
 if(active==='graph'){set('<div id="cy" class=graph></div>');const ns=S.graph.entities.slice(0,100).map(e=>({data:{id:e.id,label:e.name}})),keep=new Set(ns.map(x=>x.data.id)),es=S.graph.relations.filter(r=>keep.has(r.source_id)&&keep.has(r.target_id)).slice(0,180).map(r=>({data:{id:r.id,source:r.source_id,target:r.target_id,label:r.relation_type}}));if(cy)cy.destroy();if(typeof cytoscape!=='undefined')cy=cytoscape({container:document.getElementById('cy'),elements:[...ns,...es],style:[{selector:'node',style:{label:'data(label)','font-size':10,'background-color':'#58a6ff','color':'#fff'}},{selector:'edge',style:{'target-arrow-shape':'triangle','curve-style':'bezier','line-color':'#6e7681','target-arrow-color':'#6e7681'}}],layout:{name:'cose',animate:false}});return}
 if(active==='repo'){set(table(['类型','名称','摘要','属性'],S.graph.entities.map(e=>[E(e.type),E(e.name),E(e.summary||''),`<code>${E(JSON.stringify(e.attributes||{}))}</code>`])));return}
 if(active==='arcs'){set(table(['剧情线','起始','结束','状态'],S.arcs.map(a=>[E(a.title||a.id),a.chapter_start,a.chapter_end??'',E(a.status||'')])));return}
 if(active==='collections'){set(table(['集合','成员数','成员'],S.collections.map(c=>[E(c.label||c.id),c.members.length,E(c.members.map(id=>S.names[id]||id).join('、'))])));return}
 if(active==='achievements'){set(table(['章','类别','成就'],v.achievements.map(x=>[x.chapter,E(x.category),E(x.title)])));return}
 if(active==='combat'){set(table(['章','对手','结果','当时境界'],v.combat_records.map(x=>[x.chapter,E(A(x.opponents).join('、')),E(x.result),`<code>${E(JSON.stringify(x.protagonist_level||{}))}</code>`])));return}
 if(active==='resources'){set(table(['资源','稀有度','获得次数','当前数量'],v.resources.items.map(x=>[E(x.name),E(x.rarity||''),x.acquisition_count,`<code>${E(JSON.stringify(x.current_quantities||{}))}</code>`])));return}
 if(active==='skills'){set(table(['技能','分类','当前掌握'],v.skills.map(x=>[E(x.name),E(A(x.categories).join('、')),E(A(x.holders).map(h=>h.entity).join('、'))])));return}
 if(active==='commitments'){set(table(['建立章','内容','状态','解决章'],v.commitments.map(x=>[x.created_chapter,E(x.terms),E(x.status),x.resolved_chapter??''])));return}
 if(active==='knowledge'){const rows=[];for(const s of v.knowledge.secrets)for(const p of A(s.people))rows.push([E(s.secret),E(p.entity),p.history.length]);set(table(['秘密','人物','知情变化'],rows));return}
 if(active==='foreshadowing'){set(table(['伏笔','埋设','回收','状态'],v.foreshadowing.rows.map(x=>[E(x.label),x.planted_chapter,x.payoff_chapter??'',E(x.status)])));return}
 if(active==='levels'){const rows=[];for(const s of v.levels.series)for(const [k,h] of Object.entries(s.facets||{})){const z=A(h).at(-1);if(z)rows.push([E(s.entity),E(k),z.chapter,E(JSON.stringify(z.after))])}set(table(['人物','轴','章','当前值'],rows));return}
 if(active==='rhythm'){set(table(['章','事件','POV','断章'],v.chapter_rhythm.chapters.slice(-250).map(x=>[x.chapter,x.event_total,E(A(x.pov).join('、')),E(x.cliffhanger_type||'')])));return}
 if(active==='romance'){const rows=[];for(const x of v.romance.routes)for(const m of A(x.milestones))rows.push([E(x.character),m.chapter,E(m.kind)]);set(table(['人物','章','里程碑'],rows));return}
 if(active==='mortality'){set(table(['章','人物','死因'],v.mortality.events.map(x=>[x.chapter,E(x.entity),E(x.cause||'')])));return}
 if(active==='economy'){set(table(['章','交易','金额'],v.economy.transactions.map(x=>[x.chapter,E(x.title||x.event_id),E(x.amount??'')])));return}
 if(active==='rules'){set(table(['规则','分类','摘要'],v.rules.concepts.map(x=>[E(x.name),E(A(x.categories).join('、')),E(x.summary||'')])));return}
 if(active==='narrative'){const rows=[];for(const x of v.narrative.character_voice)for(const o of A(x.observations))rows.push([E(x.entity),N(o.chapter)??N(o.chapter_start)??'',E(o.observation||o.summary||o.text||'')]);set(table(['人物','章','声音观察'],rows));return}
 const gaps=A(B.metadata?.temporal_provenance_gaps);set(`<div class=card><b>契约：</b>${V.contract_summary?.valid?'通过':'存在问题'} · errors ${V.contract_summary?.error_count??0} · warnings ${V.contract_summary?.warning_count??0}</div><div class="card ${gaps.length?'warn':'muted'}">构建时无时间来源字段：${gaps.length}</div>`)}
function refresh(){const c=Number(sl.value);document.getElementById('cl').textContent=c;S=snapshotAt(c);document.getElementById('state').textContent=`统一快照 · ${S.graph.entities.length} 实体 · ${S.graph.events.length} 事件${B.metadata?.cutoff!=null?' · cutoff '+B.metadata.cutoff:''}`;render()}sl.addEventListener('input',refresh);refresh();
</script></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--collection-manifest", type=Path)
    parser.add_argument("--cutoff", type=int)
    parser.add_argument("--protagonist-id", action="append", default=[])
    parser.add_argument("--relation-gap-threshold", type=int, default=3)
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    collections = json.loads(args.collection_manifest.read_text(encoding="utf-8")) if args.collection_manifest else None
    model = build_model(graph, args.protagonist_id, args.relation_gap_threshold, collections, args.cutoff)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "dashboard.html"
    atomic_write_text(out, build_html(model))
    asset = Path(__file__).resolve().parent.parent / "assets" / "cytoscape-3.34.3.min.js"
    if asset.exists():
        shutil.copy2(asset, args.output_dir / asset.name)
    print(json.dumps({"dashboard": str(out), "cutoff": args.cutoff, "unified": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
