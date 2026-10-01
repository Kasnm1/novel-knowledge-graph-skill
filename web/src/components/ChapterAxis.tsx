import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { useApp } from '../app';
import { Icon } from './Icon';

const ARC_COLORS = ['#cddbf3', '#f3dccb', '#d3ead6', '#ead4ea', '#f1e7bd', '#d0e7eb', '#ebd3d3', '#ddd8f0'];
const GRADE_COLORS: Record<string, string> = { good: '#4c9a6a', review: '#d9a441', reaudit: '#c8553d' };
export const MILESTONE_COLORS: Record<string, string> = { death: '#3b3b3b', breakthrough: '#0f7d8c', romance: '#d6457a', payoff: '#7a45b5' };
const MILESTONE_LABELS: Record<string, string> = { death: '死亡', breakthrough: '突破', romance: '感情确认', payoff: '伏笔回收' };

/**
 * The one global control: a chapter slider drawn over story arcs (named), event density,
 * milestone ticks and per-chapter audit quality, with a hover preview and the spoiler lock.
 */
export function ChapterAxis() {
  const { ix, ch, setCh, lock, setLock } = useApp();
  const canvas = useRef<HTMLCanvasElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ x: number; n: number } | null>(null);
  const list = ix.chapterList;
  const pos = Math.max(0, list.indexOf(ch));
  const maxDensity = useMemo(() => Math.max(1, ...ix.m.chapters.map((c) => c.density ?? 0)), [ix]);
  const milestones = ix.m.milestones ?? [];
  const lockIndex = lock == null ? list.length - 1 : list.filter((c) => c <= lock).length - 1;

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
      const index = (c: number) => { const i = list.findIndex((v) => v >= c); return i < 0 ? n - 1 : i; };
      // named top-level arcs
      g.font = '10px sans-serif'; g.textBaseline = 'middle';
      ix.m.arcs.filter((a) => !a.parent).forEach((a, k) => {
        const i0 = index(a.from), i1 = a.to == null ? n - 1 : index(a.to);
        g.fillStyle = ARC_COLORS[k % ARC_COLORS.length];
        g.fillRect(x(i0), 0, x(i1 + 1) - x(i0), 12);
        const room = x(i1 + 1) - x(i0) - 6;
        if (room > 24) { g.fillStyle = '#3b4654'; g.fillText(fit(g, a.title, room), x(i0) + 3, 6.5); }
      });
      // density
      g.fillStyle = '#b4bfcc';
      ix.m.chapters.forEach((c, i) => {
        const d = (c.density ?? 0) / maxDensity;
        if (d > 0) g.fillRect(x(i), h - 4 - d * (h - 22), bw, d * (h - 22));
      });
      // milestones
      for (const m of milestones) {
        const i = index(m.ch);
        g.fillStyle = MILESTONE_COLORS[m.kind] ?? '#333';
        g.beginPath(); g.arc(x(i) + bw / 2, 16, 2.6, 0, Math.PI * 2); g.fill();
      }
      // audit quality
      ix.m.chapters.forEach((c, i) => {
        const grade = c.quality?.grade;
        g.fillStyle = grade ? GRADE_COLORS[grade] ?? '#ccc' : c.audit ? '#a8c5e0' : '#e4e7ec';
        g.fillRect(x(i), h - 3, bw, 3);
      });
      // locked region
      if (lockIndex < n - 1) { g.fillStyle = 'rgba(244,241,234,0.85)'; g.fillRect(x(lockIndex + 1), 0, w - x(lockIndex + 1), h); }
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(el);
    return () => ro.disconnect();
  }, [ix, list, maxDensity, lockIndex]);

  const chapter = ix.chapters.get(ch);
  const arcs = (chapter?.arcs ?? []).map((id) => ix.arcs.get(id)?.title).filter(Boolean);
  const step = (d: number) => setCh(list[Math.min(lockIndex, Math.max(0, pos + d))]);
  const onMove = (e: MouseEvent) => {
    const r = track.current!.getBoundingClientRect();
    const i = Math.min(list.length - 1, Math.max(0, Math.floor(((e.clientX - r.left) / r.width) * list.length)));
    setHover(i <= lockIndex ? { x: e.clientX - r.left, n: list[i] } : null);
  };
  const hc = hover ? ix.chapters.get(hover.n) : undefined;
  const hm = hover ? milestones.filter((m) => m.ch === hover.n) : [];

  return (
    <div class="axis">
      <button class="axis-step" onClick={() => step(-1)} disabled={pos === 0} aria-label="上一章">‹</button>
      <div class="axis-track" ref={track} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <canvas ref={canvas} class="axis-canvas" />
        <input
          type="range" min={0} max={Math.max(0, list.length - 1)} value={pos} class="axis-range" aria-label="章节"
          onInput={(e) => setCh(list[Math.min(lockIndex, Number((e.target as HTMLInputElement).value))])}
        />
        {hover && hc && (
          <div class="axis-tip" style={{ left: `${Math.min(Math.max(hover.x, 120), (track.current?.clientWidth ?? 240) - 120)}px` }}>
            <b>第{hover.n}章{hc.title ? ` · ${hc.title}` : ''}</b>
            {hc.summary && <span>{hc.summary.slice(0, 48)}{hc.summary.length > 48 ? '…' : ''}</span>}
            {hm.map((m) => <span class="tip-ms" style={{ color: MILESTONE_COLORS[m.kind] }}>● {MILESTONE_LABELS[m.kind]}：{m.label}</span>)}
          </div>
        )}
      </div>
      <button class="axis-step" onClick={() => step(1)} disabled={pos >= lockIndex} aria-label="下一章">›</button>
      <label class="axis-num">
        第<input type="number" value={ch} min={list[0]} max={list[lockIndex]}
          onChange={(e) => {
            const want = Number((e.target as HTMLInputElement).value);
            const near = list.reduce((a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a), list[0]);
            setCh(near);
          }} />章
      </label>
      <button class={`lock-btn${lock != null ? ' on' : ''}`} onClick={() => setLock(lock == null ? ch : null)}
        title={lock != null ? `防剧透：只显示到第${lock}章（点击解除）` : '防剧透：锁定在当前章，之后的内容一律不显示'}>
        <Icon name="lock" size={14} />{lock != null ? `≤${lock}` : ''}
      </button>
      <span class="axis-arc" title={arcs.join(' / ')}>{arcs[arcs.length - 1] ?? ''}</span>
    </div>
  );
}

function fit(g: CanvasRenderingContext2D, text: string, room: number): string {
  if (g.measureText(text).width <= room) return text;
  let t = text;
  while (t.length > 1 && g.measureText(t + '…').width > room) t = t.slice(0, -1);
  return t + '…';
}
