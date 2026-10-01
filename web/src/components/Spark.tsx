import { useApp } from '../app';

/** Event density of the chapters around the current one, so a chapter reads against the book's rhythm. */
export function DensitySpark({ span = 20 }: { span?: number }) {
  const { ix, ch, setCh } = useApp();
  const list = ix.chapterList, i = list.indexOf(ch);
  const from = Math.max(0, i - span / 2), win = list.slice(from, Math.min(list.length, from + span + 1));
  const values = win.map((n) => ix.chapters.get(n)?.density ?? 0);
  const max = Math.max(1, ...values), w = 8, h = 28;
  return (
    <svg class="spark" width={win.length * w} height={h} role="img" aria-label="附近章节的情节密度">
      {win.map((n, k) => {
        const bh = Math.max(2, (values[k] / max) * (h - 4));
        return (
          <rect x={k * w + 1} y={h - bh} width={w - 2} height={bh} rx={1.5} class={n === ch ? 'on' : ''} onClick={() => setCh(n)}>
            <title>第{n}章 · {values[k]} 条记录</title>
          </rect>
        );
      })}
    </svg>
  );
}

/** A step line of one value over chapters (a level ladder position), marking each change. */
export function StepLine({ points, last, labels }: { points: [number, number][]; last: number; labels: string[] }) {
  if (points.length < 2) return null;
  const W = 520, H = 120, pad = 22;
  const x0 = points[0][0], x1 = Math.max(last, points[points.length - 1][0] + 1);
  const ys = points.map((p) => p[1]), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const X = (c: number) => pad + ((c - x0) / Math.max(1, x1 - x0)) * (W - pad * 2);
  const Y = (v: number) => H - pad - ((v - y0) / Math.max(1e-9, y1 - y0)) * (H - pad * 2);
  let d = `M${X(points[0][0])},${Y(points[0][1])}`;
  for (let k = 1; k < points.length; k++) d += ` H${X(points[k][0])} V${Y(points[k][1])}`;
  d += ` H${X(x1)}`;
  return (
    <svg class="stepline" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="成长曲线">
      <path d={d} fill="none" stroke="currentColor" stroke-width="2" />
      {(() => {
        // label a point only when it has room; every point still names itself on hover
        let lastX = -Infinity;
        return points.map((p, k) => {
          const x = X(p[0]), room = x - lastX >= 64 || k === points.length - 1 && x - lastX >= 30;
          if (room) lastX = x;
          return (
            <g>
              <circle cx={x} cy={Y(p[1])} r={3.5}><title>第{p[0]}章 · {labels[k]}</title></circle>
              {room && <text x={x} y={Y(p[1]) - 7} text-anchor="middle" font-size="10">{labels[k].length > 8 ? labels[k].slice(0, 8) + '…' : labels[k]}</text>}
              {room && <text x={x} y={H - 6} text-anchor="middle" font-size="9" class="muted-text">{p[0]}</text>}
            </g>
          );
        });
      })()}
    </svg>
  );
}
