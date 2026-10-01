import { useEffect, useMemo, useRef } from 'preact/hooks';
import { useApp } from '../app';

const ARC_COLORS = ['#c7d7f2', '#f2d9c7', '#cfe8d2', '#ead0ea', '#f1e6b8', '#cde6ea', '#e9cfcf', '#dcd6f0'];
const GRADE_COLORS: Record<string, string> = { good: '#4c9a6a', review: '#d9a441', reaudit: '#c8553d' };

/**
 * The one global control: a chapter slider drawn over three bands —
 * story arcs, event density and per-chapter audit quality.
 */
export function ChapterAxis() {
  const { ix, ch, setCh } = useApp();
  const canvas = useRef<HTMLCanvasElement>(null);
  const list = ix.chapterList;
  const pos = Math.max(0, list.indexOf(ch));
  const maxDensity = useMemo(() => Math.max(1, ...ix.m.chapters.map((c) => c.density ?? 0)), [ix]);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const draw = () => {
      const w = el.clientWidth, h = el.clientHeight, dpr = devicePixelRatio || 1;
      el.width = w * dpr; el.height = h * dpr;
      const g = el.getContext('2d')!;
      g.scale(dpr, dpr);
      g.clearRect(0, 0, w, h);
      const n = list.length || 1, x = (i: number) => (i / n) * w, bw = Math.max(1, w / n);
      // top-level arcs band
      const top = ix.m.arcs.filter((a) => !a.parent);
      top.forEach((a, k) => {
        const i0 = list.findIndex((c) => c >= a.from);
        let i1 = a.to == null ? n - 1 : list.findIndex((c) => c > a.to!) - 1;
        if (i1 < 0) i1 = n - 1;
        if (i0 < 0) return;
        g.fillStyle = ARC_COLORS[k % ARC_COLORS.length];
        g.fillRect(x(i0), 0, x(i1 + 1) - x(i0), 6);
      });
      // density
      g.fillStyle = '#9aa7b8';
      ix.m.chapters.forEach((c, i) => {
        const d = (c.density ?? 0) / maxDensity;
        if (d > 0) g.fillRect(x(i), h - 4 - d * (h - 14), bw, d * (h - 14));
      });
      // audit quality
      ix.m.chapters.forEach((c, i) => {
        const grade = c.quality?.grade;
        g.fillStyle = grade ? GRADE_COLORS[grade] ?? '#ccc' : c.audit ? '#a8c5e0' : '#e4e7ec';
        g.fillRect(x(i), h - 3, bw, 3);
      });
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ix, list, maxDensity]);

  const chapter = ix.chapters.get(ch);
  const arcs = (chapter?.arcs ?? []).map((id) => ix.arcs.get(id)?.title).filter(Boolean);
  const step = (d: number) => setCh(list[Math.min(list.length - 1, Math.max(0, pos + d))]);

  return (
    <div class="axis">
      <button class="axis-step" onClick={() => step(-1)} disabled={pos === 0} aria-label="上一章">‹</button>
      <div class="axis-track">
        <canvas ref={canvas} class="axis-canvas" />
        <input
          type="range" min={0} max={Math.max(0, list.length - 1)} value={pos} class="axis-range" aria-label="章节"
          onInput={(e) => setCh(list[Number((e.target as HTMLInputElement).value)])}
        />
      </div>
      <button class="axis-step" onClick={() => step(1)} disabled={pos >= list.length - 1} aria-label="下一章">›</button>
      <label class="axis-num">
        第<input type="number" value={ch} min={list[0]} max={list[list.length - 1]}
          onChange={(e) => {
            const want = Number((e.target as HTMLInputElement).value);
            const near = list.reduce((a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a), list[0]);
            setCh(near);
          }} />章
      </label>
      <span class="axis-arc" title={arcs.join(' / ')}>{arcs[arcs.length - 1] ?? ''}</span>
    </div>
  );
}
