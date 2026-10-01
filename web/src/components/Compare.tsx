import { useState } from 'preact/hooks';
import { useApp } from '../app';
import { holds } from '../model';
import { ChLink, Empty, Ent, Ents, Panel } from './common';

/** Everything that changed between an earlier chapter A and the current chapter: states, relations, new faces. */
export function Compare() {
  const { ix, ch } = useApp();
  const list = ix.chapterList.filter((c) => c < ch);
  const [from, setFrom] = useState(list[Math.max(0, list.length - 10)] ?? ch);
  if (!list.length) return <Panel title="对比" id="compare"><Empty>这是第一章，没有可对比的章节。</Empty></Panel>;
  const facts = ix.m.facts.filter((f) => f.from > from && f.from <= ch);
  const byEntity = new Map<string, typeof facts>();
  for (const f of facts) byEntity.set(f.e, [...(byEntity.get(f.e) ?? []), f]);
  const began = ix.m.relations.filter((r) => r.from > from && r.from <= ch && ix.visible(r.s, ch) && ix.visible(r.t, ch));
  const ended = ix.m.relations.filter((r) => r.to != null && r.to >= from && r.to < ch && holds(r.from, r.to, from));
  const newcomers = Object.entries(ix.m.entities).filter(([, e]) => e.first > from && e.first <= ch && e.type === 'character').map(([id]) => id);
  const ms = (ix.m.milestones ?? []).filter((m) => m.ch > from && m.ch <= ch);
  return (
    <Panel title="对比" id="compare" extra={
      <label class="opt">从第 <select value={from} onChange={(e) => setFrom(Number((e.target as HTMLSelectElement).value))}>
        {list.map((n) => <option value={n}>{n}</option>)}</select> 章到第 {ch} 章</label>}>
      <div class="compare">
        <div>
          <h4>里程碑 {ms.length}</h4>
          {ms.length ? <ul class="timeline">{ms.map((m) => <li><ChLink n={m.ch} />{m.label}</li>)}</ul> : <Empty>无</Empty>}
          <h4>新登场人物 {newcomers.length}</h4>
          {newcomers.length ? <Ents ids={newcomers} max={40} /> : <Empty>无</Empty>}
        </div>
        <div>
          <h4>状态变化（{byEntity.size} 人）</h4>
          {byEntity.size ? <ul class="changes">{[...byEntity.entries()].slice(0, 40).map(([id, rows]) => (
            <li><Ent id={id} />：{rows.map((f) => <span class="fact">{ix.label('facets', f.facet)} {f.value} <ChLink n={f.from} /></span>)}</li>
          ))}</ul> : <Empty>无</Empty>}
        </div>
        <div>
          <h4>新关系 {began.length}</h4>
          {began.length ? <ul class="changes">{began.slice(0, 40).map((r) => <li><Ent id={r.s} /> {ix.label('relations', r.type)} <Ent id={r.t} /> <ChLink n={r.from} /></li>)}</ul> : <Empty>无</Empty>}
          <h4>结束的关系 {ended.length}</h4>
          {ended.length ? <ul class="changes">{ended.slice(0, 40).map((r) => <li><Ent id={r.s} /> {ix.label('relations', r.type)} <Ent id={r.t} /> 止于 <ChLink n={r.to!} /></li>)}</ul> : <Empty>无</Empty>}
        </div>
      </div>
    </Panel>
  );
}
