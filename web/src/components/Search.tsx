import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { useApp } from '../app';
import { datedUpTo } from '../model';

interface Hit { kind: string; label: string; sub: string; run: () => void }

/** Ctrl+K: names and aliases known by the current chapter, chapters, and events up to it. */
export function Search({ onClose }: { onClose: () => void }) {
  const { ix, ch, go, setCh } = useApp();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus(), []);

  const hits = useMemo<Hit[]>(() => {
    const term = q.trim();
    if (!term) return [];
    const out: Hit[] = [];
    const num = Number(term.replace(/[第章]/g, ''));
    if (Number.isInteger(num) && ix.chapters.has(num)) {
      out.push({ kind: '章节', label: `第${num}章 ${ix.chapters.get(num)?.title ?? ''}`, sub: '跳到这一章', run: () => { setCh(num); go('chapter'); } });
    }
    for (const [id, e] of Object.entries(ix.m.entities)) {
      if (e.first > ch) continue;
      const labels = [ix.name(id, ch), ...datedUpTo(e.aliases, ch).map((a) => a[1])];
      const match = labels.find((l) => l.includes(term));
      if (match) out.push({ kind: ix.label('entity_types', e.type), label: ix.name(id, ch), sub: match !== labels[0] ? `又称 ${match}` : `第${e.first}章登场`, run: () => go('people', id) });
      if (out.length > 60) break;
    }
    for (const c of ix.m.chapters) {
      if (c.n > ch || out.length > 80) continue;
      if (c.title?.includes(term)) out.push({ kind: '章节', label: `第${c.n}章 ${c.title}`, sub: c.summary?.slice(0, 40) ?? '', run: () => { setCh(c.n); go('chapter'); } });
    }
    for (const [, ev] of Object.entries(ix.m.events)) {
      if (ev.ch > ch || out.length > 100) continue;
      if (ev.title?.includes(term)) out.push({ kind: '事件', label: ev.title, sub: `第${ev.ch}章`, run: () => { setCh(ev.ch); go('chapter'); } });
    }
    return out;
  }, [q, ix, ch, go, setCh]);

  const pick = (h?: Hit) => { if (h) { h.run(); onClose(); } };
  return (
    <div class="modal" onClick={onClose}>
      <div class="search" onClick={(e) => e.stopPropagation()}>
        <input ref={input} value={q} placeholder={`搜索人物、地点、物品、章节、事件（截至第${ch}章）`}
          onInput={(e) => { setQ((e.target as HTMLInputElement).value); setSel(0); }}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onClose();
            if (e.key === 'ArrowDown') { e.preventDefault(); setSel(Math.min(hits.length - 1, sel + 1)); }
            if (e.key === 'ArrowUp') { e.preventDefault(); setSel(Math.max(0, sel - 1)); }
            if (e.key === 'Enter') pick(hits[sel]);
          }} />
        <ul class="hits">
          {hits.slice(0, 40).map((h, i) => (
            <li class={i === sel ? 'on' : ''} onMouseEnter={() => setSel(i)} onClick={() => pick(h)}>
              <span class="kind">{h.kind}</span><span class="label">{h.label}</span><span class="sub">{h.sub}</span>
            </li>
          ))}
          {q && !hits.length && <li class="none">截至第{ch}章没有匹配项</li>}
        </ul>
      </div>
    </div>
  );
}
