// Sets and subsets as of a chapter: who belongs to which organization, how organizations and
// places nest, and where people are. Only interval picks over the reader model's relations,
// facts and events, plus tree assembly — no story fact is inferred here.
import { Index, holds } from './model';

const NESTING = new Set(['subgroup_of', 'part_of', 'located_in']);
const SEAT = new Set(['located_in', 'located_at', 'part_of']);
export const WHERE_TTL = 5;

export interface Membership { orgs: string[]; primary?: string }

/** Every entity's organizations at `ch` (affiliation relations pointing at an organization). */
export function memberships(ix: Index, ch: number): Map<string, Membership> {
  const out = new Map<string, Membership>();
  const starts = new Map<string, Map<string, [number, number]>>();
  for (const r of ix.m.relations) {
    if (r.group !== 'affiliation' || !holds(r.from, r.to, ch)) continue;
    const target = ix.entity(r.t);
    if (!target || target.type !== 'organization' || !ix.visible(r.s, ch) || !ix.visible(r.t, ch)) continue;
    const per = starts.get(r.s) ?? new Map();
    const span = (r.to ?? Infinity) - r.from;
    const prev = per.get(r.t);
    if (!prev || r.from > prev[0]) per.set(r.t, [r.from, span]);
    starts.set(r.s, per);
  }
  for (const [id, per] of starts) {
    const orgs = [...per.keys()];
    const hinted = ix.entity(id)?.primary;
    const primary = hinted && per.has(hinted) ? hinted
      : [...per.entries()].sort((a, b) => b[1][0] - a[1][0] || b[1][1] - a[1][1])[0][0];
    out.set(id, { orgs, primary });
  }
  return out;
}

/** child → parent among entities of one type, from nesting relations active at `ch`; cycles are cut. */
export function parents(ix: Index, ch: number, type: 'organization' | 'location'): Map<string, string> {
  const parent = new Map<string, string>();
  for (const r of ix.m.relations) {
    if (!NESTING.has(r.type) || !holds(r.from, r.to, ch)) continue;
    if (ix.entity(r.s)?.type !== type || ix.entity(r.t)?.type !== type) continue;
    if (!ix.visible(r.s, ch) || !ix.visible(r.t, ch) || r.s === r.t) continue;
    if (!parent.has(r.s)) parent.set(r.s, r.t);
  }
  for (const start of [...parent.keys()]) {
    const seen = new Set([start]);
    let cur = parent.get(start);
    while (cur) {
      if (seen.has(cur)) { parent.delete(start); break; }
      seen.add(cur);
      cur = parent.get(cur);
    }
  }
  return parent;
}

/** Organization → its seat (a location), and location → controlling organization, at `ch`. */
export function placeLinks(ix: Index, ch: number) {
  const seat = new Map<string, string>(), control = new Map<string, string>();
  for (const r of ix.m.relations) {
    if (!holds(r.from, r.to, ch) || !ix.visible(r.s, ch) || !ix.visible(r.t, ch)) continue;
    const s = ix.entity(r.s)?.type, t = ix.entity(r.t)?.type;
    if (r.type === 'controlled_by' && s === 'location' && t === 'organization') control.set(r.s, r.t);
    else if (SEAT.has(r.type) && s === 'organization' && t === 'location' && !seat.has(r.s)) seat.set(r.s, r.t);
  }
  return { seat, control };
}

/**
 * Where a character is at `ch`: an event of this chapter, else an event within WHERE_TTL
 * chapters, else a location state that names a place exactly. Undefined when unknown.
 */
export function whereabouts(ix: Index, ch: number): Map<string, { place: string; since: number }> {
  const out = new Map<string, { place: string; since: number }>();
  for (const [, ev] of Object.entries(ix.m.events)) {
    if (!ev.where || ev.ch > ch || ev.ch < ch - WHERE_TTL || !ix.visible(ev.where, ch)) continue;
    for (const p of ev.who ?? []) {
      const prev = out.get(p);
      if (!prev || ev.ch >= prev.since) out.set(p, { place: ev.where, since: ev.ch });
    }
  }
  for (const f of ix.m.facts) {
    if (f.facet !== 'location' || !f.place || !holds(f.from, f.to, ch) || !ix.visible(f.place, ch)) continue;
    const prev = out.get(f.e);
    if (!prev || f.from > prev.since) out.set(f.e, { place: f.place, since: f.from });
  }
  return out;
}

export interface TreeNode { id: string; name: string; kind: 'set' | 'member' | 'ghost' | 'root' | 'loose'; value?: number; children?: TreeNode[]; entity?: string }

/** Build a nested set tree: roots are the parentless nodes; members hang under their set. */
export function nest(
  ix: Index, ch: number, setIds: string[], parent: Map<string, string>,
  members: Map<string, string[]>, ghosts: Map<string, string[]>, rootName: string, looseName: string,
): TreeNode {
  const node = (id: string): TreeNode => ({ id, entity: id, name: ix.name(id, ch), kind: 'set', children: [] });
  const nodes = new Map(setIds.map((id) => [id, node(id)]));
  const root: TreeNode = { id: '__root', name: rootName, kind: 'root', children: [] };
  for (const [id, n] of nodes) {
    const p = parent.get(id);
    (p && nodes.get(p) ? nodes.get(p)! : root).children!.push(n);
  }
  for (const [setId, ids] of members) {
    const target = setId === '__loose' ? undefined : nodes.get(setId);
    const holder = target ?? (() => {
      let loose = root.children!.find((c) => c.id === '__loose');
      if (!loose) { loose = { id: '__loose', name: looseName, kind: 'loose', children: [] }; root.children!.push(loose); }
      return loose;
    })();
    for (const id of ids) holder.children!.push({ id: `${setId}:${id}`, entity: id, name: ix.name(id, ch), kind: 'member', value: 1 });
  }
  for (const [setId, ids] of ghosts) {
    const target = nodes.get(setId);
    for (const id of ids) target?.children!.push({ id: `ghost:${setId}:${id}`, entity: id, name: ix.name(id, ch), kind: 'ghost', value: 1 });
  }
  // empty sets still take space so they can be seen and clicked
  const fill = (n: TreeNode) => { if (n.children) { n.children.forEach(fill); if (!n.children.length) n.value = 1; } };
  fill(root);
  return root;
}
