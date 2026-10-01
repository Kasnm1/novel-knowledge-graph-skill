import { useApp } from '../app';
import { Arc } from '../model';
import { ChLink, Empty, Ents, Panel } from '../components/common';

/** Story arcs up to the current chapter; books without editorial arcs fall back to fixed segments. */
export function StoryView({ arcId }: { arcId?: string }) {
  const { ix, ch } = useApp();
  const editorial = ix.m.arcs.length > 0;
  const arcs: Arc[] = editorial ? ix.m.arcs : segments(ix.chapterList);
  const arc = arcId ? arcs.find((a) => a.id === arcId) : undefined;
  if (arc) return arc.from <= ch ? <ArcPage arc={arc} editorial={editorial} /> : <Empty>这个篇章从第 {arc.from} 章开始。</Empty>;
  const shown = arcs.filter((a) => a.from <= ch);
  const first = ix.chapterList[0] ?? 0, span = Math.max(1, ch - first + 1);
  const roots = shown.filter((a) => !a.parent);
  return (
    <div class="story">
      {!editorial && <p class="muted note">这本书还没有编辑层的故事弧，下面按固定章数分段；做完编辑层后会换成真正的卷 / 篇 / 篇章。</p>}
      <Panel title={`截至第${ch}章的篇章`} count={shown.length} id="arcs">
        <div class="lanes">
          {roots.map((a) => <Lane arc={a} all={shown} first={first} span={span} depth={0} />)}
        </div>
      </Panel>
    </div>
  );
}

function Lane({ arc, all, first, span, depth }: { arc: Arc; all: Arc[]; first: number; span: number; depth: number }) {
  const { ix, ch, go } = useApp();
  const end = Math.min(arc.to ?? ch, ch);
  const left = ((arc.from - first) / span) * 100, width = Math.max(1.5, ((end - arc.from + 1) / span) * 100);
  const kids = all.filter((a) => a.parent === arc.id);
  const now = arc.from <= ch && (arc.to == null || ch <= arc.to);
  return (
    <>
      <div class={`lane${now ? ' now' : ''}`} style={{ paddingLeft: `${depth * 16}px` }}>
        <button class="lane-title" onClick={() => go('story', arc.id)}>{arc.title}</button>
        <div class="lane-track">
          <div class="lane-bar" style={{ left: `${left}%`, width: `${width}%` }} title={`第${arc.from}–${arc.to ?? '…'}章`} />
        </div>
        <span class="muted lane-range">第{arc.from}–{arc.to != null && arc.to <= ch ? arc.to : '…'}章{arc.phase ? ` · ${ix.label('story_arc_phases', arc.phase)}` : ''}</span>
      </div>
      {kids.map((k) => <Lane arc={k} all={all} first={first} span={span} depth={depth + 1} />)}
    </>
  );
}

function ArcPage({ arc, editorial }: { arc: Arc; editorial: boolean }) {
  const { ix, ch, go } = useApp();
  const chapters = ix.m.chapters.filter((c) => c.n >= arc.from && c.n <= Math.min(arc.to ?? ch, ch));
  const counts = new Map<string, number>();
  for (const c of chapters) for (const r of c.cast ?? []) if (r.mode !== 'mentioned') counts.set(r.id, (counts.get(r.id) ?? 0) + 1);
  const cast = arc.cast?.length ? arc.cast : [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 20).map(([id]) => id);
  const turns = (arc.turns ?? []).map((id) => ix.m.events[id]).filter((e) => e && e.ch <= ch);
  const ended = arc.to != null && arc.to <= ch;
  return (
    <div class="arc-page">
      <button class="link back" onClick={() => go('story')}>‹ 全部篇章</button>
      <h2>{arc.title}</h2>
      <p class="muted">第{arc.from}–{ended ? arc.to : '…'}章{!ended && arc.to != null ? '（进行中）' : ''}{editorial ? '' : ' · 固定分段'}</p>
      {ended && arc.recap && <Panel title="篇章回顾" id="recap"><p class="summary">{arc.recap}</p></Panel>}
      {!ended && arc.recap && <p class="muted note">篇章回顾写的是整个篇章，读完第 {arc.to} 章后显示。</p>}
      <div class="cols">
        <div class="col-main">
          <Panel title="章节" count={chapters.length} id="arc-chapters">
            <ul class="timeline">
              {chapters.slice().reverse().map((c) => <li><ChLink n={c.n} /><b>{c.title}</b>{c.summary && <span class="muted"> — {c.summary.slice(0, 90)}{c.summary.length > 90 ? '…' : ''}</span>}</li>)}
            </ul>
          </Panel>
        </div>
        <div class="col-side">
          <Panel title="主要人物" count={cast.length} id="arc-cast"><Ents ids={cast} max={30} /></Panel>
          {turns.length > 0 && <Panel title="转折点" id="arc-turns"><ul class="timeline">{turns.map((e) => <li><ChLink n={e!.ch} />{e!.title}</li>)}</ul></Panel>}
        </div>
      </div>
    </div>
  );
}

function segments(list: number[]): Arc[] {
  if (!list.length) return [];
  const size = list.length > 400 ? 50 : list.length > 100 ? 20 : 10;
  const out: Arc[] = [];
  for (let i = 0; i < list.length; i += size) {
    const from = list[i], to = list[Math.min(list.length, i + size) - 1];
    out.push({ id: `seg-${from}`, title: `第${from}–${to}章`, from, to });
  }
  return out;
}
