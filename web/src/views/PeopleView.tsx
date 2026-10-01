import { useMemo, useState } from 'preact/hooks';
import { useApp } from '../app';
import { datedUpTo, Fact, holds, stepAt } from '../model';
import { ChLink, Empty, Ent, Ents, Evidence, Panel, Since, Tabs, TYPE_CLASS } from '../components/common';

const TYPE_TABS: [string, string][] = [
  ['character', '人物'], ['organization', '势力'], ['location', '地点'], ['item', '物品'], ['skill', '功法技能'], ['other', '其他'],
];
const TIER_ORDER = ['protagonist', 'core', 'major', 'minor', 'background'];

export function PeopleView({ entityId }: { entityId?: string }) {
  const { ix, ch } = useApp();
  if (entityId && ix.entity(entityId)) {
    return ix.visible(entityId, ch) ? <Profile id={entityId} /> : (
      <div class="profile"><Empty>这个条目在第 {ix.entity(entityId)!.first} 章才出现。把章节轴拖到那之后再看。</Empty></div>
    );
  }
  return <Roster />;
}

function lastSeen(ids: string[] | undefined, events: Record<string, { ch: number }>, ch: number): number | undefined {
  let last: number | undefined;
  for (const id of ids ?? []) { const c = events[id]?.ch; if (c != null && c <= ch) last = c; }
  return last;
}

function Roster() {
  const { ix, ch, go } = useApp();
  const [type, setType] = useState('character');
  const [q, setQ] = useState('');
  const [showBackground, setShowBackground] = useState(false);
  const known = new Set(TYPE_TABS.map(([t]) => t));

  const visible = useMemo(() => Object.entries(ix.m.entities).filter(([, e]) => e.first <= ch), [ix, ch]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const [, e] of visible) { const k = known.has(e.type) ? e.type : 'other'; c[k] = (c[k] ?? 0) + 1; }
    return c;
  }, [visible]);
  const rows = visible
    .filter(([, e]) => (known.has(e.type) ? e.type : 'other') === type)
    .filter(([id, e]) => !q || ix.name(id, ch).includes(q) || datedUpTo(e.aliases, ch).some((a) => a[1].includes(q)));
  const byTier = new Map<string, typeof rows>();
  for (const row of rows) {
    const tier = type === 'character' ? row[1].tier : 'all';
    byTier.set(tier, [...(byTier.get(tier) ?? []), row]);
  }
  const tiers = type === 'character' ? TIER_ORDER : ['all'];

  return (
    <div class="roster">
      <div class="roster-bar">
        <Tabs tabs={TYPE_TABS.map(([k, l]) => [k, l, counts[k] ?? 0])} value={type} onChange={setType} />
        <input class="filter" placeholder="筛选名字或别称" value={q} onInput={(e) => setQ((e.target as HTMLInputElement).value)} />
      </div>
      {tiers.map((tier) => {
        const list = (byTier.get(tier) ?? []).sort((a, b) => (b[1].events ?? 0) - (a[1].events ?? 0));
        if (!list.length) return null;
        const collapsed = tier === 'background' && !showBackground && !q;
        return (
          <Panel title={tier === 'all' ? `截至第${ch}章` : ix.label('tiers', tier)} count={list.length} id={`tier-${tier}`}
            extra={tier === 'background' ? <button class="link" onClick={() => setShowBackground(!showBackground)}>{collapsed ? '展开' : '收起'}</button> : undefined}>
            {!collapsed && (
              <div class={`cards ${tier === 'protagonist' || tier === 'core' ? 'big' : ''}`}>
                {list.slice(0, 400).map(([id, e]) => {
                  const seen = lastSeen(ix.eventsByEntity.get(id), ix.m.events, ch);
                  const headline = (e.headlines ?? []).find((h) => holds(h[0], h[1], ch))?.[2];
                  const top = ix.factsAt(id, ch).filter((f) => f.facet === 'level' || f.facet === 'identity' || f.facet === 'affiliation').slice(0, 2);
                  return (
                    <button class={`card ${TYPE_CLASS[e.type] ?? ''}`} data-entity={id} onClick={() => go('people', id)}>
                      <span class="card-name">{ix.name(id, ch)}</span>
                      {headline && <span class="card-line">{headline}</span>}
                      {top.map((f) => <span class="card-fact">{f.value}</span>)}
                      <span class="card-meta">第{e.first}章登场{seen != null && seen !== e.first ? ` · 最近第${seen}章` : ''}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </Panel>
        );
      })}
      {!rows.length && <Empty>截至第 {ch} 章没有符合条件的条目。</Empty>}
    </div>
  );
}

function Profile({ id }: { id: string }) {
  const { ix, ch, go } = useApp();
  const e = ix.entity(id)!;
  const [allEvents, setAllEvents] = useState(false);
  const facts = ix.factsAt(id, ch);
  const history = (ix.factsByEntity.get(id) ?? []).filter((f) => f.from <= ch);
  const aliases = datedUpTo(e.aliases, ch);
  const summary = datedUpTo(e.summary, ch).pop();
  const attrs = (e.attrs ?? []).filter((a) => a[0] <= ch);
  const headline = (e.headlines ?? []).find((h) => holds(h[0], h[1], ch))?.[2];
  const relations = ix.relationsAt(id, ch);
  const events = (ix.eventsByEntity.get(id) ?? []).map((eid) => [eid, ix.m.events[eid]] as const).filter(([, ev]) => ev && ev.ch <= ch).reverse();
  const seen = events[0]?.[1].ch;
  const t = ix.m.threads;
  const clues = t.clues.filter((x) => x.from <= ch && x.who?.includes(id));
  const promises = t.promises.filter((x) => x.from <= ch && (x.by?.includes(id) || x.to?.includes(id)));
  const routes = t.routes.filter((x) => x.from <= ch && (x.who === id || x.pro === id));
  const groups = new Map<string, typeof relations>();
  for (const r of relations) groups.set(r.group, [...(groups.get(r.group) ?? []), r]);
  const byFacet = new Map<string, Fact[]>();
  for (const f of facts) byFacet.set(f.facet, [...(byFacet.get(f.facet) ?? []), f]);
  const arcBios = Object.entries(e.bios ?? {}).filter(([arc]) => (ix.arcs.get(arc)?.from ?? Infinity) <= ch);

  return (
    <div class="profile" data-entity={id}>
      <div class="profile-head">
        <button class="link back" onClick={() => go('people')}>‹ 名册</button>
        <h2 class={TYPE_CLASS[e.type]}>{ix.name(id, ch)}</h2>
        <div class="chips">
          <span class="chip">{ix.label('entity_types', e.type)}</span>
          {e.type === 'character' && <span class={`chip tier-${e.tier}`} title={e.tierSource === 'derived' ? '按出场事件数推算' : '编辑层判定'}>{ix.label('tiers', e.tier)}</span>}
          <span class="chip">第<ChLink n={e.first}>{e.first}</ChLink>章登场</span>
          {seen != null && <span class="chip">最近出场 第<ChLink n={seen}>{seen}</ChLink>章</span>}
          {(e.categories ?? []).map((c) => <span class="chip">{ix.label('item_categories', c)}</span>)}
        </div>
        {aliases.length > 0 && <div class="aliases">又称：{aliases.map((a) => <span title={`第${a[0]}章起`}>{a[1]}</span>)}</div>}
        {headline && <p class="headline">{headline}</p>}
        <button class="link" onClick={() => go('relations', id)}>在关系图中查看 ›</button>
      </div>

      <div class="cols">
        <div class="col-main">
          <Panel title={`截至第${ch}章的状态`} count={facts.length} id="state">
            {facts.length ? (
              <table class="state">
                <tbody>
                  {[...byFacet.entries()].map(([facet, rows]) => rows.map((f, k) => (
                    <tr class={f.from === ch ? 'fresh' : ''}>
                      <th>{k === 0 ? ix.label('facets', facet) : ''}</th>
                      <td>{f.target && f.facet !== 'possession' && <span class="target"><Ent id={f.target} plain />：</span>}{f.value}<Evidence ids={f.ev} /></td>
                      <td class="since-cell"><Since from={f.from} to={f.to} /></td>
                    </tr>
                  )))}
                </tbody>
              </table>
            ) : <Empty>没有当前有效的状态记录。会过期的状态（位置、情绪、伤势）超过时效后不再显示。</Empty>}
            {history.length > facts.length && (
              <details class="history">
                <summary>状态变化史（{history.length}）</summary>
                <ul>{history.slice().reverse().map((f) => <li><ChLink n={f.from} /> {ix.label('facets', f.facet)} → {f.value}{f.reason && <span class="muted"> — {f.reason}</span>}</li>)}</ul>
              </details>
            )}
          </Panel>

          {(summary || attrs.length > 0 || arcBios.length > 0) && (
            <Panel title="档案" id="dossier">
              {summary && <p class="summary">{summary[1]}{summary[0] === ix.m.meta.last && <span class="muted">（全书终局描述）</span>}</p>}
              {arcBios.map(([arc, bio]) => <p><b>{ix.arcs.get(arc)?.title}：</b>{bio}</p>)}
              {attrs.length > 0 && <dl class="attrs">{attrs.map(([from, k, v]) => <><dt>{k}</dt><dd>{v}<Since from={from} /></dd></>)}</dl>}
            </Panel>
          )}
          {!summary && e.summary?.length ? <p class="muted note">这个条目的简介是全书终局描述，读到第 {e.summary[0][0]} 章才显示。</p> : null}

          <Panel title="经历" count={events.length} id="timeline">
            {events.length ? (
              <ul class="timeline">
                {(allEvents ? events : events.slice(0, 25)).map(([, ev]) => (
                  <li><ChLink n={ev.ch} /><b>{ev.title}</b>{ev.desc && <span class="muted"> — {ev.desc.slice(0, 80)}{ev.desc.length > 80 ? '…' : ''}</span>}</li>
                ))}
              </ul>
            ) : <Empty>截至本章没有参与的情节。</Empty>}
            {events.length > 25 && <button class="link" onClick={() => setAllEvents(!allEvents)}>{allEvents ? '收起' : `显示全部 ${events.length} 条`}</button>}
          </Panel>
        </div>

        <div class="col-side">
          <Panel title="关系" count={relations.length} id="relations">
            {relations.length ? [...groups.entries()].map(([group, rows]) => (
              <div class="rel-group">
                <h4 class={`g-${group}`}>{ix.label('relation_groups', group)}</h4>
                <ul>
                  {rows.map((r) => {
                    const other = r.s === id ? r.t : r.s;
                    const stance = stepAt(r.stance, ch)?.[1];
                    const note = datedUpTo(r.notes, ch).pop()?.[1];
                    return (
                      <li title={note}>
                        <Ent id={other} /> <span class="rel-type">{r.s === id ? ix.label('relations', r.type) : `← ${ix.label('relations', r.type)}`}</span>
                        {stance && <span class={`stance s-${stance}`}>{ix.label('stances', stance)}</span>}
                        <Since from={r.from} to={r.to} />
                      </li>
                    );
                  })}
                </ul>
              </div>
            )) : <Empty>截至本章没有有效关系。</Empty>}
          </Panel>

          {(routes.length + clues.length + promises.length) > 0 && (
            <Panel title="相关线索" id="threads">
              <ul class="thread-list">
                {routes.map((x) => <li><span class="tag romance">感情线</span><Ent id={x.who === id ? (x.pro ?? x.who) : x.who} />：{ix.label('romance_statuses', stepAt(x.status, ch)?.[1])}</li>)}
                {promises.map((x) => <li><span class="tag promise">{ix.label('commitment_statuses', stepAt(x.status, ch)?.[1]) || '承诺'}</span>{x.terms}</li>)}
                {clues.map((x) => <li><span class="tag clue">{ix.label('foreshadow_statuses', stepAt(x.status, ch)?.[1])}</span>{x.label}</li>)}
              </ul>
            </Panel>
          )}
          {e.type === 'organization' && <Members id={id} />}
        </div>
      </div>
    </div>
  );
}

function Members({ id }: { id: string }) {
  const { ix, ch } = useApp();
  const members = ix.relationsAt(id, ch).filter((r) => r.t === id && r.group === 'affiliation').map((r) => r.s);
  if (!members.length) return null;
  return <Panel title="成员" count={members.length} id="members"><Ents ids={members} max={80} /></Panel>;
}
