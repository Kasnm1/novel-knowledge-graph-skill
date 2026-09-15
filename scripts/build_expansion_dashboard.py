#!/usr/bin/env python3
"""Build the complete chapter-synchronized expansion dashboard.

The dashboard consumes only derived view models. It never writes story facts
back into graph.json. All temporal panels follow one shared chapter slider.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from derive_novel_views import build_views


def load_views(args: argparse.Namespace) -> dict:
    if args.views:
        return json.loads(args.views.read_text(encoding="utf-8"))
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    return build_views(graph, args.protagonist_id, max(1, args.relation_gap_threshold))


def build_html(views: dict) -> str:
    payload = json.dumps(views, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = str(views.get("metadata", {}).get("source_title") or "Novel Knowledge Graph")
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · Extended Dashboard</title>
<style>
:root{{--bg:#0d1117;--panel:#161b22;--line:#30363d;--text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;--gold:#d29922}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif}}
header{{position:sticky;top:0;z-index:10;background:#0d1117f2;border-bottom:1px solid var(--line);padding:14px 20px}}
h1{{font-size:19px;margin:0 0 10px}}h2{{font-size:17px}}.toolbar{{display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
input[type=range]{{min-width:280px;flex:1}}.muted{{color:var(--muted);font-size:12px}}
nav{{position:sticky;top:86px;z-index:9;display:flex;gap:7px;overflow:auto;padding:8px 14px;background:var(--panel);border-bottom:1px solid var(--line)}}
nav button{{white-space:nowrap;background:#21262d;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:7px 10px;cursor:pointer}}
nav button.active{{border-color:var(--accent)}}main{{max-width:1700px;margin:auto;padding:18px}}.panel{{display:none}}.panel.active{{display:block}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}}.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;margin:8px 0}}
.metric{{font-size:27px;font-weight:750}}.scroll{{overflow:auto;max-height:70vh;border:1px solid var(--line);border-radius:10px}}
table{{width:100%;border-collapse:collapse;font-size:13px;background:var(--panel)}}th,td{{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}}th{{background:#21262d;position:sticky;top:0}}
.badge{{display:inline-block;padding:2px 7px;border:1px solid var(--line);border-radius:999px;margin:2px;font-size:11px}}
.empty{{padding:24px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:10px}}
#world-map,#co-map{{height:58vh;min-height:430px;border:1px solid var(--line);border-radius:12px}}.track{{position:relative;height:30px;background:#21262d;border-radius:6px;margin:6px 0;min-width:600px}}
.bar{{position:absolute;top:4px;height:22px;background:#1f6feb;border-radius:5px;padding:2px 6px;overflow:hidden;white-space:nowrap;font-size:11px}}.point{{position:absolute;top:4px;width:8px;height:22px;background:var(--gold);border-radius:3px}}
code,pre{{font-size:11px;white-space:pre-wrap}}a{{color:#79c0ff}}
</style><script src="cytoscape-3.34.3.min.js"></script></head><body>
<header><h1>{title} · 成长 / 世界 / 人际 / 叙事全景</h1><div class="toolbar"><label>章节 <strong id="chapter-label"></strong></label><input id="chapter" type="range" step="1"><span class="muted">所有时序面板共用这一章节快照；虚构地图只展示证据支持的拓扑和控制权。</span></div></header>
<nav id="tabs"></nav><main>
<section class="panel" data-panel="overview"><h2>总览</h2><div id="overview" class="cards"></div><h3>本章变更</h3><div id="diff"></div></section>
<section class="panel" data-panel="achievements"><h2>主角成就泳道</h2><div id="achievements"></div></section>
<section class="panel" data-panel="combat"><h2>战绩表：对手 — 结果 — 当时境界</h2><div id="combat"></div></section>
<section class="panel" data-panel="resources"><h2>资源仓库</h2><div id="resources"></div></section>
<section class="panel" data-panel="world"><h2>世界地图 / 势力版图回放</h2><div id="world-map"></div><div id="world-note" class="muted"></div></section>
<section class="panel" data-panel="skills"><h2>技能分类矩阵</h2><div id="skills"></div></section>
<section class="panel" data-panel="relations"><h2>关系甘特图 / 配角关系覆盖 / 同框网络</h2><div id="relations"></div><h3>关系甘特</h3><div id="relation-gantt"></div><h3>同框网络</h3><div id="co-map"></div></section>
<section class="panel" data-panel="commitments"><h2>承诺生命周期 / 恩怨账本</h2><div id="commitments"></div><h3>恩情 / 亏欠</h3><div id="favors"></div></section>
<section class="panel" data-panel="knowledge"><h2>知情不对称矩阵 / 秘密传播</h2><div id="knowledge"></div><h3>传播链</h3><div id="propagation"></div></section>
<section class="panel" data-panel="foreshadowing"><h2>伏笔甘特带</h2><div id="foreshadowing"></div><h3>Payoff / 爽点跨度</h3><div id="payoffs"></div></section>
<section class="panel" data-panel="levels"><h2>战力阶梯 / 等级膨胀</h2><div id="levels"></div></section>
<section class="panel" data-panel="rhythm"><h2>章节节奏心电图 / POV / 断章</h2><div id="rhythm"></div></section>
<section class="panel" data-panel="romance"><h2>感情线里程碑轨道</h2><div id="romance"></div></section>
<section class="panel" data-panel="mortality"><h2>死亡 / 复活名册</h2><div id="mortality"></div><h3>血脉 / 师承 / 物品来源链</h3><div id="inheritance"></div></section>
<section class="panel" data-panel="economy"><h2>交易 / 财富</h2><div id="economy"></div></section>
<section class="panel" data-panel="rules"><h2>世界规则 / 禁令 / 诅咒 / 配方</h2><div id="rules"></div></section>
<section class="panel" data-panel="narrative"><h2>人物声音 / 作者写法</h2><div id="narrative"></div></section>
<section class="panel" data-panel="audit"><h2>覆盖审计</h2><div id="audit"></div></section>
</main><script>
const D={payload};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const cs=Number(D.metadata?.chapter_start||0), ce=Number(D.metadata?.chapter_end||0);
const slider=document.getElementById('chapter'), label=document.getElementById('chapter-label');slider.min=cs;slider.max=ce;slider.value=ce;
const tabs=[['overview','总览'],['achievements','成就'],['combat','战绩'],['resources','资源'],['world','世界地图'],['skills','技能'],['relations','关系'],['commitments','承诺'],['knowledge','秘密'],['foreshadowing','伏笔'],['levels','战力'],['rhythm','节奏'],['romance','感情'],['mortality','生死传承'],['economy','经济'],['rules','规则'],['narrative','写法'],['audit','覆盖审计']];
const nav=document.getElementById('tabs');
function activate(id){{document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.target===id));document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.dataset.panel===id));if(id==='world')renderWorld();if(id==='relations')renderCo();}}
tabs.forEach(([id,n],i)=>{{let b=document.createElement('button');b.textContent=n;b.dataset.target=id;b.onclick=()=>activate(id);if(!i)b.classList.add('active');nav.appendChild(b)}});document.querySelector('[data-panel=overview]').classList.add('active');
const ch=()=>Number(slider.value), pct=x=>ce>cs?Math.max(0,Math.min(100,(Number(x)-cs)/(ce-cs)*100)):0;
function badges(values){{return (values||[]).map(x=>`<span class="badge">${{esc(x)}}</span>`).join('')}}
function table(headers,rows){{if(!rows.length)return '<div class="empty">当前章节范围没有可显示数据</div>';return `<div class="scroll"><table><thead><tr>${{headers.map(x=>`<th>${{esc(x)}}</th>`).join('')}}</tr></thead><tbody>${{rows.map(r=>`<tr>${{r.map(x=>`<td>${{x??''}}</td>`).join('')}}</tr>`).join('')}}</tbody></table></div>`}}
function renderOverview(){{let a=(D.achievements||[]).filter(x=>x.chapter<=ch()),b=(D.combat_records||[]).filter(x=>x.chapter<=ch()),open=(D.commitments||[]).filter(x=>x.created_chapter<=ch()&&['active','partially_fulfilled','uncertain'].includes(x.status)),fs=(D.foreshadowing?.unresolved||[]).filter(x=>x.planted_chapter<=ch());let metrics=[[a.length,'成就'],[b.filter(x=>x.result==='victory').length,'胜场'],[open.length,'未完承诺'],[fs.length,'未收伏笔'],[(D.world?.locations||[]).filter(x=>!x.first_chapter||x.first_chapter<=ch()).length,'已出现地点'],[(D.cooccurrence?.relation_gap_candidates||[]).length,'配角关系待核']];document.getElementById('overview').innerHTML=metrics.map(x=>`<div class="card"><div class="metric">${{x[0]}}</div><div class="muted">${{x[1]}}</div></div>`).join('');let bucket=(D.snapshot_changes?.by_chapter||[]).find(x=>Number(x.chapter)===ch());document.getElementById('diff').innerHTML=table(['人物','分面','动作','之前','之后'],(bucket?.changes||[]).map(x=>[esc(x.entity),esc(x.facet),esc(x.action),`<code>${{esc(JSON.stringify(x.before))}}</code>`,`<code>${{esc(JSON.stringify(x.after))}}</code>`]))}}
function renderAchievements(){{document.getElementById('achievements').innerHTML=table(['章','类别','里程碑','重要度'],(D.achievements||[]).filter(x=>x.chapter<=ch()).map(x=>[x.chapter,esc(x.category),esc(x.title),x.importance]))}}
function renderCombat(){{document.getElementById('combat').innerHTML=table(['章','对手','结果','主角当时境界','对手当时境界','地点','赌注'],(D.combat_records||[]).filter(x=>x.chapter<=ch()).map(x=>[x.chapter,esc((x.opponents||[]).join('、')),esc(x.result),`<code>${{esc(JSON.stringify(x.protagonist_level||{{}}))}}</code>`,`<code>${{esc(JSON.stringify(x.opponent_levels||{{}}))}}</code>`,esc(x.location||''),badges(x.stake_ids)]))}}
function renderResources(){{let rows=(D.resources?.items||[]).map(x=>{{let h=(x.role_history||[]).filter(r=>Number(r.chapter||0)<=ch()),g=h.filter(r=>r.action==='gained'),loc=[...new Set(g.map(r=>r.location).filter(Boolean))];return [esc(x.name),badges(x.categories),esc(x.rarity||''),esc(x.supply||''),g.length,esc(loc.join('、')),`<code>${{esc(JSON.stringify(x.current_quantities||{{}}))}}</code>`]}}).filter(r=>r[4]>0||r[2]||r[3]);document.getElementById('resources').innerHTML=table(['资源','分类','稀有度','供给','获得次数','获得地点','当前数量'],rows)}}
function renderSkills(){{document.getElementById('skills').innerHTML=table(['技能','分类','人物/掌握关系'],(D.skills||[]).map(x=>[esc(x.name),badges(x.categories),esc((x.holders||[]).map(h=>`${{h.entity}}:${{h.relation_type}}`).join('；'))]))}}
function renderRelations(){{let gaps=(D.cooccurrence?.relation_gap_candidates||[]).filter(x=>(x.shared_events||[]).some(e=>Number(e.chapter||0)<=ch()));document.getElementById('relations').innerHTML=table(['人物A','人物B','同框次数','状态'],gaps.map(x=>[esc(x.characters?.[0]),esc(x.characters?.[1]),(x.shared_events||[]).filter(e=>Number(e.chapter||0)<=ch()).length,'待核：高同框但无关系边']));let rel=(D.relation_timeline?.relations||[]).filter(r=>Number(r.valid_from||0)<=ch());document.getElementById('relation-gantt').innerHTML=rel.slice(0,250).map(r=>`<div class="card"><b>${{esc(r.source)}} → ${{esc(r.target)}}</b> ${{badges([r.relation_type,r.status])}}<div class="track"><div class="bar" style="left:${{pct(r.valid_from)}}%;width:${{Math.max(1,pct(r.valid_to||ch())-pct(r.valid_from))}}%">${{esc(r.relation_type)}}</div></div></div>`).join('')||'<div class="empty">无关系数据</div>'}}
function renderCommitments(){{document.getElementById('commitments').innerHTML=table(['建立章','类型','立约人','对象','内容','期限','状态','解决章'],(D.commitments||[]).filter(x=>Number(x.created_chapter||0)<=ch()).map(x=>[x.created_chapter,esc(x.kind),esc((x.promisors||[]).join('、')),esc((x.counterparties||[]).join('、')),esc(x.terms),x.deadline_chapter??esc(x.deadline_story_time||''),esc(x.status),x.resolved_chapter&&x.resolved_chapter<=ch()?x.resolved_chapter:'']));document.getElementById('favors').innerHTML=table(['欠方','受恩方','强度','开始','结束','状态'],(D.favor_ledger||[]).filter(x=>Number(x.valid_from||0)<=ch()).map(x=>[esc(x.debtor),esc(x.creditor),x.strength,x.valid_from,x.valid_to??'',esc(x.status)]))}}
function knowledgeState(history){{let rows=(history||[]).filter(x=>Number(x.chapter||0)<=ch());return rows.length?rows[rows.length-1]:null}}
function renderKnowledge(){{let secrets=D.knowledge?.secrets||[],people=[...new Set(secrets.flatMap(s=>(s.people||[]).map(p=>p.entity)))];let head=['人物',...secrets.map(s=>s.secret)],rows=people.map(p=>[esc(p),...secrets.map(s=>{{let person=(s.people||[]).find(x=>x.entity===p),last=person?knowledgeState(person.history):null;return last?`<span class="badge">${{esc(last.action)}} · 第${{last.chapter}}章</span>`:'—'}})]);document.getElementById('knowledge').innerHTML=table(head,rows);document.getElementById('propagation').innerHTML=table(['章','秘密','从','到','方式'],(D.knowledge?.propagation||[]).filter(x=>Number(x.chapter||0)<=ch()).map(x=>[x.chapter,esc(x.secret),esc(x.from||'未知/自行发现'),esc(x.to),esc(x.mode)]))}}
function renderForeshadowing(){{let rows=(D.foreshadowing?.rows||[]).filter(x=>Number(x.planted_chapter||0)<=ch());document.getElementById('foreshadowing').innerHTML=rows.map(x=>`<div class="card"><b>${{esc(x.label)}}</b><span class="muted"> 第${{x.planted_chapter}}章 → ${{x.payoff_chapter&&x.payoff_chapter<=ch()?`第${{x.payoff_chapter}}章`:'未回收'}}</span><div class="track"><div class="bar" style="left:${{pct(x.planted_chapter)}}%;width:${{Math.max(1,pct(x.payoff_chapter&&x.payoff_chapter<=ch()?x.payoff_chapter:ch())-pct(x.planted_chapter))}}%">${{esc(x.status)}}</div></div></div>`).join('')||'<div class="empty">无伏笔数据</div>';document.getElementById('payoffs').innerHTML=table(['兑现章','类型','标题','铺垫跨度'],(D.payoffs?.rows||[]).filter(x=>Number(x.chapter||0)<=ch()).map(x=>[x.chapter,esc(x.kind),esc(x.title),esc((x.setups||[]).map(s=>s.span==null?'?':`${{s.span}}章`).join('、'))]))}}
function renderLevels(){{let rows=[];(D.levels?.series||[]).forEach(e=>Object.entries(e.facets||{{}}).forEach(([f,arr])=>(arr||[]).filter(x=>Number(x.chapter||0)<=ch()).forEach(x=>rows.push([esc(e.entity),esc(f),x.chapter,esc(x.action),`<code>${{esc(JSON.stringify(x.after))}}</code>`]))));document.getElementById('levels').innerHTML=table(['人物','等级轴/分面','章','动作','当时值'],rows)}}
function renderRhythm(){{document.getElementById('rhythm').innerHTML=table(['章','事件数','事件类型','POV','场景','断章','故事内时间'],(D.chapter_rhythm?.chapters||[]).filter(x=>x.chapter<=ch()).map(x=>[x.chapter,x.event_total,esc(Object.entries(x.events||{{}}).map(([k,v])=>`${{k}}:${{v}}`).join('；')),esc((x.pov||[]).join('、')),x.scene_count??'',esc(x.cliffhanger_type||''),esc(typeof x.story_time==='string'?x.story_time:JSON.stringify(x.story_time||''))]))}}
function renderRomance(){{document.getElementById('romance').innerHTML=(D.romance?.routes||[]).map(r=>`<div class="card"><b>${{esc(r.character)}}</b> ${{badges([r.status])}}<div class="track">${{(r.milestones||[]).filter(m=>m.chapter<=ch()).map(m=>`<span class="point" title="${{esc(m.kind)}} · 第${{m.chapter}}章" style="left:${{pct(m.chapter)}}%"></span>`).join('')}}</div></div>`).join('')||'<div class="empty">无感情路线</div>'}}
function renderMortality(){{document.getElementById('mortality').innerHTML=table(['章','人物','凶手','死因','复活机制/代价'],(D.mortality?.events||[]).filter(x=>Number(x.chapter||0)<=ch()).map(x=>[x.chapter,esc(x.entity),esc((x.killers||[]).join('、')),esc(x.cause),esc([x.revival_mechanism,x.cost].filter(Boolean).join(' / '))]));document.getElementById('inheritance').innerHTML=table(['来源','关系','去向','章'],(D.inheritance?.relations||[]).filter(x=>Number(x.valid_from||0)<=ch()).map(x=>[esc(x.source),esc(x.relation_type),esc(x.target),x.valid_from]))}}
function renderEconomy(){{document.getElementById('economy').innerHTML=table(['章','买方','卖方','物品','金额','货币'],(D.economy?.transactions||[]).filter(x=>Number(x.chapter||0)<=ch()).map(x=>[x.chapter,esc((x.buyers||[]).join('、')),esc((x.sellers||[]).join('、')),esc((x.items||[]).join('、')),`<code>${{esc(JSON.stringify(x.amount))}}</code>`,esc(x.currency||x.unit||'')]))}}
function renderRules(){{document.getElementById('rules').innerHTML=table(['概念','分类','首次','说明'],(D.rules?.concepts||[]).filter(x=>!x.first_chapter||x.first_chapter<=ch()).map(x=>[esc(x.name),badges(x.categories),x.first_chapter??'',esc(x.summary||'')]))}}
function renderNarrative(){{document.getElementById('narrative').innerHTML=(D.narrative?.character_voice||[]).map(x=>`<div class="card"><b>${{esc(x.entity)}}</b><pre><code>${{esc(JSON.stringify(x.observations,null,2))}}</code></pre></div>`).join('')||'<div class="empty">暂无人物声音 observation；POV、场景数和断章仍在“节奏”中可见。</div>'}}
function renderAudit(){{let rows=Object.entries(D.coverage||{{}}).map(([k,v])=>[esc(k),v.covered,v.total,v.total?`${{(v.covered/v.total*100).toFixed(1)}}%`:'N/A（分母为0，不视为通过）']);document.getElementById('audit').innerHTML=`<div class="cards"><div class="card"><div class="metric">${{D.contract_summary?.valid?'PASS':'FAIL'}}</div><div class="muted">扩展契约</div></div><div class="card"><div class="metric">${{D.contract_summary?.error_count||0}}</div><div class="muted">错误</div></div><div class="card"><div class="metric">${{D.contract_summary?.warning_count||0}}</div><div class="muted">警告</div></div></div>`+table(['能力','已覆盖','分母','比例'],rows)}}
let cy=null,cocy=null;
function renderWorld(){{let container=document.getElementById('world-map');if(!window.cytoscape){{container.innerHTML='<div class="empty">Cytoscape 未加载</div>';return}}let loc=(D.world?.locations||[]).filter(x=>!x.first_chapter||x.first_chapter<=ch()),visible=new Set(loc.map(x=>x.id)),els=loc.map(x=>({{data:{{id:x.id,label:x.name,kind:'location'}}}}));(D.world?.hierarchy||[]).filter(e=>visible.has(e.child_id)&&visible.has(e.parent_id)&&Number(e.valid_from||0)<=ch()&&(!e.valid_to||e.valid_to>=ch())).forEach(e=>els.push({{data:{{id:'h:'+e.relation_id,source:e.child_id,target:e.parent_id,kind:'hierarchy'}}}}));(D.world?.controls||[]).filter(e=>visible.has(e.location_id)&&Number(e.valid_from||0)<=ch()&&(!e.valid_to||e.valid_to>=ch())).forEach(e=>{{let oid='org:'+e.organization_id;if(!els.some(x=>x.data.id===oid))els.push({{data:{{id:oid,label:e.organization_name,kind:'organization'}}}});els.push({{data:{{id:'c:'+e.relation_id,source:e.location_id,target:oid,kind:'control'}}}})}});if(cy)cy.destroy();cy=cytoscape({{container,elements:els,style:[{{selector:'node',style:{{label:'data(label)','background-color':'#58a6ff',color:'#e6edf3','text-outline-color':'#0d1117','text-outline-width':2,'font-size':10}}}},{{selector:'node[kind="organization"]',style:{{'background-color':'#d29922',shape:'round-rectangle'}}}},{{selector:'edge[kind="hierarchy"]',style:{{width:1,'line-color':'#8b949e','target-arrow-shape':'triangle','target-arrow-color':'#8b949e'}}}},{{selector:'edge[kind="control"]',style:{{width:2,'line-style':'dashed','line-color':'#d29922','target-arrow-shape':'triangle','target-arrow-color':'#d29922'}}}}],layout:{{name:'breadthfirst',directed:true,padding:30}}}});document.getElementById('world-note').textContent=`地点 ${{loc.length}} · 层级边 ${{els.filter(e=>e.data.kind==='hierarchy').length}} · 控制边 ${{els.filter(e=>e.data.kind==='control').length}}`}}
function renderCo(){{let container=document.getElementById('co-map');if(!window.cytoscape)return;let pairs=(D.cooccurrence?.pairs||[]).map(x=>[x,(x.shared_events||[]).filter(e=>Number(e.chapter||0)<=ch()).length]).filter(x=>x[1]>0).slice(0,150),nodes=new Map(),els=[];pairs.forEach(([p,n])=>{{p.character_ids.forEach((id,i)=>nodes.set(id,p.characters[i]));els.push({{data:{{id:'p:'+p.character_ids.join(':'),source:p.character_ids[0],target:p.character_ids[1],count:n}}}})}});nodes.forEach((name,id)=>els.push({{data:{{id,label:name}}}}));if(cocy)cocy.destroy();cocy=cytoscape({{container,elements:els,style:[{{selector:'node',style:{{label:'data(label)','background-color':'#58a6ff',color:'#e6edf3','text-outline-width':2,'text-outline-color':'#0d1117','font-size':10}}}},{{selector:'edge',style:{{width:'mapData(count,1,20,1,8)','line-color':'#8b949e','curve-style':'bezier'}}}}],layout:{{name:'cose',animate:false}}}})}}
function renderAll(){{label.textContent=ch();renderOverview();renderAchievements();renderCombat();renderResources();renderSkills();renderRelations();renderCommitments();renderKnowledge();renderForeshadowing();renderLevels();renderRhythm();renderRomance();renderMortality();renderEconomy();renderRules();renderNarrative();renderAudit();if(document.querySelector('[data-panel=world]').classList.contains('active'))renderWorld();if(document.querySelector('[data-panel=relations]').classList.contains('active'))renderCo()}}
slider.addEventListener('input',renderAll);renderAll();
</script></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--views", type=Path)
    source.add_argument("--graph", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--protagonist-id", action="append", default=[])
    parser.add_argument("--relation-gap-threshold", type=int, default=3)
    args = parser.parse_args()
    views = load_views(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "expansion-dashboard.html"
    output.write_text(build_html(views), encoding="utf-8")
    asset = Path(__file__).resolve().parent.parent / "assets" / "cytoscape-3.34.3.min.js"
    if asset.exists():
        shutil.copy2(asset, args.output_dir / asset.name)
    else:
        print(f"warning: Cytoscape asset not found at {asset}")
    print(json.dumps({"output": str(output), "chapter_end": views.get("metadata", {}).get("chapter_end"), "panels": 18}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
