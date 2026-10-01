import { ElementDefinition } from 'cytoscape';
import { useMemo, useState } from 'preact/hooks';
import { useApp } from '../app';
import { Index, Relation, datedUpTo, holds, stepAt } from '../model';
import { memberships, parents } from '../sets';
import { GraphCanvas, GROUP_COLORS } from '../components/GraphCanvas';
import { orgFill, orgStroke } from '../palette';
import { ChLink, Empty, Ent, Evidence, Panel, Since, Tabs } from '../components/common';

type Mode = 'focus' | 'circles' | 'window';
const PEOPLE_GROUPS = ['family', 'romance', 'mentorship', 'ally', 'hostile', 'affiliation', 'identity'];
const MAX_NODES = 400;
const TIER_RANK: Record<string, number> = { protagonist: 0, core: 1, major: 2, minor: 3, background: 4 };

export function RelationsView({ focus }: { focus?: string }) {
  const { ix, ch, go } = useApp();
  const [mode, setMode] = useState<Mode>(focus ? 'focus' : 'focus');
  const [groups, setGroups] = useState<Set<string>>(new Set(PEOPLE_GROUPS));
  const [hops, setHops] = useState(1);
  const [minTier, setMinTier] = useState(3);
  const [picked, setPicked] = useState<{ id: string; kind: 'node' | 'edge' } | null>(null);
  const center = focus && ix.visible(focus, ch) ? focus : (ix.m.meta.protagonists ?? []).find((p) => ix.visible(p, ch));

  const graph = useMemo(() => {
    if (mode === 'focus') return center ? egoGraph(ix, ch, center, hops, groups) : { elements: [], note: '没有主角或焦点人物。' };
    if (mode === 'circles') return setGraph(ix, ch, groupsFilter(groups), (id) => TIER_RANK[ix.entity(id)!.tier] <= minTier);
    const cast = windowCast(ix, ch, 10);
    return setGraph(ix, ch, groupsFilter(groups), (id) => cast.has(id));
  }, [ix, ch, mode, center, hops, groups, minTier]);

  const key = `${mode}|${ch}|${center}|${hops}|${[...groups].join()}|${minTier}`;
  return (
    <div class="relations">
      <div class="roster-bar">
        <Tabs tabs={[['focus', '焦点人物'], ['circles', '圈层（势力 ⊃ 成员）'], ['window', '近 10 章出场']]} value={mode} onChange={(m) => { setMode(m); setPicked(null); }} />
        <div class="group-filter">
          {PEOPLE_GROUPS.map((g) => (
            <label style={{ color: GROUP_COLORS[g] }}>
              <input type="checkbox" checked={groups.has(g)} onChange={() => { const n = new Set(groups); n.has(g) ? n.delete(g) : n.add(g); setGroups(n); }} />
              {ix.label('relation_groups', g)}
            </label>
          ))}
        </div>
        {mode === 'focus' && <label class="opt">范围 <select value={hops} onChange={(e) => setHops(Number((e.target as HTMLSelectElement).value))}><option value={1}>一度</option><option value={2}>两度</option></select></label>}
        {mode === 'circles' && <label class="opt">人物 <select value={minTier} onChange={(e) => setMinTier(Number((e.target as HTMLSelectElement).value))}>
          <option value={1}>核心以上</option><option value={2}>主要以上</option><option value={3}>次要以上</option><option value={4}>全部</option></select></label>}
      </div>
      <div class="cols wide-left">
        <div class="col-main">
          <Panel title={mode === 'focus' && center ? `${ix.name(center, ch)} 的关系（截至第${ch}章）` : `截至第${ch}章`} id="graph"
            extra={<span class="muted">{graph.note ?? '框 = 集合（势力、关系类别、社交圈），框可以套框；虚线 = 敌对或轻蔑'}{mode !== 'focus' ? ' · 悬停或点人物显示其关系线' : ''}</span>}>
            {graph.elements.length ? <GraphCanvas elements={graph.elements} layoutKey={key} edgesOnDemand={mode !== 'focus'} onPick={(id, kind) => setPicked({ id, kind })} />
              : <Empty>截至本章没有可画的关系。</Empty>}
          </Panel>
        </div>
        <div class="col-side">
          {picked ? <PickedPanel picked={picked} onFocus={(id) => go('relations', id)} />
            : <Panel title="说明" id="graph-help"><p class="muted">点人物看关系详情，悬停高亮邻居；拖动章节轴，图会只保留截至该章有效的关系。</p></Panel>}
        </div>
      </div>
    </div>
  );
}

const groupsFilter = (groups: Set<string>) => (r: Relation) => groups.has(r.group);

function personEdge(ix: Index, ch: number, r: Relation, extra: Record<string, unknown> = {}): ElementDefinition {
  const stance = stepAt(r.stance, ch)?.[1];
  return { data: { id: r.id, source: r.s, target: r.t, group: r.group, stance, label: ix.label('relations', r.type), ...extra } };
}

function personNode(ix: Index, ch: number, id: string, extra: Record<string, unknown> = {}): ElementDefinition {
  const e = ix.entity(id)!;
  const size = { protagonist: 34, core: 26, major: 20, minor: 15, background: 11 }[e.tier] ?? 12;
  return { data: { id, label: ix.name(id, ch), type: e.type, size, protagonist: e.tier === 'protagonist', ...extra } };
}

/** Ego network: neighbours boxed by relation category, so the categories read as sets. */
function egoGraph(ix: Index, ch: number, center: string, hops: number, groups: Set<string>) {
  const els: ElementDefinition[] = [];
  const nodes = new Map<string, string | undefined>([[center, undefined]]);
  const edges: Relation[] = [];
  let frontier = [center];
  for (let h = 0; h < hops; h++) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const r of ix.relationsAt(id, ch)) {
        if (!groups.has(r.group)) continue;
        const other = r.s === id ? r.t : r.s;
        const t = ix.entity(other)?.type;
        if (t !== 'character' && t !== 'organization') continue;
        edges.push(r);
        if (!nodes.has(other)) { nodes.set(other, h === 0 ? r.group : `hop2`); next.push(other); }
        if (nodes.size > MAX_NODES) break;
      }
    }
    frontier = next;
  }
  const used = new Set([...nodes.values()].filter(Boolean) as string[]);
  for (const g of used) {
    els.push({ data: { id: `box:${g}`, label: g === 'hop2' ? '二度关系' : ix.label('relation_groups', g), fill: tint(GROUP_COLORS[g] ?? '#9aa7b8'), stroke: GROUP_COLORS[g] } });
  }
  for (const [id, g] of nodes) els.push(personNode(ix, ch, id, { parent: g ? `box:${g}` : undefined, focus: id === center }));
  const seen = new Set<string>();
  for (const r of edges) if (!seen.has(r.id) && nodes.has(r.s) && nodes.has(r.t)) { seen.add(r.id); els.push(personEdge(ix, ch, r, { hidelabel: edges.length > 60 })); }
  return { elements: els, note: undefined as string | undefined };
}

/** People inside their primary organization's box; organizations nest; the unaffiliated form social circles. */
function setGraph(ix: Index, ch: number, edgeOk: (r: Relation) => boolean, include: (id: string) => boolean) {
  const people = Object.entries(ix.m.entities)
    .filter(([id, e]) => e.type === 'character' && e.first <= ch && include(id))
    .sort((a, b) => (b[1].events ?? 0) - (a[1].events ?? 0))
    .slice(0, MAX_NODES).map(([id]) => id);
  const keep = new Set(people);
  const member = memberships(ix, ch);
  const orgParent = parents(ix, ch, 'organization');
  const rels = ix.m.relations.filter((r) => holds(r.from, r.to, ch) && keep.has(r.s) && keep.has(r.t) && r.s !== r.t && edgeOk(r));
  const els: ElementDefinition[] = [];
  const orgsUsed = new Set<string>();
  const addOrg = (org: string) => {
    if (orgsUsed.has(org)) return;
    orgsUsed.add(org);
    const p = orgParent.get(org);
    if (p) addOrg(p);
    els.push({ data: { id: `set:${org}`, label: ix.name(org, ch), parent: p ? `set:${p}` : undefined, kind: 'org', fill: orgFill(org), stroke: orgStroke(org) } });
  };
  const circles = socialCircles(people.filter((p) => !member.has(p)), rels);
  for (const id of people) {
    const m = member.get(id);
    let parent: string | undefined;
    if (m?.primary) { addOrg(m.primary); parent = `set:${m.primary}`; }
    else if (circles.has(id)) parent = `circle:${circles.get(id)}`;
    els.push(personNode(ix, ch, id, { parent, multi: m && m.orgs.length > 1 ? m.orgs.length : undefined, color: m?.primary ? orgStroke(m.primary) : undefined }));
  }
  for (const label of new Set(circles.values())) {
    els.push({ data: { id: `circle:${label}`, label: `${ix.name(label, ch)} 的圈子`, kind: 'circle', fill: '#fbfbf7', stroke: '#c9c3a6' } });
  }
  for (const r of rels) els.push(personEdge(ix, ch, r, { hidelabel: true }));
  const multi = people.filter((p) => (member.get(p)?.orgs.length ?? 0) > 1).length;
  return { elements: els, note: `${people.length} 人 · ${orgsUsed.size} 个势力框${multi ? ` · ${multi} 人同属多个势力（放在主要势力里）` : ''} · 无势力的人按关系聚成圈子（虚线框）` };
}

/** Label propagation over visible person–person relations; circles of one are dropped. */
function socialCircles(people: string[], rels: Relation[]): Map<string, string> {
  const set = new Set(people), adj = new Map<string, string[]>();
  for (const r of rels) {
    if (!set.has(r.s) || !set.has(r.t)) continue;
    adj.set(r.s, [...(adj.get(r.s) ?? []), r.t]);
    adj.set(r.t, [...(adj.get(r.t) ?? []), r.s]);
  }
  const label = new Map(people.map((p) => [p, p]));
  const order = [...people].sort();
  for (let round = 0; round < 8; round++) {
    let changed = false;
    for (const p of order) {
      const counts = new Map<string, number>();
      for (const q of adj.get(p) ?? []) counts.set(label.get(q)!, (counts.get(label.get(q)!) ?? 0) + 1);
      if (!counts.size) continue;
      const best = [...counts.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))[0][0];
      if (best !== label.get(p)) { label.set(p, best); changed = true; }
    }
    if (!changed) break;
  }
  const size = new Map<string, number>();
  for (const l of label.values()) size.set(l, (size.get(l) ?? 0) + 1);
  // name each circle after its best-connected member
  const out = new Map<string, string>();
  const lead = new Map<string, string>();
  for (const p of people) {
    const l = label.get(p)!;
    if ((size.get(l) ?? 0) < 3) continue;
    const cur = lead.get(l);
    if (!cur || (adj.get(p)?.length ?? 0) > (adj.get(cur)?.length ?? 0)) lead.set(l, p);
  }
  for (const p of people) { const l = label.get(p)!; if (lead.has(l)) out.set(p, lead.get(l)!); }
  return out;
}

function windowCast(ix: Index, ch: number, span: number): Set<string> {
  const out = new Set<string>();
  for (const n of ix.chapterList) {
    if (n > ch || n <= ch - span) continue;
    for (const r of ix.chapters.get(n)?.cast ?? []) if (r.mode !== 'mentioned' && ix.entity(r.id)?.type === 'character') out.add(r.id);
  }
  return out;
}

function tint(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const mix = (v: number) => Math.round(v + (255 - v) * 0.88);
  return `rgb(${mix(n >> 16)},${mix((n >> 8) & 255)},${mix(n & 255)})`;
}

function PickedPanel({ picked, onFocus }: { picked: { id: string; kind: 'node' | 'edge' }; onFocus: (id: string) => void }) {
  const { ix, ch, go } = useApp();
  if (picked.kind === 'edge') {
    const r = ix.m.relations.find((x) => x.id === picked.id);
    if (!r) return null;
    const stance = stepAt(r.stance, ch)?.[1];
    return (
      <Panel title="关系" id="picked-edge">
        <p><Ent id={r.s} /> <span class="rel-type">{ix.label('relations', r.type)}</span> <Ent id={r.t} /> <Since from={r.from} to={r.to} /></p>
        {stance && <p>当前态度：{ix.label('stances', stance)}</p>}
        {(r.stance?.length ?? 0) > 1 && <p class="muted">态度变化：{datedUpTo(r.stance, ch).map((s) => <><ChLink n={s[0]} />{ix.label('stances', s[1])} </>)}</p>}
        <ul class="timeline">{datedUpTo(r.notes, ch).map((n) => <li><ChLink n={n[0]} />{n[1]}</li>)}</ul>
        <Evidence ids={r.ev} />
      </Panel>
    );
  }
  const id = picked.id;
  if (!ix.entity(id)) return null;
  const rels = ix.relationsAt(id, ch).filter((r) => PEOPLE_GROUPS.includes(r.group));
  return (
    <Panel title={ix.name(id, ch)} id="picked-node" extra={<button class="link" onClick={() => go('people', id)}>人物页 ›</button>}>
      <button class="link" onClick={() => onFocus(id)}>以 TA 为焦点</button>
      <ul class="changes">
        {rels.map((r) => {
          const other = r.s === id ? r.t : r.s;
          const stance = stepAt(r.stance, ch)?.[1];
          return <li><span class="rel-type" style={{ color: GROUP_COLORS[r.group] }}>{ix.label('relations', r.type)}</span> <Ent id={other} />{stance && <span class="stance">（{ix.label('stances', stance)}）</span>}<Since from={r.from} to={r.to} /></li>;
        })}
      </ul>
      {!rels.length && <Empty>截至本章没有人物关系。</Empty>}
    </Panel>
  );
}
