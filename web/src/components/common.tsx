import { ComponentChildren } from 'preact';
import { useState } from 'preact/hooks';
import { useApp } from '../app';

export const TYPE_CLASS: Record<string, string> = {
  character: 't-char', organization: 't-org', location: 't-loc', item: 't-item', skill: 't-skill',
  concept: 't-concept', creature: 't-creature', level_axis: 't-axis', title: 't-concept',
};

/** An entity's name as of the slider chapter; clicking opens its page. */
export function Ent({ id, plain }: { id: string; plain?: boolean }) {
  const { ix, ch, go } = useApp();
  const e = ix.entity(id);
  if (!e) return null;
  const name = ix.name(id, ch);
  if (plain) return <span>{name}</span>;
  return (
    <a class={`ent ${TYPE_CLASS[e.type] ?? ''}`} data-entity={id} onClick={(ev) => { ev.preventDefault(); go('people', id); }} href="#">
      {name}
    </a>
  );
}

export function Ents({ ids, max = 12 }: { ids?: string[]; max?: number }) {
  const { ix, ch } = useApp();
  const shown = (ids ?? []).filter((id) => ix.visible(id, ch));
  if (!shown.length) return null;
  return (
    <span class="ents">
      {shown.slice(0, max).map((id) => <Ent id={id} />)}
      {shown.length > max && <span class="muted">等 {shown.length} 个</span>}
    </span>
  );
}

/** "第 N 章起" – every dynamic value says since when it holds. */
export function Since({ from, to }: { from: number; to?: number | null }) {
  const { ch } = useApp();
  return (
    <span class={`since${from === ch ? ' fresh' : ''}`} title={to != null ? `有效至第 ${to} 章` : undefined}>
      {from === ch ? '本章' : `第${from}章起`}
    </span>
  );
}

/** A chapter link that moves the slider. */
export function ChLink({ n, children }: { n: number; children?: ComponentChildren }) {
  const { setCh } = useApp();
  return <a class="chlink" href="#" onClick={(e) => { e.preventDefault(); setCh(n); }}>{children ?? `第${n}章`}</a>;
}

/** Evidence: a small toggle that reveals the quotations a value rests on. */
export function Evidence({ ids }: { ids?: string[] }) {
  const { ix } = useApp();
  const [open, setOpen] = useState(false);
  const rows = (ids ?? []).map((id) => ix.m.evidence[id]).filter(Boolean);
  if (!rows.length) return null;
  return (
    <span class="evidence">
      <button class="ev-btn" onClick={() => setOpen(!open)} title="原文依据">原文{rows.length > 1 ? ` ${rows.length}` : ''}</button>
      {open && (
        <span class="ev-pop">
          {rows.map(([n, quote]) => <q><ChLink n={n} />{quote}</q>)}
        </span>
      )}
    </span>
  );
}

export function Panel({ title, count, children, extra, id }: { title: string; count?: number; children: ComponentChildren; extra?: ComponentChildren; id?: string }) {
  return (
    <section class="panel" data-panel={id}>
      <h3>{title}{count != null && <span class="count">{count}</span>}{extra && <span class="panel-extra">{extra}</span>}</h3>
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ComponentChildren }) {
  return <p class="empty">{children}</p>;
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: [T, string, number?][]; value: T; onChange: (v: T) => void }) {
  return (
    <div class="tabs" role="tablist">
      {tabs.map(([key, label, n]) => (
        <button role="tab" class={key === value ? 'on' : ''} onClick={() => onChange(key)}>
          {label}{n != null && <span class="count">{n}</span>}
        </button>
      ))}
    </div>
  );
}
