import { ComponentChildren } from 'preact';
import { useApp } from '../app';
import { stepAt } from '../model';
import { ChLink, Empty, Ent, Ents, Evidence, Tabs } from '../components/common';

type Tab = 'clues' | 'promises' | 'routes' | 'acts';

/** Tracking boards: every thread in the column of its status as of the current chapter. */
export function ThreadsView({ tab }: { tab?: string }) {
  const { ix, ch, go } = useApp();
  const t = ix.m.threads;
  const current = (['clues', 'promises', 'routes', 'acts'].includes(tab ?? '') ? tab : 'clues') as Tab;
  const n = (rows: { from?: number; ch?: number }[]) => rows.filter((r) => (r.from ?? r.ch ?? Infinity) <= ch).length;
  return (
    <div class="threads">
      <Tabs tabs={[['clues', '伏笔', n(t.clues)], ['promises', '承诺', n(t.promises)], ['routes', '感情线', n(t.routes)], ['acts', '亲密行为', n(t.acts)]]}
        value={current} onChange={(v) => go('threads', v)} />
      {current === 'clues' && <Clues />}
      {current === 'promises' && <Promises />}
      {current === 'routes' && <Routes />}
      {current === 'acts' && <Acts />}
    </div>
  );
}

function Board({ columns }: { columns: [string, string, ComponentChildren[]][] }) {
  const used = columns.filter(([, , cards]) => cards.length);
  if (!used.length) return <Empty>截至本章没有记录。</Empty>;
  return (
    <div class="board">
      {used.map(([key, label, cards]) => (
        <section class={`board-col s-${key}`}><h3>{label}<span class="count">{cards.length}</span></h3>{cards}</section>
      ))}
    </div>
  );
}

function group<T>(rows: T[], key: (r: T) => string | undefined): Map<string, T[]> {
  const out = new Map<string, T[]>();
  for (const r of rows) { const k = key(r) ?? 'uncertain'; out.set(k, [...(out.get(k) ?? []), r]); }
  return out;
}

function Clues() {
  const { ix, ch } = useApp();
  const rows = ix.m.threads.clues.filter((x) => x.from <= ch);
  const by = group(rows, (x) => stepAt(x.status, ch)?.[1]);
  const order = ['open', 'progressed', 'partially_resolved', 'resolved', 'false_lead'];
  return <Board columns={order.map((k) => [k, ix.label('foreshadow_statuses', k), (by.get(k) ?? []).map((x) => (
    <article class="tcard">
      <b>{x.label}</b>
      <div class="muted">埋于 <ChLink n={x.from} />{x.payoffAt != null && x.payoffAt <= ch && <>· 回收于 <ChLink n={x.payoffAt} /></>}</div>
      {x.obs && <p>{x.obs}</p>}
      {(x.steps ?? []).filter((s) => s[0] <= ch).map((s) => <div class="step"><ChLink n={s[0]} />{ix.label('progression_kinds', s[1])}：{s[2]}</div>)}
      <Ents ids={x.who} /><Evidence ids={x.ev} />
    </article>
  ))])} />;
}

function Promises() {
  const { ix, ch } = useApp();
  const rows = ix.m.threads.promises.filter((x) => x.from <= ch);
  const by = group(rows, (x) => stepAt(x.status, ch)?.[1]);
  const order = ['active', 'partially_fulfilled', 'fulfilled', 'broken', 'expired', 'waived', 'uncertain'];
  return <Board columns={order.map((k) => [k, ix.label('commitment_statuses', k), (by.get(k) ?? []).map((x) => (
    <article class="tcard">
      <div><Ents ids={x.by} />{x.to?.length ? <> → <Ents ids={x.to} /></> : null}</div>
      <p>{x.terms}</p>
      <div class="muted">立于 <ChLink n={x.from} />{x.deadline != null && ` · 期限第${x.deadline}章`}{x.resolvedAt != null && x.resolvedAt <= ch && <> · 了结于 <ChLink n={x.resolvedAt} /></>}</div>
      {x.resolvedAt != null && x.resolvedAt <= ch && x.resolution && <p class="muted">{x.resolution}</p>}
      <Evidence ids={x.ev} />
    </article>
  ))])} />;
}

function Routes() {
  const { ix, ch } = useApp();
  const rows = ix.m.threads.routes.filter((x) => x.from <= ch && ix.visible(x.who, ch));
  const by = group(rows, (x) => stepAt(x.status, ch)?.[1]);
  const order = ['uncertain', 'ambiguous', 'mutual_interest', 'provisional_intimate', 'confirmed_relationship', 'betrothed', 'spouse', 'one_sided',
    'accidental_or_contextual', 'coerced_or_forced', 'ended', 'excluded_nonromantic'];
  const milestone = (label: string, n?: number) => (n != null && n <= ch ? <span class="ms">{label} <ChLink n={n} /></span> : null);
  return <Board columns={order.map((k) => [k, ix.label('romance_statuses', k), (by.get(k) ?? []).map((x) => (
    <article class="tcard">
      <b><Ent id={x.who} /></b>{x.pro && <span class="muted"> 与 <Ent id={x.pro} /></span>}
      <div class="milestones">{milestone('相识', x.met)}{milestone('暧昧', x.ambiguous)}{milestone('确认', x.confirmed)}{milestone('初次', x.firstSex)}</div>
      {(x.steps ?? []).filter((s) => s[0] <= ch).slice(-3).map((s) => <div class="step"><ChLink n={s[0]} />{s[2]}</div>)}
    </article>
  ))])} />;
}

function Acts() {
  const { ix, ch } = useApp();
  const rows = ix.m.threads.acts.filter((x) => x.ch <= ch);
  if (!rows.length) return <Empty>截至本章没有亲密行为记录。</Empty>;
  const pairs = group(rows, (x) => [...(x.by ?? []), ...(x.to ?? [])].sort().join('|'));
  return (
    <div class="acts">
      {[...pairs.entries()].sort((a, b) => b[1].length - a[1].length).map(([, list]) => (
        <section class="panel">
          <h3><Ents ids={[...new Set([...(list[0].by ?? []), ...(list[0].to ?? [])])]} /><span class="count">{list.length}</span></h3>
          <ul class="timeline">
            {list.slice().reverse().map((x) => (
              <li><ChLink n={x.ch} /><span class="tag intimate">{ix.label('intimacy_act_types', x.type)}</span>
                {x.consent && <span class="muted">（{ix.label('consent_contexts', x.consent)}）</span>} {x.desc}<Evidence ids={x.ev} /></li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
