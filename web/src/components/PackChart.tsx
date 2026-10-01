import { hierarchy, pack, HierarchyCircularNode } from 'd3-hierarchy';
import { useMemo, useState } from 'preact/hooks';
import { TreeNode } from '../sets';

type Node = HierarchyCircularNode<TreeNode>;
const DEPTH_FILL = ['#f7f9fc', '#eef3fb', '#e3ecf8', '#d8e4f4', '#cddcf0', '#c2d4ec'];

export interface PackProps {
  root: TreeNode;
  /** colour of a member dot or a set's fill by entity id (e.g. controlling faction, entity type) */
  tint?: (entity: string | undefined, node: TreeNode) => string | undefined;
  /** entity ids to emphasise (this chapter's places, a searched name) */
  highlight?: Set<string>;
  /** small labelled dots drawn inside a set (e.g. who is in this place) */
  pins?: Map<string, { id: string; label: string }[]>;
  onPick?: (entity: string) => void;
  height?: number;
}

/**
 * Nested sets as circles inside circles: a set's circle contains its subsets and members.
 * Click a set to zoom into it; the breadcrumb walks back out. Area follows member count.
 */
export function PackChart({ root, tint, highlight, pins, onPick, height = 640 }: PackProps) {
  const size = 1000;
  const layout = useMemo(() => {
    const h = hierarchy(root).sum((d) => (d.children?.length ? 0 : d.value ?? 1))
      .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
    return pack<TreeNode>().size([size, size]).padding((d) => (d.depth === 0 ? 8 : 4))(h);
  }, [root]);
  const [focusId, setFocusId] = useState<string>('__root');
  const focus = layout.descendants().find((d) => d.data.id === focusId) ?? layout;
  const k = size / (focus.r * 2.05);
  const tx = (x: number) => (x - focus.x) * k + size / 2;
  const ty = (y: number) => (y - focus.y) * k + size / 2;
  const trail = focus.ancestors().reverse();
  const visible = layout.descendants().filter((d) => d.depth <= focus.depth + 3 && d.r * k > 1.5 && isInside(d, focus));

  return (
    <div class="pack">
      <div class="crumbs">
        {trail.map((d, i) => (
          <>
            {i > 0 && <span class="sep">⊃</span>}
            <button class={d === focus ? 'on' : ''} onClick={() => setFocusId(d.data.id)}>{d.data.name}</button>
          </>
        ))}
        <span class="muted pack-note">圆套圆表示从属（子集），不代表真实方位或距离</span>
      </div>
      <svg viewBox={`0 0 ${size} ${size}`} style={{ height: `${height}px`, maxWidth: '100%' }} role="img" aria-label="集合层级图">
        {visible.map((d) => {
          const r = d.r * k, x = tx(d.x), y = ty(d.y), data = d.data;
          if (data.kind === 'member' || data.kind === 'ghost') {
            const fill = tint?.(data.entity, data) ?? '#2f6fd6';
            const hot = data.entity && highlight?.has(data.entity);
            return (
              <g class={`pk-member ${data.kind}`} onClick={() => data.entity && onPick?.(data.entity)} data-entity={data.entity}>
                <circle cx={x} cy={y} r={Math.max(r, 2)} fill={data.kind === 'ghost' ? 'none' : fill} stroke={hot ? '#e8b931' : fill}
                  stroke-width={hot ? 3 : 1} stroke-dasharray={data.kind === 'ghost' ? '3 2' : undefined} fill-opacity={0.85} />
                {r > 9 && <text x={x} y={y + 4} text-anchor="middle" class="pk-label" font-size={Math.min(13, r * 0.7)}>{data.name}</text>}
                <title>{data.name}{data.kind === 'ghost' ? '（同时属于这里）' : ''}</title>
              </g>
            );
          }
          const fill = tint?.(data.entity, data) ?? DEPTH_FILL[Math.min(d.depth, DEPTH_FILL.length - 1)];
          const hot = data.entity && highlight?.has(data.entity);
          const here = data.entity ? pins?.get(data.entity) ?? [] : [];
          return (
            <g class={`pk-set ${data.kind}`} data-entity={data.entity}>
              <circle cx={x} cy={y} r={r} fill={fill} stroke={hot ? '#e8b931' : '#b9c6d8'} stroke-width={hot ? 3 : 1}
                stroke-dasharray={data.kind === 'loose' ? '5 4' : undefined}
                onClick={(e) => { e.stopPropagation(); if (d.children) setFocusId(data.id); else if (data.entity) onPick?.(data.entity); }} />
              {r > 22 && d !== focus && (
                <text x={x} y={y - r + Math.min(18, r * 0.3)} text-anchor="middle" class="pk-set-label" font-size={Math.min(15, Math.max(10, r / 6))}
                  onClick={() => data.entity && onPick?.(data.entity)}>{data.name}</text>
              )}
              {here.length > 0 && r > 12 && here.slice(0, 6).map((p, i) => (
                <g class="pk-pin" onClick={() => onPick?.(p.id)}>
                  <circle cx={x - r * 0.5 + (i % 3) * r * 0.5} cy={y + r * 0.35 + Math.floor(i / 3) * 14} r={4} fill="#c23d6a" />
                  {r > 50 && <text x={x - r * 0.5 + (i % 3) * r * 0.5 + 6} y={y + r * 0.35 + Math.floor(i / 3) * 14 + 4} font-size="11" class="pk-pin-label">{p.label}</text>}
                </g>
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function isInside(d: Node, focus: Node): boolean {
  for (let a: Node | null = d; a; a = a.parent) if (a === focus) return true;
  return false;
}
