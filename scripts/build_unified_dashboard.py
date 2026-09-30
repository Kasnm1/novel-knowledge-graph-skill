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

# The Chinese display vocabulary is shared with the legacy renderer; import it
# instead of keeping a second copy, so a new enum never renders as a raw English
# machine key in this dashboard.
from build_dashboard import DEFAULT_VOCABULARY, merge_vocabulary


def build_model(graph: dict[str, Any], protagonists=(), gap_threshold: int = 3, collections: dict[str, Any] | None = None, cutoff: int | None = None, vocabulary: dict[str, Any] | None = None) -> dict[str, Any]:
    scoped = filter_graph(graph, cutoff, strict=True) if cutoff is not None else graph
    meta = scoped.get("metadata") if isinstance(scoped.get("metadata"), dict) else {}
    if not isinstance(scoped.get("_display_vocabulary"), dict) or not scoped.get("_display_vocabulary"):
        vocab = merge_vocabulary(DEFAULT_VOCABULARY, meta.get("display_vocabulary", {}) if isinstance(meta.get("display_vocabulary"), dict) else {})
        if vocabulary:
            vocab = merge_vocabulary(vocab, vocabulary)
        scoped["_display_vocabulary"] = vocab
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
:root{--b:#0d1117;--p:#161b22;--l:#30363d;--t:#e6edf3;--m:#8b949e;--a:#58a6ff}*{box-sizing:border-box}body{margin:0;background:var(--b);color:var(--t);font:13px system-ui}header{position:sticky;top:0;z-index:3;background:#0d1117f5;padding:12px 16px;border-bottom:1px solid var(--l)}h1{font-size:19px;margin:0 0 8px}.bar{display:flex;gap:10px;align-items:center}input{flex:1}nav{display:flex;gap:6px;overflow:auto;padding:7px 10px;background:var(--p);position:sticky;top:72px;z-index:2}button{background:#21262d;color:var(--t);border:1px solid var(--l);border-radius:7px;padding:6px 8px;white-space:nowrap}button.on{border-color:var(--a)}main{padding:14px;max-width:1700px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}.card{background:var(--p);border:1px solid var(--l);border-radius:9px;padding:9px;margin:6px 0}.metric{font-size:24px;font-weight:700}.muted{color:var(--m)}.scroll{overflow:auto;max-height:72vh;border:1px solid var(--l);border-radius:8px}table{width:100%;border-collapse:collapse;background:var(--p)}th,td{padding:7px;border-bottom:1px solid var(--l);vertical-align:top;text-align:left}
table td:first-child,table th:first-child{width:1%;white-space:nowrap;padding-right:14px}
table td:nth-child(2),table th:nth-child(2){white-space:nowrap;padding-right:14px}
table td:last-child,table th:last-child{width:auto}th{position:sticky;top:0;background:#21262d}.graph{height:60vh;min-height:420px;border:1px solid var(--l);border-radius:9px}code{white-space:pre-wrap;font-size:11px}
.warn{color:#f2cc60}#shell{display:grid;grid-template-columns:minmax(0,1fr);align-items:start}
body.detail-open #shell{grid-template-columns:minmax(0,1fr) var(--dw,430px);gap:12px}
aside.detail{overflow:auto;border-left:1px solid var(--l);background:var(--p);padding:12px;display:none}
aside.detail.on{display:block;max-height:calc(100vh - 110px)}
.detail-resize{position:absolute;left:0;top:0;bottom:0;width:6px;cursor:col-resize}
.eyebrow{color:var(--m);font-size:11px;letter-spacing:.04em;margin-bottom:4px}
aside.detail h2{font-size:17px;margin:0 0 8px}
aside.detail h3{font-size:14px;margin:14px 0 6px}
.summary{color:var(--t);line-height:1.7;margin:6px 0}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0}
.chip{background:#21262d;border:1px solid var(--l);border-radius:999px;padding:2px 8px;font-size:11px;color:var(--m)}
.entity-summary-card{margin:10px 0;padding:11px;border:1px solid var(--l);border-radius:11px;background:#161b22}
.entity-summary-scope{color:var(--a);font-size:11px;font-weight:650}
.entity-summary-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px}
.entity-summary-grid div{padding:6px;border-radius:8px;background:#0d1117;text-align:center}
.entity-summary-grid b{display:block;font-size:16px}
.entity-summary-grid span{font-size:11px;color:var(--m)}
.entity-highlights{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.entity-highlights span{background:#0d1117;border:1px solid var(--l);border-radius:7px;padding:3px 8px;font-size:11px}
.entity-latest{color:var(--m);font-size:11px;margin-top:7px}
.section{margin:14px 0 0}
.section>h3{font-size:13px;margin:0 0 7px;color:var(--m);font-weight:500}
.row{display:grid;grid-template-columns:96px minmax(0,1fr);gap:8px;padding:5px 0;border-bottom:1px solid #21262d}
.row b{color:var(--m);font-weight:500;font-size:12px}
.row span{font-size:12px;line-height:1.6;word-break:break-word}
.history-item{padding:7px 0;border-bottom:1px solid #21262d}
.history-item b{font-size:12px}
.history-item p{margin:3px 0 0;font-size:12px;color:var(--m);line-height:1.6}
.quote{border-left:2px solid #30363d;padding:4px 0 4px 9px;margin:5px 0;font-size:12px;line-height:1.65}
.quote small{display:block;color:var(--m);font-size:11px;margin-top:2px}
.quote-preview{display:grid;grid-template-columns:88px minmax(0,1fr);gap:8px;padding:4px 0;font-size:12px;line-height:1.6}
.quote-preview b{color:var(--m);font-weight:500;font-size:11px}
.evidence-summary{color:var(--m);font-size:11px;margin:4px 0 6px}
.history-more{margin-top:6px}
.history-more summary{cursor:pointer;color:var(--a);font-size:11px;padding:3px 0}
.category-empty,.entry-meta{color:var(--m);font-size:12px;margin:5px 0}
details.category{border:1px solid var(--l);border-radius:9px;margin:7px 0;background:#0d1117}
details.category>summary{padding:8px 10px;cursor:pointer;display:flex;flex-wrap:wrap;gap:8px;align-items:baseline}
.category-title{font-weight:500;font-size:13px}
details.category>summary small{color:var(--m);font-size:11px;flex:1}
.category-preview{color:#5f6b7d;font-size:11px}
.category-body{padding:0 10px 10px}
.category-subtitle{font-size:11px;color:var(--m);margin:9px 0 4px;padding-top:7px;border-top:1px solid #21262d}
.category-subtitle.current{color:var(--a);border-top:none}
.entry{padding:7px 0;border-bottom:1px solid #21262d}
.entry-name{font-size:13px;margin:0 0 3px;font-weight:500;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.entry-dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.entry-kind{font-size:11px;color:var(--m);font-weight:400}
.entry-badge{background:#1f6feb33;color:#79c0ff;border-radius:5px;padding:1px 6px;font-size:11px;font-weight:400}
.entry-lines{margin-top:4px}
.entry-line{display:grid;grid-template-columns:150px minmax(0,1fr);gap:8px;padding:2px 0;font-size:12px;line-height:1.6}
.entry-line b{color:var(--m);font-weight:500;font-size:11px}
.entry-reasons{margin-top:5px}
.entry-reasons summary{cursor:pointer;color:var(--a);font-size:11px}
.entry-reason{font-size:11px;color:var(--m);margin:4px 0;line-height:1.6}
.change-values{color:var(--m)}
.empty-value{color:#5f6b7d}
.level-strip{display:flex;flex-wrap:wrap;gap:7px;margin:8px 0}
.level-card{background:#0d1117;border:1px solid var(--l);border-radius:9px;padding:7px 10px;min-width:104px}
.level-card .level-axis{display:block;color:var(--m);font-size:11px}
.level-card b{display:block;font-size:14px;margin:2px 0}
.level-card small{color:#5f6b7d;font-size:11px}
.level-card[data-level-axis]{cursor:pointer}
.person-time{margin:12px 0;padding:10px;border:1px solid var(--l);border-radius:11px;background:#161b22}
.person-time-head{display:flex;justify-content:space-between;align-items:baseline;font-size:12px;margin-bottom:6px}
.person-time .time-dots{position:relative;height:16px;margin:5px 0}
.time-dot{position:absolute;top:2px;width:9px;height:9px;padding:0;border-radius:50%;background:#30363d;border:1px solid #30363d;transform:translateX(-50%)}
.time-dot.past{background:#58a6ff;border-color:#58a6ff}
.time-dot.current{background:#f2cc60;border-color:#f2cc60;width:11px;height:11px;top:1px}
.time-nav{display:flex;gap:7px;margin-top:7px}
.time-nav button{flex:1;font-size:11px}
.time-nav button:disabled{opacity:.4}
.romance-card{border:1px solid var(--l);border-radius:9px;padding:9px;margin:6px 0;background:#161b22;cursor:pointer}
.romance-card h3{font-size:13px;margin:0 0 5px}
.romance-card p{margin:3px 0;font-size:11px;color:var(--m);line-height:1.6}
.milestone-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
.milestone{border:1px solid var(--l);border-radius:8px;padding:7px;background:#0d1117}
.milestone .ms-label{display:block;color:var(--m);font-size:11px}
.milestone .ms-value{display:block;font-size:12px;margin-top:3px}
.confidence-explicit{color:#56d364}.confidence-inferred{color:#d29922}.confidence-uncertain{color:#8b949e}
.repo-card{border:1px solid var(--l);border-radius:9px;padding:9px;margin:6px 0;background:#161b22;cursor:pointer}
.repo-card:hover{border-color:var(--a)}
.repo-card h4{margin:0 0 4px;font-size:13px;font-weight:500}
.repo-card p{margin:3px 0;font-size:11px;color:var(--m);line-height:1.6}
.repo-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px}
.filters{display:flex;flex-wrap:wrap;gap:7px;margin:9px 0}
.filters input,.filters select{font-size:12px;padding:5px 7px;background:#0d1117;color:var(--t);border:1px solid var(--l);border-radius:7px}
.filters input{flex:1;min-width:170px}
.pager{display:flex;gap:7px;align-items:center;justify-content:center;margin:11px 0;font-size:12px;color:var(--m)}
.bar-row{display:grid;grid-template-columns:150px minmax(0,1fr) 42px;gap:8px;align-items:center;padding:2px 0;font-size:11px}
.bar-track{background:#21262d;border-radius:3px;height:13px;position:relative;overflow:hidden}
.bar-fill{background:#1f6feb;height:100%;border-radius:3px}
.lane{display:grid;grid-template-columns:130px minmax(0,1fr);gap:8px;align-items:center;padding:2px 0;font-size:11px}
.lane-track{background:#21262d;border-radius:3px;height:15px;position:relative}
.lane-span{position:absolute;top:2px;height:11px;background:#1f6feb;border-radius:3px;overflow:hidden;white-space:nowrap;font-size:10px;line-height:11px;padding:0 3px;color:#fff}
</style><script src="cytoscape-3.34.3.min.js"></script></head><body>
<header><h1>__TITLE__ · 统一时序 Dashboard</h1><div class="bar"><b>章节 <span id="cl"></span></b><input id="ch" type="range" step="1"><span id="state" class="muted"></span></div></header><nav id="tabs"></nav><div id="shell"><main id="main"></main><aside class="detail"><div id="detail"></div></aside></div><script>
const B=__PAYLOAD__,G=B.graph||{},V=B.views||{},C=B.collections||{collections:[]},META=G.metadata||{};
const A=x=>Array.isArray(x)?x:[],N=x=>Number.isInteger(x)?x:null,E=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const min=Number(B.metadata?.chapter_start??V.metadata?.chapter_start??0),max=Number(B.metadata?.chapter_end??V.metadata?.chapter_end??0),sl=document.getElementById('ch'),tabsEl=document.getElementById('tabs'),mainEl=document.getElementById('main');sl.min=min;sl.max=max;sl.value=max;let active='overview',cy=null;
function interval(r,c,a='valid_from',z='valid_to'){const s=N(r?.[a])??0,e=N(r?.[z]);return s<=c&&(e===null||c<=e)}
function nestedChapter(map,id,key){if(!map||typeof map!=='object')return null;const n=map[id];if(n&&typeof n==='object')return N(n[key]);return key==null?N(n):N(map[key])}
function histValue(rows,c,keys){const h=A(rows).filter(x=>(N(x.valid_from)??N(x.chapter)??1e15)<=c).sort((a,b)=>(N(a.valid_from)??N(a.chapter)??0)-(N(b.valid_from)??N(b.chapter)??0));if(!h.length)return undefined;const r=h.at(-1);for(const k of keys)if(Object.hasOwn(r,k))return structuredClone(r[k]);return undefined}
function nameAt(e,c){const h=histValue(e.name_history,c,['name','value']);if(typeof h==='string')return h;const first=N(e.name_first_chapter)??nestedChapter(META.name_first_chapter,e.id,null);if(first!==null)return first<=c?e.name:`[${e.type}:${e.id}]`;return c>=max?e.name:`[${e.type}:${e.id}]`}
function proseAt(e,field,c){const h=histValue(e[`${field}_history`],c,[field,'value','text']);if(h!==undefined)return h;const first=N(e[`${field}_chapter`])??N(e[`${field}_first_chapter`])??nestedChapter(META[`${field}_first_chapter`],e.id,null);if(first!==null)return first<=c?e[field]:undefined;return c>=max?e[field]:undefined}
function attrsAt(e,c){const out={};for(const r of [...A(e.attribute_history),...A(e.attributes_history)].sort((a,b)=>(N(a.chapter)??N(a.valid_from)??0)-(N(b.chapter)??N(b.valid_from)??0))){const at=N(r.chapter)??N(r.valid_from);if(at!==null&&at<=c){const k=r.key??r.attribute;if(typeof k==='string')out[k]=structuredClone(r.value)}}for(const [k,v] of Object.entries(e.attributes||{})){if(Object.hasOwn(out,k))continue;const first=nestedChapter(META.attribute_first_chapter,e.id,k);if((first!==null&&first<=c)||(first===null&&c>=max))out[k]=structuredClone(v)}return out}
const entityAtCache=new Map();
function entityAt(e,c){const hit=entityAtCache.get(e.id);if(hit&&hit.c===c)return hit.v;const x={...e,name:nameAt(e,c),attributes:attrsAt(e,c)};const summary=proseAt(e,'summary',c),description=proseAt(e,'description',c);if(summary===undefined)delete x.summary;else x.summary=summary;if(description===undefined)delete x.description;else x.description=description;delete x.current_state;entityAtCache.set(e.id,{c,v:x});return x}
function safeName(id,names){return names[id]??id??''}function rewriteNames(text,names){let s=String(text??'');for(const e of A(G.entities)){if(typeof e.name==='string'&&e.name&&names[e.id]&&names[e.id]!==e.name)s=s.split(e.name).join(names[e.id])}return s}
function commitAt(x,c){x=structuredClone(x);x.observations=A(x.observations).filter(o=>(N(o.chapter)??0)<=c).sort((a,b)=>(N(a.chapter)??0)-(N(b.chapter)??0));if(N(x.resolved_chapter)!==null&&x.resolved_chapter>c){x.resolved_chapter=null;x.resolution=null}const s=[...x.observations].reverse().find(o=>typeof o.status==='string')?.status;if(s)x.status=s;else if(!x.resolved_chapter)x.status='active';return x}
function relationAt(x,c){x=structuredClone(x);const end=N(x.valid_to);x.observations=A(x.observations).filter(o=>(N(o.chapter)??0)<=c).sort((a,b)=>(N(a.chapter)??0)-(N(b.chapter)??0));if(end!==null&&end>c)delete x.valid_to;const s=[...x.observations].reverse().find(o=>typeof o.status==='string')?.status;if(s)x.status=s;else if(end!==null&&end>c&&!['active','uncertain',null].includes(x.status))x.status='active';return x}
function resourceAt(x,c,names){x=structuredClone(x);x.name=safeName(x.item_id,names)||x.name;x.role_history=A(x.role_history).filter(r=>(N(r.chapter)??0)<=c&&interval(r,c,'chapter','valid_to')).map(r=>({...r,entity:safeName(r.entity_id,names),location:safeName(r.location_id,names)}));x.quantity_history=A(x.quantity_history).filter(r=>(N(r.chapter)??0)<=c);x.current_quantities={};for(const r of x.quantity_history)if(r.entity_id)x.current_quantities[r.entity_id]=r.after;x.acquisition_count=x.role_history.filter(r=>r.action==='gained').length;return x}
function expr(q,s,stack=[]){const all=new Set(s.graph.entities.map(e=>e.id));if(!q||typeof q!=='object')return new Set();if(q.explicit_members)return new Set(A(q.explicit_members).filter(x=>all.has(x)));if(q.type)return new Set(s.graph.entities.filter(e=>e.type===q.type).map(e=>e.id));if(q.arc){const a=s.arcs.find(x=>x.id===q.arc);return new Set(A(a?.entity_ids).filter(x=>all.has(x)))}if(q.collection){if(stack.includes(q.collection))return new Set();const c=A(C.collections).find(x=>x.id===q.collection);return c?expr(c.expression,s,[...stack,q.collection]):new Set()}if(q.and){const ss=A(q.and).map(x=>expr(x,s,stack));return ss.length?new Set([...ss[0]].filter(x=>ss.slice(1).every(z=>z.has(x)))):new Set()}if(q.or){const o=new Set();for(const z of A(q.or).map(x=>expr(x,s,stack)))for(const x of z)o.add(x);return o}if(q.not){const bad=expr(q.not,s,stack);return new Set([...all].filter(x=>!bad.has(x)))}if(q.relation){const spec=typeof q.relation==='string'?{type:q.relation}:q.relation,o=new Set();for(const r of s.graph.relations){if((spec.type||spec.relation_type)&&r.relation_type!==(spec.type||spec.relation_type))continue;o.add(r.source_id);o.add(r.target_id)}return new Set([...o].filter(x=>all.has(x)))}return new Set()}

const ENUMS=(()=>{const m={};for(const g of Object.values(G._display_vocabulary||{})){if(g&&typeof g==='object'&&!Array.isArray(g))for(const [k,v] of Object.entries(g))if(typeof v==='string')m[k]=v}return m})();
function vocab(){return (G._display_vocabulary||{})}
function term(group,key){const v=vocab();return (v[group]&&v[group][key])||key||''}
const VATTR=(()=>{const v=vocab();return v.attribute_keys||{}})();
const attrKey=k=>VATTR[k]||k;
const cleanProse=t=>{if(typeof t!=='string')return t;let out=t;for(const [k,v] of Object.entries(ENUMS)){if(!k||k.length<3)continue;out=out.split(k).join(v)}return out};
function asOf(t){if(typeof t!=='string')return t==null?'':E(attrText(t));return E(cleanProse(t))}
function levelShape(v){return !!v&&typeof v==='object'&&!Array.isArray(v)&&('label' in v||'value' in v)}
function levelText(v){if(!levelShape(v))return '';const l=v.label!=null?String(v.label):'';const val=v.value;if(l)return l;return val==null?'':String(val)}
function attrText(v){if(v===null||v===undefined||v==='')return '无';if(typeof v==='boolean')return v?'是':'否';if(Array.isArray(v))return v.map(attrText).join('、');if(levelShape(v))return levelText(v);if(typeof v==='object'){const label=v.label!==undefined?v.label:v['名称'];if(label!==undefined&&label!==null&&label!==''){const range=v.range!==undefined?v.range:v['区间'];return Array.isArray(range)&&range.length===2?`${label}（${range[0]}—${range[1]}）`:String(label)}return Object.entries(v).map(([k,x])=>`${attrKey(k)}：${attrText(x)}`).join('；')}return String(v)}
function value(v){if(v===null||v===undefined||v==='')return '<span class="empty-value">无</span>';if(typeof v==='boolean')return v?'是':'否';if(levelShape(v)){const t=levelText(v);return t?asOf(t):'<span class="empty-value">无</span>'}if(typeof v==='object')return asOf(attrText(v));return asOf(v)}
const evidenceById=new Map(A(G.evidence).map(x=>[x.id,x]));
const entityById=new Map(A(G.entities).map(x=>[x.id,x]));
function uniqueEvidence(ids){return [...new Set(A(ids).filter(id=>evidenceById.has(id)))]}
function recordEvidence(records){return uniqueEvidence(A(records).flatMap(x=>A(x&&x.evidence_ids)))}
function nameOf(id){return S?(S.names[id]||entityById.get(id)?.name||id):(entityById.get(id)?.name||id)}
function evidenceHtml(ids){const rows=uniqueEvidence(ids).map(id=>evidenceById.get(id)).filter(Boolean).sort((a,b)=>(a.chapter??0)-(b.chapter??0));if(!rows.length)return '<p class="category-empty">暂无可追溯原文证据。</p>';return rows.map(e=>`<div class="quote">“${E(e.quote)}”<small>第 ${e.chapter} 章</small></div>`).join('')}
function compactEvidenceHtml(ids,limit=3){const rows=uniqueEvidence(ids).map(id=>evidenceById.get(id)).filter(Boolean).sort((a,b)=>(a.chapter??0)-(b.chapter??0));if(!rows.length)return '<p class="category-empty">暂无可追溯原文证据。</p>';const chs=rows.map(x=>x.chapter).filter(Number.isFinite);const range=chs.length?(Math.min(...chs)===Math.max(...chs)?`第 ${chs[0]} 章`:`第 ${Math.min(...chs)}—${Math.max(...chs)} 章`):'章节未定';const one=x=>`<div class="quote-preview"><b>第 ${x.chapter} 章</b><span title="${E(x.quote)}">“${E(x.quote)}”</span></div>`;return `<p class="evidence-summary">${rows.length} 条可追溯证据 · ${range}</p>${rows.slice(0,limit).map(one).join('')}${rows.length>limit?`<details class="history-more"><summary>展开其余 ${rows.length-limit} 条证据</summary>${rows.slice(limit).map(one).join('')}</details>`:''}`}
function collapsibleHistory(lines,limit=3){if(!lines.length)return '<p class="category-empty">暂无变化记录。</p>';return lines.slice(0,limit).join('')+(lines.length>limit?`<details class="history-more"><summary>展开其余 ${lines.length-limit} 条历史</summary>${lines.slice(limit).join('')}</details>`:'')}
function section(title,body){return `<section class="section"><h3>${E(title)}</h3>${body}</section>`}


let S=null;
let currentEntityId=null;
const detailEl=()=>document.getElementById('detail');
const changesByEntity=new Map(),changesByTarget=new Map(),relationsByEntity=new Map(),traitsByEntity=new Map(),itemRolesByItem=new Map();
function buildIndexes(){
  for(const x of A(G.state_changes)){if(!changesByEntity.has(x.entity_id))changesByEntity.set(x.entity_id,[]);changesByEntity.get(x.entity_id).push(x);if(x.target_id){if(!changesByTarget.has(x.target_id))changesByTarget.set(x.target_id,[]);changesByTarget.get(x.target_id).push(x)}}
  for(const m of changesByEntity.values())m.sort((a,b)=>(a.chapter??0)-(b.chapter??0)||String(a.id||'').localeCompare(String(b.id||'')));
  for(const r of A(G.relations)){for(const id of [r.source_id,r.target_id]){if(!relationsByEntity.has(id))relationsByEntity.set(id,[]);relationsByEntity.get(id).push(r)}}
  for(const t of A(G.character_traits)){if(!traitsByEntity.has(t.entity_id))traitsByEntity.set(t.entity_id,[]);traitsByEntity.get(t.entity_id).push(t)}
  for(const r of A(G.item_roles)){const k=r.item_id;if(!itemRolesByItem.has(k))itemRolesByItem.set(k,[]);itemRolesByItem.get(k).push(r)}
}
function entityChanges(id){const rows=[...(changesByEntity.get(id)||[]),...(changesByTarget.get(id)||[])];return [...new Map(rows.map(x=>[x.id,x])).values()]}
function visibleRelation(r,c){const s=N(r.valid_from)??0,e=N(r.valid_to);return s<=c&&(e===null||e===undefined||c<=e)&&(!r.status||r.status!=='ended')}
function effectiveState(id,c){
  const state={};
  for(const x of (changesByEntity.get(id)||[])){if((N(x.chapter)??0)>c)break;if(N(x.end_chapter)!==null&&c>x.end_chapter)continue;const facet=term('facets',x.facet)||x.facet;const key=x.target_id?`${facet} · ${nameOf(x.target_id)}`:facet;state[key]=x.after}
  const e=entityById.get(id);
  if(e&&typeof e.attributes==='object')for(const [k,v] of Object.entries(e.attributes)){const label=attrKey(k);const key=label;if(!(key in state))state[key]=v}
  return state;
}
function entityStats(id,c){
  const e=entityById.get(id);if(!e)return null;
  const changes=entityChanges(id),rels=relationsByEntity.get(id)||[];
  const active=rels.filter(r=>visibleRelation(r,c));
  const evIds=uniqueEvidence([...A(e.evidence_ids),...recordEvidence(changes),...recordEvidence(rels)]);
  const issues=A(G.review_issues).filter(x=>!x.resolution&&A(x.related_ids).includes(id));
  const past=changes.filter(x=>(N(x.chapter)??0)<=c);
  const latest=past.length?Math.max(...past.map(x=>N(x.chapter)??0)):null;
  const state=effectiveState(id,c);
  const entries=Object.entries(state).filter(([,v])=>v!==null&&v!==undefined&&v!==''&&v!==false);
  const priority=['等级','身份','称号','所在地点','地点','所属势力','身体状态'];
  const hi=[];
  for(const want of priority){const hit=entries.find(([k])=>k===want||k.startsWith(want+' ·'));if(hit&&!hi.some(x=>x[0]===hit[0]))hi.push(hit);if(hi.length===3)break}
  for(const row of entries)if(hi.length<3&&!hi.some(x=>x[0]===row[0]))hi.push(row);
  return {entity:e,state,currentStateCount:entries.length,currentHighlights:hi,activeRelations:active,activeRelationCount:active.length,changeCount:changes.length,latestChangeChapter:latest,evidenceIds:evIds,evidenceCount:evIds.length,issueCount:issues.length,changes,pastChanges:past};
}
function summaryCard(id,c){
  const s=entityStats(id,c);if(!s)return '';
  const metrics=[[s.currentStateCount,'当前状态'],[s.activeRelationCount,'当前有效关系'],[s.changeCount,'历史变化'],[s.evidenceCount,'可追溯证据'],[s.issueCount,'待核问题']];
  return `<section class="entity-summary-card"><div class="entity-summary-scope">截至第 ${c} 章的动态状态</div><div class="entity-summary-grid">${metrics.map(([n,l])=>`<div><b>${n}</b><span>${l}</span></div>`).join('')}</div>${s.currentHighlights.length?`<div class="entity-highlights">${s.currentHighlights.map(([k,v])=>`<span>${E(k)}：${value(v)}</span>`).join('')}</div>`:'<p class="entity-latest">此时点没有可推导的动态状态。</p>'}${s.latestChangeChapter?`<div class="entity-latest">最近一次已发生变化：第 ${s.latestChangeChapter} 章</div>`:''}</section>`;
}
function levelStrip(id,c){
  const axes=new Map();
  for(const x of entityChanges(id).filter(v=>v.facet==='level').sort((a,b)=>(a.chapter??0)-(b.chapter??0))){const k=x.target_id||'level';if(!axes.has(k))axes.set(k,{k,axis:x.target_id?nameOf(x.target_id):term('facets','level'),value:null,chapter:null});const rec=axes.get(k);if((N(x.chapter)??0)<=c){rec.value=x.after;rec.chapter=x.chapter}}
  const rows=[...axes.values()].filter(a=>a.value!==null&&a.value!==undefined&&a.value!=='');
  if(!rows.length)return '';
  return `<div class="level-strip">${rows.map(a=>`<div class="level-card"><span class="level-axis">${E(a.axis)}</span><b>${value(a.value)}</b><small>第 ${a.chapter} 章</small></div>`).join('')}</div>`;
}
function tierText(t){
  if(t==null)return '';
  if(typeof t==='string')return t;
  if(typeof t==='number')return String(t);
  const name=t.名称??t.name??t.label??'';
  const range=A(t.区间).length?`（${t.区间[0]}—${t.区间[1]}）`:(t.说明||t.note?'（'+String(t.说明||t.note)+'）':'');
  return name+range;
}
function levelLegendHtml(rows){
  const axes=new Map();
  for(const a of A(G.entities).filter(e=>e.type==='level_axis'))axes.set(a.id,a);
  if(!axes.size)return '';
  const used=new Set(rows.map(r=>{const m=String(r[1]).match(/data-entity="([^"]+)"/);return m?m[1]:null}).filter(Boolean));
  const cards=[...axes.values()].filter(a=>used.has(a.id)).slice(0,12).map(a=>{
    const at=a.attributes||{};
    const tiers=A(at.档位).map(tierText).filter(Boolean);
    const ladder=at.分级?String(at.分级).split('/').map(s=>s.trim()).filter(Boolean):[];
    const uniq=[...new Set(A(G.state_changes).filter(x=>x.target_id===a.id&&(N(x.chapter)??0)<=S.chapter).map(x=>x.entity_id))];
    return `<article class="repo-card"><h4>${E(a.name)}</h4><p>${E(a.summary||'')}</p>`
      +(ladder.length?`<p><span class="muted">分级：</span>${ladder.map(E).join(' → ')}</p>`:'')
      +(tiers.length?`<p><span class="muted">档位说明：</span>${E(tiers.join(' · '))}</p>`:'')
      +`<p class="muted">截至第 ${S.chapter} 章共 ${uniq.length} 人有记录</p></article>`;
  }).join('');
  return cards?`<section class="section"><h3>等级轴说明</h3><div class="repo-grid">${cards}</div></section>`:'';
}
function personTimeline(id,c){
  const all=entityChanges(id).filter(x=>Number.isInteger(x.chapter)).sort((a,b)=>a.chapter-b.chapter);
  const chapters=[...new Set(all.map(x=>x.chapter))].sort((a,b)=>a-b);
  if(!chapters.length)return '';
  const e=entityById.get(id);const mn=N(e?.first_chapter)??1,mx=Number(META.chapter_end)||c,span=Math.max(1,mx-mn);
  const prev=[...chapters].reverse().find(x=>x<c),next=chapters.find(x=>x>c);
  const dots=chapters.filter(x=>x>=mn&&x<=mx).map(x=>`<button class="time-dot${x<c?' past':''}${x===c?' current':''}" style="left:${((x-mn)/span)*100}%" data-jump="${x}" aria-label="跳到第 ${x} 章变化" title="第 ${x} 章"></button>`).join('');
  return `<div class="person-time"><div class="person-time-head"><b>${E(nameOf(id))}的变化时间轴</b><span>第 ${c} 章</span></div><input id="personCh" type="range" min="${mn}" max="${mx}" value="${c}" aria-label="${E(nameOf(id))}的章节回放"><div class="time-dots">${dots}</div><div class="time-nav"><button data-step="-1"${prev===undefined?' disabled':''}>上次变化${prev===undefined?'':' · 第 '+prev+'章'}</button><button data-step="1"${next===undefined?' disabled':''}>下次变化${next===undefined?'':' · 第 '+next+'章'}</button></div></div>`;
}
const FACET_ORDER=['identity','title','level','attribute','skill','possession','romance','relationship','knowledge','goal','health','location','affiliation','emotion'];
function categoryPanel(id,c){
  const all=entityChanges(id),rels=relationsByEntity.get(id)||[];
  const facets=new Map();
  const slot=(f,key,label)=>{if(!facets.has(f))facets.set(f,new Map());const m=facets.get(f);if(!m.has(key))m.set(key,{key,label,value:null,valueChapter:null,first:null,last:null,changes:[],relations:[]});const it=m.get(key);if(label)it.label=label;return it};
  const mark=(it,ch)=>{if(!Number.isInteger(ch))return;it.first=it.first===null?ch:Math.min(it.first,ch);it.last=it.last===null?ch:Math.max(it.last,ch)};
  for(const x of all.slice().sort((a,b)=>(a.chapter??0)-(b.chapter??0))){const f=x.facet,key=x.target_id||`facet:${f}`,it=slot(f,key,x.target_id?nameOf(x.target_id):term('facets',f));it.changes.push(x);if((N(x.chapter)??0)<=c&&!(N(x.end_chapter)!==null&&c>x.end_chapter)){it.value=x.after;it.valueChapter=x.chapter}mark(it,x.chapter)}
  for(const r of rels){const other=r.source_id===id?r.target_id:r.source_id;const it=slot('relationship',other,nameOf(other));it.relations.push(r);mark(it,N(r.valid_from))}
  const e=entityById.get(id);
  if(e&&typeof e.attributes==='object')for(const [k,v] of Object.entries(e.attributes)){const label=attrKey(k);const it=slot('attribute',`attribute:${label}`,label);const empty=z=>z===null||z===undefined||z==='';if(empty(it.value)||(!empty(v)&&String(v).length>String(it.value).length))it.value=v}
  const routes=A(G.romance_routes).filter(r=>r.protagonist_id===id||r.character_id===id);
  if(routes.length)for(const r of routes){const other=r.protagonist_id===id?r.character_id:r.protagonist_id;const it=slot('romance',other,nameOf(other));mark(it,N(r.confirmed_chapter)??N(r.ambiguity_started_chapter)??N(r.first_meeting_chapter))}
  if(!facets.size)return '<p class="category-empty">暂无分类记录。</p>';
  const sorted=[...facets.keys()].sort((a,b)=>{const ai=FACET_ORDER.indexOf(a),bi=FACET_ORDER.indexOf(b);return (ai<0?99:ai)-(bi<0?99:bi)});
  return `<div class="category-list">${sorted.map(f=>{
    const entries=[...facets.get(f).values()];
    const named=entries.filter(x=>x.key&&!String(x.key).startsWith('facet:')&&!String(x.key).startsWith('attribute:')).sort((a,b)=>(a.first??0)-(b.first??0)||String(a.label).localeCompare(String(b.label),'zh-CN'));
    const scalars=entries.filter(x=>!named.includes(x));
    const scalarState=scalars.filter(x=>x.value!==null&&x.value!==undefined&&x.value!==false&&x.value!=='').map(x=>`<div class="row"><b>${E(x.label)}</b><span>${value(x.value)}</span></div>`).join('');
    const routeCards=f==='romance'?routes.map(r=>romanceCard(r,id)).join(''):'';
    const hist=scalars.flatMap(x=>x.changes).sort((a,b)=>(b.chapter??0)-(a.chapter??0)).map(x=>`<div class="history-item"><b>第 ${x.chapter} 章 · ${E(term('actions',x.action))}</b><p class="change-values">${value(x.before)} → ${value(x.after)}</p><p>${asOf(x.reason)}</p></div>`);
    const evIds=uniqueEvidence([...entries.flatMap(x=>recordEvidence([...x.changes,...x.relations])),...(f==='romance'?recordEvidence(routes):[])]);
    const preview=named.length?`<span class="category-preview">${named.slice(0,6).map(x=>E(x.label)).join('、')}${named.length>6?' 等':''}</span>`:'';
    const stateBlock=(scalarState||routeCards)?`<div class="category-subtitle current">截至第 ${c} 章的动态状态</div>${routeCards}${scalarState}`:`<div class="category-subtitle current">截至第 ${c} 章的动态状态</div><p class="category-empty">此时点没有有效状态。</p>`;
    const itemBlock=named.length?`<div class="category-subtitle">全范围具名条目</div><div class="entry-list">${named.map(x=>entryCard(x,id,c)).join('')}</div>`:'';
    return `<details class="category"><summary><span class="category-title">${E(term('facets',f)||f)}</span><small>${entries.length} 项 · ${hist.length} 条变化</small>${preview}</summary><div class="category-body">${stateBlock}${itemBlock}<div class="category-subtitle">完整变化历史</div>${collapsibleHistory(hist)}<div class="category-subtitle">原文证据</div>${compactEvidenceHtml(evIds)}</div></details>`;
  }).join('')}</div>`;
}
function entryCard(it,personId,c){
  const ent=entityById.get(it.key);
  const changes=it.changes.slice().sort((a,b)=>(b.chapter??0)-(a.chapter??0));
  const rels=it.relations.slice().sort((a,b)=>(N(b.valid_from)??1)-(N(a.valid_from)??1));
  const cur=(it.value!==null&&it.value!==undefined&&it.value!==''&&it.value!==false)?value(it.value):'';
  const lines=[...rels.map(r=>`<div class="entry-line"><b>${E(relationLabel(r))}</b><span>${relSpan(r,c)}</span></div>`),...changes.map(x=>`<div class="entry-line"><b>第 ${x.chapter} 章 · ${E(term('actions',x.action))}</b><span class="change-values">${value(x.before)} → ${value(x.after)}</span></div>`)];
  const reasons=changes.filter(x=>x.reason).length?`<details class="entry-reasons"><summary>${changes.filter(x=>x.reason).length} 条变化原因</summary>${changes.filter(x=>x.reason).map(x=>`<p class="entry-reason">第 ${x.chapter} 章：${asOf(x.reason)}</p>`).join('')}</details>`:'';
  return `<article class="entry"${ent?` data-entity="${E(it.key)}"`:''}><h4 class="entry-name">${ent?`<i class="entry-dot" style="background:${typeColor(ent.type)}"></i>`:''}${E(it.label)}${ent?`<span class="entry-kind">${E(term('entity_types',ent.type)||ent.type)}</span>`:''}${cur?`<span class="entry-badge">${cur}</span>`:''}</h4>${lines.length?`<div class="entry-lines">${collapsibleHistory(lines)}</div>`:''}${reasons}</article>`;
}
const REL_FALLBACK=[[/gift|gave|donat/,'赠予／馈赠'],[/rescu|protect|save|heal/,'保护／救助'],[/harm|hurt|attack|enemy|hunt|kill|rival/,'伤害／敌对'],[/parent|child|sibling|family|spouse|marri|betroth/,'家族／婚姻／婚约'],[/teacher|mentor|student|instruct|teach/,'师徒／教导'],[/friend|ally|companion|partner/,'朋友／盟友'],[/romance|love|dating|intimat|crush/,'感情／亲密'],[/member|affiliat|sect|school|citizen|leader/,'势力／组织归属'],[/own|hold|use|transfer|possess/,'物品持有／转交'],[/identity|alter|avatar|disguis|same_body/,'身份／秘密'],[/part_of|subgroup|located/,'层级／地点子集'],[/shared|participat/,'共同经历事件']];
function relationLabel(r){const t=String(r&&r.relation_type||'');const exact=(vocab().relations||{})[t];if(exact)return exact;for(const [re,label] of REL_FALLBACK)if(re.test(t))return label;return '其他关系'}
function relSpan(r,c){const s=N(r.valid_from),e=N(r.valid_to);if(s===null)return '有效期未知';return `第 ${s} 章${e===null||e===undefined?'起至今':`—${e} 章`}`}
function typeColor(t){const m=(vocab().entity_colors||{});return m[t]||({character:'#7F77DD',skill:'#1D9E75',item:'#BA7517',organization:'#378ADD',location:'#3E8B9E',creature:'#97C459',concept:'#888780',level_axis:'#BA7517'}[t]||'#888780')}
function romanceCard(r,personId){
  const other=r.protagonist_id===personId?r.character_id:r.protagonist_id;
  const st=(vocab().romance_statuses||{})[r.status]||r.status||'';
  return `<div class="romance-card" data-romance="${E(r.id)}"><h3>${E(nameOf(other))} · ${E(st)}</h3><p>${E(term('romance_inclusion_bases',r.inclusion_basis))} · ${E(term('consent_contexts',r.consent_context))}</p><p>首次相遇：${r.first_meeting_chapter?`第 ${r.first_meeting_chapter} 章`:'未定年'} · 首次亲密／暧昧：${r.ambiguity_started_chapter?`第 ${r.ambiguity_started_chapter} 章`:'尚未记录'}</p><p>关系确认：${r.confirmed_chapter?`第 ${r.confirmed_chapter} 章`:'尚未确认'} · 首次明确性关系：${r.first_sex_chapter?`第 ${r.first_sex_chapter} 章`:'尚未记录'}</p></div>`;
}
function showEntity(id){
  const e=entityById.get(id);if(!e)return;
  currentEntityId=id;
  const c=Number(document.getElementById('ch').value);
  const st=entityStats(id,c);if(!st)return;
  const aliases=A(e.aliases).filter(Boolean);
  const chips=[...aliases.map(x=>'别名 · '+x),...A(e.tags).map(x=>'标签 · '+x)];
  const activeRels=st.activeRelations;
  const historyLines=st.changes.slice().sort((a,b)=>(b.chapter??0)-(a.chapter??0)).map(x=>`<div class="history-item"><b>第 ${x.chapter} 章 · ${E(term('facets',x.facet)||x.facet)} / ${E(term('actions',x.action))}</b><p class="change-values">${value(x.before)} → ${value(x.after)}</p><p>${asOf(x.reason)}</p></div>`);
  const html=`<div class="eyebrow">${E(term('entity_types',e.type)||e.type)}${N(e.first_chapter)!==null?` · 初见第 ${e.first_chapter} 章`:''}</div><h2>${E(e.name||id)}</h2>${e.summary?`<p class="summary">${asOf(e.summary)}</p>`:''}${chips.length?`<div class="chips">${[...new Set(chips)].map(x=>`<span class="chip">${E(x)}</span>`).join('')}</div>`:''}${summaryCard(id,c)}${levelStrip(id,c)}${personTimeline(id,c)}${section(`截至第 ${c} 章的动态状态`,Object.entries(st.state).filter(([,v])=>v!==null&&v!==undefined&&v!=='').map(([k,v])=>`<div class="row"><b>${E(k)}</b><span>${value(v)}</span></div>`).join('')||'<p class="category-empty">此时点没有可推导的动态状态。</p>')}${section('当前有效关系',activeRels.length?activeRels.map(r=>{const other=r.source_id===id?r.target_id:r.source_id;return `<div class="history-item"><b>${E(relationLabel(r))} · ${E(nameOf(other))}</b><p>${relSpan(r,c)}</p></div>`}).join(''):'<p class="category-empty">截至本章没有有效关系。</p>')}${categoryPanel(id,c)}${section('完整变化历史',collapsibleHistory(historyLines,3))}${section('全范围实体证据',compactEvidenceHtml(st.evidenceIds,4))}`;
  detailEl().innerHTML=html;
  document.querySelector('aside.detail').classList.add('on');
  document.body.classList.add('detail-open');
  bindDetail();
}
function bindDetail(){
  const d=detailEl();
  d.querySelectorAll('[data-entity]').forEach(node=>node.onclick=ev=>{if(ev.target.closest('a,button'))return;showEntity(node.dataset.entity)});
  d.querySelectorAll('[data-romance]').forEach(node=>node.onclick=()=>showRomance(node.dataset.romance));
  const pc=d.querySelector('#personCh');
  if(pc){pc.oninput=()=>{const v=Number(pc.value);document.getElementById('ch').value=v;refresh();}}
  d.querySelectorAll('[data-jump]').forEach(b=>b.onclick=()=>{const v=Number(b.dataset.jump);document.getElementById('ch').value=v;refresh()});
  d.querySelectorAll('.time-nav button[data-step]').forEach(b=>b.onclick=()=>{
    const cur=Number(document.getElementById('ch').value);
    const chs=[...new Set(entityChanges(currentEntityId).map(x=>x.chapter))].filter(Number.isInteger).sort((x,y)=>x-y);
    const t=Number(b.dataset.step)>0?chs.find(x=>x>cur):[...chs].reverse().find(x=>x<cur);
    if(t!==undefined){document.getElementById('ch').value=t;refresh()}
  });
}
function showRomance(id){
  const r=A(G.romance_routes).find(x=>x.id===id);if(!r)return;
  const st=(vocab().romance_statuses||{})[r.status]||r.status||'';
  const ms=[['首次相遇',r.first_meeting_chapter],['首次亲密／暧昧',r.ambiguity_started_chapter],['关系确认',r.confirmed_chapter],['首次明确性关系',r.first_sex_chapter]];
  detailEl().innerHTML=`<button class="ghost" onclick="document.querySelector('aside.detail').classList.remove('on');document.body.classList.remove('detail-open')">关闭</button><div class="eyebrow">感情线／后宫 · ${E(st)}</div><h2>${E(nameOf(r.protagonist_id))} × ${E(nameOf(r.character_id))}</h2><p class="summary">${asOf(r.notes||'只记录有原文依据的感情进展。')}</p><section class="section"><div class="row"><b>入选依据</b><span>${E(term('romance_inclusion_bases',r.inclusion_basis))}</span></div><div class="row"><b>互动性质</b><span>${E(term('consent_contexts',r.consent_context))}</span></div><div class="row"><b>当前阶段</b><span>${E(st)}</span></div><div class="row"><b>可信度</b><span class="confidence-${E(r.confidence)}">${E(term('confidences',r.confidence))}</span></div></section>${section('里程碑',`<div class="milestone-grid">${ms.map(([l,ch])=>`<div class="milestone"><span class="ms-label">${l}</span><span class="ms-value">${ch?`第 ${ch} 章`:'尚未记录'}</span></div>`).join('')}</div>`)}${section('原文证据',compactEvidenceHtml([...A(r.first_meeting_evidence_ids),...A(r.ambiguity_evidence_ids),...A(r.confirmed_evidence_ids),...A(r.first_sex_evidence_ids)],4))}`;
  document.querySelector('aside.detail').classList.add('on');
  document.body.classList.add('detail-open');
}

 let snapCache=null,snapKey=null;
function snapshotAt(c){
 // Scrubbing re-enters with the same chapter on every animation frame; and the
 // per-entity as-of projection (alias history + attribute history + prose history)
 // is the expensive part. Memoize the whole snapshot per chapter so an open
 // detail panel re-rendering does not recompute 980 entities.
 if(snapKey===c&&snapCache)return snapCache;
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
 const s={chapter:c,graph:{entities,relations,events},arcs,views:v,names};s.collections=A(C.collections).map(x=>({id:x.id,label:x.label,members:[...expr(x.expression,s)]}));snapKey=c;snapCache=s;return s
}
const panels=[['overview','总览'],['graph','关系图'],['repo','仓库'],['arcs','剧情线'],['collections','集合'],['achievements','成就'],['combat','战绩'],['resources','资源'],['skills','技能'],['commitments','承诺'],['knowledge','秘密'],['foreshadowing','伏笔'],['levels','战力'],['rhythm','节奏'],['romance','感情'],['intimacy','亲密行为'],['mortality','生死'],['economy','经济'],['rules','规则'],['narrative','写法'],['audit','审计']];
for(const [id,t] of panels){const b=document.createElement('button');b.textContent=t;b.dataset.panel=id;b.onclick=()=>{active=id;document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));render()};if(id==='overview')b.className='on';tabsEl.appendChild(b)}

const clickableId=id=>typeof id==='string'&&entityById.has(id);
function entLink(label,id){
  const text=label==null?'':String(label);
  if(id&&clickableId(id))return `<a href="#" class="ent" data-entity="${E(id)}">${E(text||nameOf(id))}</a>`;
  const hit=clickableId(text)?text:null;
  if(hit)return `<a href="#" class="ent" data-entity="${E(hit)}">${E(nameOf(hit))}</a>`;
  const byName=A(S?.graph.entities).find(e=>e.name===text);
  if(byName)return `<a href="#" class="ent" data-entity="${E(byName.id)}">${E(text)}</a>`;
  return E(text);
}
function emptyNote(title,source,detail){
  return `<div class="card"><b>${E(title)}</b><p class="muted" style="margin:6px 0 0">这一格不是渲染出错：该数据面在本次图谱写定里条数为 0。来源：${E(source)}${detail?`<br>${E(detail)}`:''}</p></div>`;
}
const repoState={tab:'characters',q:'',sort:'first',filter:'all',page:1,pageSize:24};
const REPO_TABS=[['characters','人物库','character'],['organizations','势力／家族','organization'],['locations','地点库','location'],['skills','技能库','skill'],['items','装备／物品库','item'],['levels','等级库','level_axis']];
function repoRows(){
  const tab=REPO_TABS.find(x=>x[0]===repoState.tab)||REPO_TABS[0];
  let rows=A(S.graph.entities).filter(e=>e.type===tab[2]);
  if(tableRoleFilter.active&&tab[2]==='item'){} 
  const q=repoState.q.trim().toLowerCase();
  if(q)rows=rows.filter(e=>String(e.name||'').toLowerCase().includes(q)||A(e.aliases).some(a=>String(a).toLowerCase().includes(q)));
  if(repoState.filter==='protagonist')rows=rows.filter(e=>A(e.tags).some(t=>t==='protagonist'||t==='主角'));
  if(repoState.filter==='active')rows=rows.filter(e=>{const st=entityStats(e.id,Number(sl.value));return st&&st.activeRelations.length});
  if(repoState.filter==='changed')rows=rows.filter(e=>{const st=entityStats(e.id,Number(sl.value));return st&&st.changeCount>0});
  if(repoState.filter==='issues')rows=rows.filter(e=>{const st=entityStats(e.id,Number(sl.value));return st&&st.issueCount>0});
  if(repoState.sort==='name')rows=[...rows].sort((a,b)=>String(a.name).localeCompare(String(b.name),'zh-CN'));
  else if(repoState.sort==='latest')rows=[...rows].sort((a,b)=>{const sa=entityStats(a.id,Number(sl.value)),sb=entityStats(b.id,Number(sl.value));return (sb?.latestChangeChapter??0)-(sa?.latestChangeChapter??0)});
  else rows=[...rows].sort((a,b)=>(N(a.first_chapter)??1e9)-(N(b.first_chapter)??1e9));
  return rows;
}
const tableRoleFilter={active:false};
function repoCard(e,c){
  const st=entityStats(e.id,c)||{};
  const hi=(st.currentHighlights||[]).slice(0,2).map(([k,v])=>`<p><b>${E(k)}</b>：${value(v)}</p>`).join('');
  return `<article class="repo-card" data-entity="${E(e.id)}"><h4>${E(e.name||e.id)}<span class="entry-kind">${E(term('entity_types',e.type)||e.type)}</span></h4>${e.summary?`<p>${asOf(e.summary)}</p>`:''}${hi}<p>初见第 ${N(e.first_chapter)??'—'} 章 · ${st.changeCount||0} 次变化 · ${st.activeRelationCount||0} 条有效关系 · ${st.evidenceCount||0} 条证据</p></article>`;
}
function renderRepo(){
  const tabs=`<div class="filters">${REPO_TABS.map(([id,label])=>`<button data-repo-tab="${id}" class="${repoState.tab===id?'on':''}">${label}</button>`).join('')}</div>`;
  const bar=`<div class="filters"><input id="repoQ" type="search" placeholder="搜索名称或别名" value="${E(repoState.q)}"><select id="repoSort"><option value="first"${repoState.sort==='first'?' selected':''}>按初见章节</option><option value="name"${repoState.sort==='name'?' selected':''}>按名称</option><option value="latest"${repoState.sort==='latest'?' selected':''}>按最近变化</option></select><select id="repoFilter"><option value="all"${repoState.filter==='all'?' selected':''}>全部结果</option><option value="protagonist"${repoState.filter==='protagonist'?' selected':''}>主角相关</option><option value="active"${repoState.filter==='active'?' selected':''}>当前有效</option><option value="changed"${repoState.filter==='changed'?' selected':''}>有变化记录</option><option value="issues"${repoState.filter==='issues'?' selected':''}>有待核问题</option></select></div>`;
  const rows=repoRows(),total=rows.length,pages=Math.max(1,Math.ceil(total/repoState.pageSize));
  if(repoState.page>pages)repoState.page=pages;
  const start=(repoState.page-1)*repoState.pageSize,slice=rows.slice(start,start+repoState.pageSize);
  const c=Number(sl.value);
  const body=slice.length?`<div class="repo-grid">${slice.map(e=>repoCard(e,c)).join('')}</div>`:'<p class="category-empty">当前筛选没有匹配的实体。</p>';
  const pager=pages>1?`<div class="pager"><button data-repo-page="1"${repoState.page<=1?' disabled':''}>首页</button><button data-repo-page="${repoState.page-1}"${repoState.page<=1?' disabled':''}>上一页</button><span>第 ${repoState.page} / ${pages} 页 · 共 ${total} 条</span><button data-repo-page="${repoState.page+1}"${repoState.page>=pages?' disabled':''}>下一页</button><button data-repo-page="${pages}"${repoState.page>=pages?' disabled':''}>末页</button></div>`:`<div class="pager">共 ${total} 条</div>`;
  set(`<p class="muted">完整资料始终可浏览；章节控件只回放当前有效的身份、关系、物品角色与等级占用。点开任一卡片查看该实体截至第 ${c} 章的动态状态。</p>${tabs}${bar}${body}${pager}`);
  document.querySelectorAll('[data-repo-tab]').forEach(b=>b.onclick=()=>{repoState.tab=b.dataset.repoTab;repoState.page=1;renderRepo()});
  const q=document.getElementById('repoQ');
  if(q){q.oninput=()=>{repoState.q=q.value;repoState.page=1;renderRepo();const n=document.getElementById('repoQ');if(n){n.focus();n.setSelectionRange(n.value.length,n.value.length)}}}
  const so=document.getElementById('repoSort');if(so)so.onchange=()=>{repoState.sort=so.value;repoState.page=1;renderRepo()};
  const fi=document.getElementById('repoFilter');if(fi)fi.onchange=()=>{repoState.filter=fi.value;repoState.page=1;renderRepo()};
  document.querySelectorAll('[data-repo-page]').forEach(b=>b.onclick=()=>{repoState.page=Number(b.dataset.repoPage);renderRepo()});
  bindEntitiesIn(mainEl);
}
function bindEntitiesIn(root){
  root.querySelectorAll('a.ent').forEach(a=>a.onclick=ev=>{ev.preventDefault();showEntity(a.dataset.entity)});
  root.querySelectorAll('[data-romance]').forEach(node=>node.onclick=()=>showRomance(node.dataset.romance));
}
function renderIntimacy(){
  const c=Number(sl.value);
  const acts=A(G.intimate_acts).filter(a=>(N(a.chapter)??0)<=c).sort((a,b)=>(b.chapter??0)-(a.chapter??0));
  if(!acts.length){set(emptyNote('截至本章没有亲密行为记录','intimate_acts[]'));return}
  const cc=k=>(vocab().consent_contexts||{})[k]||k||'未记录';
  const at=k=>(vocab().intimacy_act_types||{})[k]||k||'';
  const who=a=>[...A(a.initiator_ids),...A(a.recipient_ids),...A(a.observer_ids)].map(id=>nameOf(id)).join('、')||'未记录';
  const cards=acts.map(a=>`<article class="repo-card"><h4>${E(at(a.act_type))}<span class="entry-kind">第 ${a.chapter} 章</span></h4><p>${asOf(a.description)}</p><p><b>主动方</b>：${E(A(a.initiator_ids).map(nameOf).join('、')||'—')} · <b>承受方</b>：${E(A(a.recipient_ids).map(nameOf).join('、')||'—')}${A(a.observer_ids).length?' · <b>旁观者</b>：'+E(A(a.observer_ids).map(nameOf).join('、')):''}</p><p><b>互动性质</b>：${E(cc(a.consent))} · <b>可信度</b>：<span class="confidence-${E(a.confidence)}">${E(term('confidences',a.confidence))}</span></p></article>`).join('');
  set(`<p class="muted">逐次记录发生过的亲密或性行为，区分主动方、承受方与旁观者。「暴力强迫」与「非自愿／受迫」刻意分开：前者是暴力或无力反抗，后者是胁迫、施压或权力不对等。共 ${acts.length} 条。</p><div class="repo-grid">${cards}</div>`);
}

function table(h,rows){if(!rows.length)return '<div class="card muted">当前章节无数据</div>';return `<div class=scroll><table><thead><tr>${h.map(x=>`<th>${E(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(x=>`<td>${x??''}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}function set(x){mainEl.innerHTML=`<section>${x}</section>`;bindEntitiesIn(mainEl)}
function render(){const v=S.views;if(active==='overview'){const open=v.commitments.filter(x=>['active','partially_fulfilled','uncertain'].includes(x.status)),metrics=[[S.graph.entities.length,'实体','repo'],[S.graph.events.length,'事件','rhythm'],[v.achievements.length,'成就','achievements'],[v.combat_records.filter(x=>x.result==='victory').length,'胜场','combat'],[open.length,'未完承诺','commitments'],[v.foreshadowing.unresolved.length,'未收伏笔','foreshadowing']];set(`<div class=grid>${metrics.map(x=>`<div class=card data-goto="${x[2]}" style="cursor:pointer"><div class=metric>${x[0]}</div><div class=muted>${x[1]}</div></div>`).join('')}</div><p class="muted">点任一卡片进入对应面板。所有面板共用上方章节滑块。</p>`);mainEl.querySelectorAll('[data-goto]').forEach(b=>b.onclick=()=>{const id=b.dataset.goto;const btn=document.querySelector(`#tabs button[data-panel=${id}]`);if(btn)btn.click()});return}
 if(active==='graph'){set('<div id="cy" class=graph></div><p class="muted">节点颜色按实体类型；点击节点查看该实体截至本章的档案。</p>');const cap=260;const ns=S.graph.entities.slice(0,cap).map(e=>({data:{id:e.id,label:e.name,color:typeColor(e.type)}})),keep=new Set(ns.map(x=>x.data.id)),es=S.graph.relations.filter(r=>keep.has(r.source_id)&&keep.has(r.target_id)).slice(0,520).map(r=>({data:{id:r.id,source:r.source_id,target:r.target_id,label:relationLabel(r)}}));if(cy)cy.destroy();if(typeof cytoscape!=='undefined')cy=cytoscape({container:document.getElementById('cy'),elements:[...ns,...es],style:[{selector:'node',style:{label:'data(label)','font-size':10,'background-color':'data(color)','color':'#e6edf3','text-valign':'bottom','text-margin-y':3,'width':18,'height':18}},{selector:'edge',style:{'target-arrow-shape':'triangle','curve-style':'bezier','line-color':'#30363d','target-arrow-color':'#30363d','label':'data(label)','font-size':8,'color':'#8b949e','text-rotation':'autorotate','text-opacity':.7}},{selector:'node:selected',style:{'border-width':2,'border-color':'#f2cc60'}}],layout:{name:'cose',animate:false,nodeRepulsion:9000}});cy.on('tap','node',ev=>{const id=ev.target.id();currentEntityId=id;showEntity(id)});return}
 if(active==='repo'){renderRepo();return}
 if(active==='arcs'){if(!S.arcs.length){set(emptyNote('本图谱尚未登记剧情线','story_arcs[]','契约要求按区间记录，可嵌套/并行；补齐后此处渲染泳道'));return}
  const mx=Number(META.chapter_end)||1;const lanes=S.arcs.map(a=>{const s0=N(a.chapter_start)??1,e0=N(a.chapter_end);const left=((s0-1)/mx)*100,right=((e0??mx)/mx)*100;const phase=E(term('story_arc_phases',a.phase)||'');return `<div class="lane"><span>${E(a.title||a.id)}</span><div class="lane-track"><div class="lane-span" style="left:${left}%;width:${Math.max(1,right-left)}%" title="${E((a.title||a.id)+' 第 '+s0+'—'+(e0??'未完')+' 章')}">${e0?'':"未完"}</div></div></div>`}).join('');set(`<p class="muted">每条剧情线独立泳道；区间可重叠、可嵌套。宽度按章节范围。</p><div class="card">${lanes}</div>`);return}
 if(active==='collections'){const cs=S.collections;if(!cs.length){set(emptyNote('本 run 没有定义集合','dashboard-views.json（--collection-manifest）','集合是把实体按表达式分组后再取交集／并集／差集；该 run 未提供 manifest，所以为空'));return}set(table(['集合','成员数','成员'],cs.map(c=>[E(c.label||c.id),A(c.members).length,E(A(c.members).map(id=>S.names[id]||id).join('、'))])));return}
 if(active==='achievements'){const ks=k=>(vocab().achievement_categories||{})[k]||k||'';if(!v.achievements.length){set(emptyNote('本 run 没有可派生的成就行','derived from events/state_changes'));return}set(table(['章','类别','成就'],v.achievements.map(x=>[x.chapter,E(ks(x.category)),E(x.title)])));return}
 if(active==='combat'){const rc=r=>(vocab().combat_results||{})[r]||({victory:'胜',defeat:'败',draw:'平',escaped:'逃脱',interrupted:'中断',uncertain:'结果未定'}[r])||r||'';set(table(['章','对手','结果','当时境界'],v.combat_records.map(x=>[x.chapter,A(x.opponents).map(o=>entLink(o)).join('、'),E(rc(x.result)),value((x.protagonist_level||{}).level)])));return}
 if(active==='resources'){const rar=r=>(vocab().resource_rarity||{})[r]||r||'';set(table(['资源','稀有度','获得章','当前持有人'],v.resources.items.map(x=>{const holder=A(x.role_history).filter(r=>r.role==='holder'||r.role==='owner').at(-1);return [entLink(x.name,x.item_id),E(rar(x.rarity)||'未标注'),x.first_acquired_chapter??(A(x.role_history)[0]||{}).chapter??'',holder?entLink(holder.entity,holder.entity_id):'—']})));return}
 if(active==='skills'){set(table(['技能','分类','当前掌握'],v.skills.map(x=>[E(x.name),E(A(x.categories).join('、')),E(A(x.holders).map(h=>h.entity).join('、'))])));return}
 if(active==='commitments'){const ks=k=>(vocab().commitment_kinds||{})[k]||k||'';const st=k=>(vocab().commitment_statuses||{})[k]||k||'';set(table(['建立章','类型','内容','状态','解决章'],v.commitments.map(x=>[x.created_chapter,E(ks(x.kind)),E(x.terms),E(st(x.status)),N(x.resolved_chapter)!==null?x.resolved_chapter:'—'])));return}
 if(active==='knowledge'){if(!v.knowledge.secrets.length){set(emptyNote('本图谱尚未登记秘密','secret 概念实体 + knowledge 状态变化'));return}const rows=[];for(const s of v.knowledge.secrets)for(const p of A(s.people))rows.push([E(s.secret),entLink(p.entity,p.entity_id),p.history.length]);set(table(['秘密','人物','知情变化'],rows));return}
 if(active==='foreshadowing'){set(table(['伏笔','埋设章','回收章','跨度','状态'],v.foreshadowing.rows.map(x=>[E(x.label),x.planted_chapter,N(x.payoff_chapter)!==null?x.payoff_chapter:'—',N(x.payoff_chapter)!==null?`${x.payoff_chapter-x.planted_chapter} 章`:'未收',E(term('foreshadow_statuses',x.status)||x.status||'')])));return}
 if(active==='levels'){const rows=[];for(const s of v.levels.series)for(const [k,h] of Object.entries(s.facets||{})){const z=A(h).at(-1);if(!z)continue;const src=A(G.state_changes).find(x=>x.id===z.record_id);const axisId=src&&src.target_id;rows.push([entLink(s.entity,s.entity_id),axisId?entLink(nameOf(axisId),axisId):E(term('facets',k)||k),z.chapter,value(z.after)])}set(`<p class="muted">每位人物在其等级轴上的当前档位，按所选章节回放。换轴体系互不合并。</p>`+table(['人物','等级轴','最近变化章','截至本章档位'],rows)+levelLegendHtml(rows));return}
 if(active==='rhythm'){const rows=v.chapter_rhythm.chapters.slice(-200);const mx=Math.max(1,...rows.map(x=>x.event_total||0));const bars=rows.map(x=>`<div class="bar-row"><span>第 ${x.chapter} 章</span><div class="bar-track"><div class="bar-fill" style="width:${((x.event_total||0)/mx)*100}%"></div></div><span>${x.event_total||0}</span></div>`).join('');set(`<p class="muted">最近 200 章的事件密度与断章类型。${E((vocab().cliffhanger_types||{})['crisis']?'':'').slice(0,0)}</p><div class="card">${bars}</div>`);return}
 if(active==='intimacy'){renderIntimacy();return}
 if(active==='romance'){const mk=k=>(vocab().romance_milestones||{})[k]||({first_meeting:'首次相遇',ambiguity:'首次亲密／暧昧',confirmed:'关系确认',intimacy:'首次明确性关系'}[k])||k;
  if(!v.romance.routes.length){set(emptyNote('本图谱尚未记录感情线','romance_routes'));return}
  // The derived view keeps only six fields; inclusion_basis and consent_context
  // live on the source record, so look them up rather than rendering blanks.
  const srcRoute=new Map(A(G.romance_routes).map(x=>[x.id,x]));
  const cards=v.romance.routes.map(r=>{const st=(vocab().romance_statuses||{})[r.status]||r.status||'';const raw=srcRoute.get(r.route_id)||{};const basis=term('romance_inclusion_bases',raw.inclusion_basis);const consent=term('consent_contexts',raw.consent_context);const ms=A(r.milestones).map(m=>`<div class="milestone"><span class="ms-label">${E(mk(m.kind))}</span><span class="ms-value">第 ${m.chapter} 章</span></div>`).join('');return `<article class="repo-card" data-romance="${E(r.route_id)}"><h4>${E(r.character)} · ${E(st)}</h4><p>入选依据：${E(basis||'未标注')} · 互动性质：${E(consent||'未标注')}</p><div class="milestone-grid">${ms}</div></article>`}).join('');
  set(`<p class="muted">有原文可证的亲密动作或明确亲密提议即可入列；入列不等于自愿或确认恋爱。</p><div class="repo-grid">${cards}</div>`);return}
 if(active==='mortality'){if(!v.mortality.events.length){set(emptyNote('本图谱尚未记录死亡／复活事件','mortality events（events[].type=mortality 或 health 状态变化）'));return}set(table(['章','人物','死因'],v.mortality.events.map(x=>[x.chapter,E(x.entity),asOf(x.cause||'')])));return}
 if(active==='economy'){if(!v.economy.transactions.length){set(emptyNote('本图谱尚未记录交易','economy = events[].transaction 面','该 run 的事件里没有带 transaction 面；补齐需回到抽取阶段，不是渲染问题'));return}set(table(['章','交易','金额'],v.economy.transactions.map(x=>[x.chapter,E(x.title||x.event_id),E(x.amount??'')])));return}
 if(active==='rules'){set(table(['规则','分类','摘要'],v.rules.concepts.map(x=>[E(x.name),E(A(x.categories).join('、')),E(x.summary||'')])));return}
 if(active==='narrative'){if(!v.narrative.character_voice.length&&!v.narrative.author_style.length){set(emptyNote('本 run 没有风格观察','style-observations.json（validate_style_observations.py 校验）'));return}const rows=[];for(const x of v.narrative.character_voice)for(const o of A(x.observations))rows.push([E(x.entity),N(o.chapter)??N(o.chapter_start)??'',asOf(o.observation||o.summary||o.text||'')]);set(table(['人物','章','声音观察'],rows));return}
 const gaps=A(B.metadata?.temporal_provenance_gaps);set(`<div class=card><b>契约：</b>${V.contract_summary?.valid?'通过':'存在问题'} · errors ${V.contract_summary?.error_count??0} · warnings ${V.contract_summary?.warning_count??0}</div><div class="card ${gaps.length?'warn':'muted'}">构建时无时间来源字段：${gaps.length}</div>`)}
// Chapter scrubbing must not rebuild the whole page: coalesce input to one render
// per animation frame, and re-project an open entity detail instead of dropping it.
let pendingFrame=0;
function refresh(){if(pendingFrame)return;pendingFrame=requestAnimationFrame(()=>{pendingFrame=0;const c=Number(sl.value);document.getElementById('cl').textContent=c;S=snapshotAt(c);document.getElementById('state').textContent=`统一快照 · ${S.graph.entities.length} 实体 · ${S.graph.events.length} 事件${B.metadata?.cutoff!=null?' · cutoff '+B.metadata.cutoff:''}`;render();if(currentEntityId&&entityById.has(currentEntityId))showEntity(currentEntityId)})}buildIndexes();sl.addEventListener('input',refresh);refresh();
</script></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--collection-manifest", type=Path)
    parser.add_argument("--cutoff", type=int)
    parser.add_argument("--protagonist-id", action="append", default=[])
    parser.add_argument("--relation-gap-threshold", type=int, default=3)
    parser.add_argument("--vocabulary", type=Path, help="Optional book-specific display vocabulary JSON")
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    collections = json.loads(args.collection_manifest.read_text(encoding="utf-8")) if args.collection_manifest else None
    vocabulary = json.loads(args.vocabulary.read_text(encoding="utf-8")) if args.vocabulary else None
    model = build_model(graph, args.protagonist_id, args.relation_gap_threshold, collections, args.cutoff, vocabulary)
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
