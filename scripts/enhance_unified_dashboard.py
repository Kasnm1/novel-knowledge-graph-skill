#!/usr/bin/env python3
"""Enhance the unified Dashboard with AI-driven entity detail, quality, and snapshot diff UX."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from io_utils import atomic_write_text


STYLE = r'''<style id="nkg-intelligence-style">
#nkgEntityShade{position:fixed;inset:0;background:#0008;z-index:20;display:none}#nkgEntityDrawer{position:fixed;right:0;top:0;bottom:0;width:min(560px,94vw);background:#0d1117;border-left:1px solid #30363d;box-shadow:-18px 0 60px #0008;z-index:21;transform:translateX(102%);transition:transform .18s ease;overflow:auto;padding:18px}#nkgEntityDrawer.open{transform:translateX(0)}#nkgEntityShade.open{display:block}.nkgClose{float:right;font-size:18px}.nkgHero{padding:14px;border:1px solid #30363d;border-radius:12px;background:linear-gradient(145deg,#161b22,#11161d);margin:8px 0 12px}.nkgHero h2{font-size:24px;margin:2px 0 5px}.nkgHeadline{font-size:14px;color:#c9d1d9;margin:5px 0 12px}.nkgKeyLine{display:flex;gap:8px;align-items:baseline;margin:7px 0}.nkgKeyLabel{color:#8b949e;min-width:72px}.nkgFirst{font-size:16px;font-weight:700}.nkgChips{display:flex;gap:6px;flex-wrap:wrap}.nkgChip{border:1px solid #3b4754;border-radius:999px;padding:4px 8px;background:#1b222c}.nkgBadge{border-color:#8957e5;color:#d2a8ff}.nkgDetailSection{margin:14px 0}.nkgDetailSection h3{font-size:14px;margin:0 0 7px;color:#c9d1d9}.nkgDetailGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:6px}.nkgMini{border:1px solid #30363d;border-radius:8px;padding:7px;background:#161b22}.nkgMini b{display:block;margin-bottom:3px}.nkgClickable{cursor:pointer}.nkgClickable:hover{outline:1px solid #58a6ff;background:#18202a}.nkgEvidence{display:block;color:#79c0ff;text-decoration:none;margin:4px 0}.nkgEvidence:hover{text-decoration:underline}.nkgQualityGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:7px;margin-top:10px}.nkgQualityMetric{border:1px solid #30363d;border-radius:9px;padding:9px;background:#11161d}.nkgQualityMetric strong{font-size:20px;display:block}.nkgDiffControls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}.nkgDiffControls input{max-width:110px;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:5px}.nkgDiffList{margin:4px 0 0;padding-left:18px}.nkgAiNote{color:#8b949e;font-size:12px;margin-top:8px}
</style>'''


SCRIPT = r'''<script id="nkg-intelligence-layer">
const NKGX=__NKG_PAYLOAD__;
const NKG_PROFILES=NKGX.profiles?.profiles||{};
const NKG_QUALITY=NKGX.quality||{};
let nkgCompareChapter=Math.max(min, max-50);
function nkgVis(row,c){const a=N(row?.valid_from)??0,z=N(row?.valid_to);return a<=c&&(z===null||c<=z)}
function nkgEv(id){return A(G.evidence).find(x=>x.id===id)}
function nkgProfile(id,c){const p=NKG_PROFILES[id]||{};return {headlines:A(p.headlines).filter(x=>nkgVis(x,c)),important_attributes:A(p.important_attributes).filter(x=>nkgVis(x,c)),badges:A(p.badges).filter(x=>nkgVis(x,c)),ai_authored:!!p.ai_authored}}
function nkgImportant(e,p){const raw=A(G.entities).find(x=>x.id===e.id),projected=raw?entityAt(raw,S.chapter):e,attrs=projected?.attributes||{};let rows=[];for(const x of p.important_attributes){if(Object.hasOwn(attrs,x.source_key))rows.push({label:x.label||x.source_key,value:attrs[x.source_key],reason:x.reason||''})}if(!rows.length)rows=Object.entries(attrs).slice(0,6).map(([k,v])=>({label:k,value:v,reason:''}));return rows}
function nkgCurrentStates(id,c){const latest=new Map();for(const x of A(G.state_changes)){if(x.entity_id!==id||(N(x.chapter)??1e15)>c)continue;const key=String(x.facet||'状态');const old=latest.get(key);if(!old||(N(old.chapter)??0)<=(N(x.chapter)??0))latest.set(key,x)}return [...latest.entries()].map(([facet,x])=>({facet,value:x.after,chapter:x.chapter}))}
function nkgRelLabel(r,id){const other=r.source_id===id?r.target_id:r.source_id;return `${r.relation_type||'relation'} · ${S.names[other]||other}`}
function nkgOpenEntity(id){const e=S?.graph?.entities?.find(x=>x.id===id);if(!e)return;const p=nkgProfile(id,S.chapter),attrs=nkgImportant(e,p),states=nkgCurrentStates(id,S.chapter);const rels=A(S.graph.relations).filter(r=>r.source_id===id||r.target_id===id).slice(0,12);const events=A(S.graph.events).filter(v=>A(v.participant_ids).includes(id)).sort((a,b)=>(N(b.chapter)??0)-(N(a.chapter)??0)).slice(0,8);const headline=p.headlines.at(-1)?.text||e.summary||e.description||'';const first=N(e.first_chapter);const badges=p.badges.map(x=>`<span class="nkgChip nkgBadge">${E(x.label)}</span>`).join('');const attrHtml=attrs.length?attrs.map(x=>`<span class=nkgChip title="${E(x.reason)}"><b>${E(x.label)}</b> ${E(typeof x.value==='object'?JSON.stringify(x.value):x.value)}</span>`).join(''):'<span class=muted>当前章节暂无可见属性</span>';const stateHtml=states.length?states.map(x=>`<div class=nkgMini><b>${E(x.facet)}</b>${E(typeof x.value==='object'?JSON.stringify(x.value):x.value)}<div class=muted>第${x.chapter}章更新</div></div>`).join(''):'<div class=muted>暂无状态变化</div>';const relHtml=rels.length?rels.map(r=>`<div class=nkgMini><b>${E(nkgRelLabel(r,id))}</b><span class=muted>${E(r.status||'')}</span></div>`).join(''):'<div class=muted>当前章节暂无活动关系</div>';const eventHtml=events.length?events.map(v=>`<div class=nkgMini><b>第${v.chapter}章 · ${E(v.title||v.type||v.id)}</b><span class=muted>${E(v.type||'')}</span></div>`).join(''):'<div class=muted>暂无已发生事件</div>';const evid=A(e.evidence_ids).map(nkgEv).filter(x=>x&&(N(x.chapter)??1e15)<=S.chapter).slice(0,10);const evidHtml=evid.length?evid.map(x=>`<a class=nkgEvidence href="reader.html?chapter=${x.chapter}&evidence=${encodeURIComponent(x.id)}">第${x.chapter}章 · ${E(String(x.quote||'').slice(0,72))}</a>`).join(''):'<div class=muted>暂无直接实体证据</div>';document.getElementById('nkgEntityBody').innerHTML=`<button class=nkgClose id=nkgCloseEntity>×</button><div class=nkgHero><div class=muted>${E(e.type||'entity')} · ${E(e.id)}</div><h2>${E(e.name||e.id)}</h2>${headline?`<div class=nkgHeadline>${E(headline)}</div>`:''}<div class=nkgKeyLine><span class=nkgKeyLabel>首次出现</span><span class=nkgFirst>${first===null?'未知':`第 ${first} 章`}</span></div><div class=nkgKeyLine><span class=nkgKeyLabel>重要属性</span><div class=nkgChips>${attrHtml}</div></div>${badges?`<div class=nkgChips>${badges}</div>`:''}<div class=nkgAiNote>${p.ai_authored?'重要性由 AI display profile 按当前作品判断；事实值仍来自当前章节快照。':'未提供 AI display profile；当前仅使用可见属性做中性降级。'}</div></div><div class=nkgDetailSection><h3>当前状态</h3><div class=nkgDetailGrid>${stateHtml}</div></div><div class=nkgDetailSection><h3>当前关系</h3><div class=nkgDetailGrid>${relHtml}</div></div><div class=nkgDetailSection><h3>最近事件</h3><div class=nkgDetailGrid>${eventHtml}</div></div><div class=nkgDetailSection><h3>证据</h3>${evidHtml}</div>`;document.getElementById('nkgEntityDrawer').classList.add('open');document.getElementById('nkgEntityShade').classList.add('open');document.getElementById('nkgCloseEntity').onclick=nkgCloseEntity}
function nkgCloseEntity(){document.getElementById('nkgEntityDrawer').classList.remove('open');document.getElementById('nkgEntityShade').classList.remove('open')}
function nkgBind(){if(active==='repo'){const rows=document.querySelectorAll('#main tbody tr');rows.forEach((row,i)=>{const e=S.graph.entities[i];if(!e)return;row.classList.add('nkgClickable');row.onclick=()=>nkgOpenEntity(e.id)})}if(active==='graph'&&cy&&!cy.__nkgEntityBound){cy.__nkgEntityBound=true;cy.on('tap','node',evt=>nkgOpenEntity(evt.target.id()))}}
function nkgAppendQuality(){const q=NKG_QUALITY;if(!q||!q.evidence)return;const ratio=q.evidence.ratio==null?'—':`${Math.round(q.evidence.ratio*100)}%`;const root=document.querySelector('#main section');if(!root||root.querySelector('.nkgQualityGrid'))return;root.insertAdjacentHTML('beforeend',`<div class=nkgQualityGrid><div class=nkgQualityMetric><strong>${ratio}</strong>证据引用覆盖</div><div class=nkgQualityMetric><strong>${q.temporal_provenance?.gap_count??0}</strong>时序来源缺口</div><div class=nkgQualityMetric><strong>${q.review?.unresolved_count??0}</strong>未解决审计项</div><div class=nkgQualityMetric><strong>${q.invariants?.warning_count??0}</strong>语义不变量警告</div><div class=nkgQualityMetric><strong>${q.invariants?.error_count??0}</strong>语义不变量错误</div></div><div class="card muted">质量指标描述证据、完整度与时序风险，不是“事实为真概率”。当前指标针对本次构建范围。</div>`)}
function nkgIdSet(rows){return new Set(A(rows).map(x=>x.id).filter(Boolean))}
function nkgRenderChanges(){const hi=S.chapter,lo=Math.min(Math.max(Number(nkgCompareChapter)||min,min),hi),old=snapshotAt(lo),newEnt=nkgIdSet(S.graph.entities),oldEnt=nkgIdSet(old.graph.entities),newEv=nkgIdSet(S.graph.events),oldEv=nkgIdSet(old.graph.events);const entities=S.graph.entities.filter(x=>!oldEnt.has(x.id)),events=S.graph.events.filter(x=>!oldEv.has(x.id)),states=A(G.state_changes).filter(x=>(N(x.chapter)??0)>lo&&(N(x.chapter)??0)<=hi),oldRel=Object.fromEntries(old.graph.relations.map(x=>[x.id,`${x.status||''}|${x.valid_to??''}`])),relChanges=S.graph.relations.filter(x=>oldRel[x.id]!==`${x.status||''}|${x.valid_to??''}`),oldCom=Object.fromEntries(A(old.views.commitments).map(x=>[x.id,x.status])),comChanges=A(S.views.commitments).filter(x=>oldCom[x.id]!==x.status);mainEl.innerHTML=`<section><div class=nkgDiffControls><b>快照变化</b><label>对比章 <input id=nkgCompare type=number min=${min} max=${hi} value=${lo}></label><span class=muted>→ 当前第 ${hi} 章</span></div><div class=grid><div class=card><div class=metric>${entities.length}</div><div class=muted>新增实体</div></div><div class=card><div class=metric>${events.length}</div><div class=muted>新增事件</div></div><div class=card><div class=metric>${states.length}</div><div class=muted>状态变化</div></div><div class=card><div class=metric>${relChanges.length}</div><div class=muted>关系变化</div></div><div class=card><div class=metric>${comChanges.length}</div><div class=muted>承诺状态变化</div></div></div>${table(['类别','章节/对象','变化'],[...entities.slice(0,40).map(x=>['实体',E(x.name),`首次出现 ${x.first_chapter??''}`]),...events.slice(0,60).map(x=>['事件',`第${x.chapter}章`,E(x.title||x.type||x.id)]),...states.slice(0,80).map(x=>['状态',`第${x.chapter}章 · ${E(S.names[x.entity_id]||x.entity_id)}`,`${E(x.facet)} → ${E(typeof x.after==='object'?JSON.stringify(x.after):x.after)}`]),...relChanges.slice(0,40).map(x=>['关系',E(x.relation_type),E(`${S.names[x.source_id]||x.source_id} ↔ ${S.names[x.target_id]||x.target_id}`)]),...comChanges.slice(0,30).map(x=>['承诺',x.created_chapter??'',E(`${x.terms} · ${x.status}`)])])}</section>`;document.getElementById('nkgCompare').onchange=e=>{nkgCompareChapter=Number(e.target.value);nkgRenderChanges()}}
const nkgBaseRender=render;render=function(){if(active==='changes'){nkgRenderChanges();return}nkgBaseRender();setTimeout(()=>{nkgBind();if(active==='audit')nkgAppendQuality()},0)};
document.body.insertAdjacentHTML('beforeend','<div id=nkgEntityShade></div><aside id=nkgEntityDrawer><div id=nkgEntityBody></div></aside>');document.getElementById('nkgEntityShade').onclick=nkgCloseEntity;
const nkgChangeButton=document.createElement('button');nkgChangeButton.textContent='变化';nkgChangeButton.dataset.panel='changes';nkgChangeButton.onclick=()=>{active='changes';document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===nkgChangeButton));render()};const nkgAudit=[...tabsEl.querySelectorAll('button')].find(x=>x.textContent==='审计');tabsEl.insertBefore(nkgChangeButton,nkgAudit||null);nkgBind();
</script>'''


def enhance_html(source: str, profiles: dict[str, Any], quality: dict[str, Any] | None = None) -> str:
    if 'id="nkg-intelligence-layer"' in source:
        return source
    payload = json.dumps({"profiles": profiles, "quality": quality or {}}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    style = STYLE
    script = SCRIPT.replace("__NKG_PAYLOAD__", payload)
    if "</head>" not in source or "</body>" not in source:
        raise ValueError("dashboard HTML is missing </head> or </body>")
    return source.replace("</head>", style + "</head>", 1).replace("</body>", script + "</body>", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard", required=True, type=Path)
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--quality", type=Path)
    args = parser.parse_args()
    source = args.dashboard.read_text(encoding="utf-8")
    profiles = json.loads(args.profiles.read_text(encoding="utf-8"))
    quality = json.loads(args.quality.read_text(encoding="utf-8")) if args.quality else None
    atomic_write_text(args.dashboard, enhance_html(source, profiles, quality))
    print(json.dumps({"dashboard": str(args.dashboard), "entity_detail": True, "snapshot_diff": True, "quality_overlay": quality is not None}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
