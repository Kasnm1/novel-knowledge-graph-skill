import { useMemo } from 'preact/hooks';
import { useApp } from '../app';
import { holds } from '../model';
import { memberships, nest, parents, placeLinks, whereabouts } from '../sets';
import { PackChart } from '../components/PackChart';
import { Empty, Ent, Ents, Panel, Tabs } from '../components/common';

type Tab = 'factions' | 'map' | 'levels' | 'catalog';
const PALETTE = ['#e8d5f5', '#d5ecdf', '#f7e3cf', '#d6e4f7', '#f5d5dc', '#e9eccf', '#d3eef0', '#efdcc9'];
const hue = (id: string) => PALETTE[[...id].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7) % PALETTE.length];

export function WorldView({ tab }: { tab?: string }) {
  const { go } = useApp();
  const current = (['factions', 'map', 'levels', 'catalog'].includes(tab ?? '') ? tab : 'factions') as Tab;
  return (
    <div class="world">
      <Tabs tabs={[['factions', '势力图'], ['map', '地图'], ['levels', '等级天梯'], ['catalog', '物品与功法']]} value={current} onChange={(t) => go('world', t)} />
      {current === 'factions' && <Factions />}
      {current === 'map' && <WorldMap />}
      {current === 'levels' && <Levels />}
      {current === 'catalog' && <Catalog />}
    </div>
  );
}

function Factions() {
  const { ix, ch, go } = useApp();
  const data = useMemo(() => {
    const orgs = Object.entries(ix.m.entities).filter(([, e]) => e.type === 'organization' && e.first <= ch).map(([id]) => id);
    const member = memberships(ix, ch);
    const members = new Map<string, string[]>(), ghosts = new Map<string, string[]>();
    let multi = 0;
    for (const [id, m] of member) {
      if (ix.entity(id)?.type === 'organization') continue;
      members.set(m.primary!, [...(members.get(m.primary!) ?? []), id]);
      if (m.orgs.length > 1) multi++;
      for (const o of m.orgs) if (o !== m.primary) ghosts.set(o, [...(ghosts.get(o) ?? []), id]);
    }
    const tree = nest(ix, ch, orgs, parents(ix, ch, 'organization'), members, ghosts, '全部势力', '');
    const between = ix.m.relations.filter((r) => holds(r.from, r.to, ch) && ix.entity(r.s)?.type === 'organization'
      && ix.entity(r.t)?.type === 'organization' && (r.group === 'ally' || r.group === 'hostile'));
    return { tree, orgs: orgs.length, people: [...member.keys()].length, multi, between };
  }, [ix, ch]);

  if (!data.orgs) return <Empty>截至第 {ch} 章还没有出现势力。</Empty>;
  return (
    <div class="cols wide-left">
      <div class="col-main">
        <Panel title={`截至第${ch}章的势力`} count={data.orgs} id="faction-pack"
          extra={<span class="muted">{data.people} 人有归属{data.multi ? ` · ${data.multi} 人同时属于多个势力（虚线圈）` : ''}</span>}>
          <PackChart root={data.tree} onPick={(id) => go('people', id)}
            tint={(id, n) => (n.kind === 'member' || n.kind === 'ghost' ? (ix.entity(id ?? '')?.tier === 'protagonist' ? '#c23d6a' : '#2f6fd6') : id ? hue(id) : undefined)} />
        </Panel>
      </div>
      <div class="col-side">
        <Panel title="势力之间" count={data.between.length} id="faction-relations">
          {data.between.length ? (
            <ul class="changes">{data.between.map((r) => (
              <li><Ent id={r.s} /> <span class={`rel-type g-${r.group}`}>{ix.label('relations', r.type)}</span> <Ent id={r.t} /></li>
            ))}</ul>
          ) : <Empty>没有记录势力之间的结盟或敌对。</Empty>}
        </Panel>
      </div>
    </div>
  );
}

function WorldMap() {
  const { ix, ch, go } = useApp();
  const data = useMemo(() => {
    const places = Object.entries(ix.m.entities).filter(([, e]) => e.type === 'location' && e.first <= ch).map(([id]) => id);
    const { seat, control } = placeLinks(ix, ch);
    const members = new Map<string, string[]>();
    for (const [org, place] of seat) members.set(place, [...(members.get(place) ?? []), org]);
    const tree = nest(ix, ch, places, parents(ix, ch, 'location'), members, new Map(), '世界', '');
    const where = whereabouts(ix, ch);
    const pins = new Map<string, { id: string; label: string }[]>();
    for (const [who, w] of where) {
      if (ix.entity(who)?.type !== 'character') continue;
      pins.set(w.place, [...(pins.get(w.place) ?? []), { id: who, label: ix.name(who, ch) }]);
    }
    const here = new Set((ix.chapters.get(ch)?.events ?? []).map((e) => ix.m.events[e]?.where).filter(Boolean) as string[]);
    return { tree, control, pins, here, count: places.length, located: where.size };
  }, [ix, ch]);

  if (!data.count) return <Empty>截至第 {ch} 章还没有出现地点。</Empty>;
  const herePlaces = [...data.here];
  return (
    <div class="cols wide-left">
      <div class="col-main">
        <Panel title={`截至第${ch}章的地点`} count={data.count} id="map-pack"
          extra={<span class="muted"><i class="legend hot" />本章发生地 <i class="legend pin" />人物所在 · 底色 = 控制势力</span>}>
          <PackChart root={data.tree} highlight={data.here} pins={data.pins} onPick={(id) => go('people', id)}
            tint={(id, n) => (n.kind === 'member' ? '#8a4fc7' : id && data.control.get(id) ? hue(data.control.get(id)!) : undefined)} />
        </Panel>
      </div>
      <div class="col-side">
        <Panel title="本章发生地" count={herePlaces.length} id="map-here">
          {herePlaces.length ? <Ents ids={herePlaces} /> : <Empty>本章事件没有记录地点。</Empty>}
        </Panel>
        <Panel title="人物所在" count={[...data.pins.values()].reduce((a, b) => a + b.length, 0)} id="map-who">
          {data.pins.size ? (
            <ul class="changes">{[...data.pins.entries()].map(([place, who]) => (
              <li><Ent id={place} />：<Ents ids={who.map((w) => w.id)} /></li>
            ))}</ul>
          ) : <Empty>没有近 5 章内可确认的人物位置。</Empty>}
        </Panel>
        {data.control.size > 0 && (
          <Panel title="领地" count={data.control.size} id="map-control">
            <ul class="changes">{[...data.control.entries()].map(([place, org]) => <li><Ent id={place} /> 受控于 <Ent id={org} /></li>)}</ul>
          </Panel>
        )}
      </div>
    </div>
  );
}

function Levels() {
  const { ix, ch } = useApp();
  const axes = Object.entries(ix.m.levels);
  if (!axes.length) return <Empty>没有等级体系记录。</Empty>;
  return (
    <div class="ladders">
      {axes.map(([axis, ladder]) => {
        const holders = new Map<string, string[]>();
        for (const f of ix.m.facts) {
          if (f.facet === 'level' && f.target === axis && holds(f.from, f.to, ch) && ix.visible(f.e, ch)) holders.set(f.value, [...(holders.get(f.value) ?? []), f.e]);
        }
        const rungs = ladder.rungs.filter((r) => r.from <= ch);
        if (!rungs.length) return null;
        return (
          <Panel title={ix.visible(axis, ch) ? ix.name(axis, ch) : '等级'} count={rungs.length} id={`ladder-${axis}`}>
            <ol class="ladder">
              {rungs.slice().reverse().map((r) => (
                <li class={holders.has(r.label) ? 'held' : ''}>
                  <span class="rung">{r.label}</span><span class="muted rung-from">第{r.from}章首见</span>
                  <Ents ids={holders.get(r.label)} max={20} />
                </li>
              ))}
            </ol>
          </Panel>
        );
      })}
    </div>
  );
}

function Catalog() {
  const { ix, ch, go } = useApp();
  const holders = new Map<string, string[]>();
  for (const r of ix.m.relations) {
    if (r.group !== 'possession' || !holds(r.from, r.to, ch) || !ix.visible(r.s, ch)) continue;
    holders.set(r.t, [...(holders.get(r.t) ?? []), r.s]);
  }
  const groups = new Map<string, string[]>();
  for (const [id, e] of Object.entries(ix.m.entities)) {
    if ((e.type !== 'item' && e.type !== 'skill') || e.first > ch) continue;
    const cats = e.categories?.length ? e.categories : [e.type === 'skill' ? '__skill' : 'unresolved'];
    for (const c of cats) groups.set(c, [...(groups.get(c) ?? []), id]);
  }
  if (!groups.size) return <Empty>截至第 {ch} 章没有物品或功法。</Empty>;
  return (
    <div class="catalog">
      {[...groups.entries()].sort((a, b) => b[1].length - a[1].length).map(([cat, ids]) => (
        <Panel title={cat === '__skill' ? '功法技能' : ix.label('item_categories', cat)} count={ids.length} id={`cat-${cat}`}>
          <div class="cards">
            {ids.map((id) => (
              <button class={`card ${ix.entity(id)!.type === 'skill' ? 't-skill' : 't-item'}`} onClick={() => go('people', id)}>
                <span class="card-name">{ix.name(id, ch)}</span>
                {holders.get(id) && <span class="card-meta">持有：{holders.get(id)!.slice(0, 3).map((h) => ix.name(h, ch)).join('、')}</span>}
                <span class="card-meta">第{ix.entity(id)!.first}章登场</span>
              </button>
            ))}
          </div>
        </Panel>
      ))}
    </div>
  );
}
