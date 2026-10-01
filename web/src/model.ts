// The reader model built by scripts/build_reader_model.py, and the only lookups the page does:
// pick the interval or the step that contains the chapter. No as-of reasoning happens here.

export type Step<T = string> = [number, T];
export type Dated<T = string> = [number, T];

export interface Fact {
  e: string; facet: string; target?: string; from: number; to?: number; value: string;
  sort?: number; action?: string; reason?: string; ev?: string[]; volatile?: boolean; id?: string; place?: string;
}
export interface Relation {
  id: string; s: string; t: string; type: string; group: string; from: number; to?: number;
  status?: Step[]; stance?: Step[]; notes?: Dated[]; ev?: string[];
}
export interface Entity {
  type: string; first: number; names: Dated[]; aliases?: Dated[]; summary?: Dated[];
  tier: string; tierSource: string; categories?: string[]; headlines?: [number, number | null, string][];
  bios?: Record<string, string>; toProtagonist?: string; primary?: string; attrs?: [number, string, string][]; events?: number;
}
export interface CastRow { id: string; mode: string; role?: string; check?: string }
export interface Scene { purpose?: string; who?: string[]; where?: string; when?: string; pov?: string; events?: string[] }
export interface Chapter {
  n: number; title?: string; summary?: string; arcs?: string[]; events?: string[]; cast?: CastRow[];
  scenes?: Scene[]; prev?: string; next?: string; functions?: string[]; cliffhanger?: string;
  audit?: Record<string, { s?: string; c?: number; r?: string }>; density?: number;
  quality?: { score?: number; grade?: string; verified?: boolean }; ev?: string[];
}
export interface StoryEvent {
  ch: number; type?: string; title?: string; desc?: string; who?: string[]; where?: string;
  tags?: string[]; ev?: string[]; combat?: boolean; death?: boolean;
}
export interface Arc {
  id: string; title: string; from: number; to?: number; parent?: string; phase?: string; status?: string;
  summary?: string; recap?: string; cast?: string[]; turns?: string[];
}
export interface Clue {
  id: string; label: string; from: number; obs?: string; steps?: [number, string, string][];
  payoffAt?: number; who?: string[]; status: Step[]; ev?: string[];
}
export interface Promise_ {
  id: string; kind?: string; terms?: string; from: number; by?: string[]; to?: string[]; deadline?: number;
  status: Step[]; resolution?: string; resolvedAt?: number; ev?: string[];
}
export interface Route {
  id: string; who: string; pro?: string; from: number; status: Step[]; met?: number; ambiguous?: number;
  confirmed?: number; firstSex?: number; basis?: string; consent?: string; steps?: [number, string, string][];
}
export interface Act { id: string; ch: number; type?: string; by?: string[]; to?: string[]; consent?: string; desc?: string; ev?: string[] }
export interface Model {
  schema: string;
  meta: { title?: string; first: number; last: number; cutoff?: number; protagonists?: string[]; audited?: number; chapters?: number };
  vocab: Record<string, Record<string, string>>;
  arcs: Arc[]; chapters: Chapter[]; entities: Record<string, Entity>; facts: Fact[]; relations: Relation[];
  events: Record<string, StoryEvent>;
  threads: { clues: Clue[]; promises: Promise_[]; routes: Route[]; acts: Act[] };
  levels: Record<string, { rungs: { label: string; sort?: number; from: number }[] }>;
  evidence: Record<string, [number, string]>;
  milestones?: Milestone[];
}
export interface Milestone { ch: number; kind: 'death' | 'breakthrough' | 'romance' | 'payoff'; label: string; who?: string; event?: string }

export const holds = (from: number, to: number | null | undefined, ch: number) => from <= ch && (to == null || ch <= to);

export function stepAt<T>(steps: Step<T>[] | undefined, ch: number): Step<T> | undefined {
  let found: Step<T> | undefined;
  for (const s of steps ?? []) { if (s[0] <= ch) found = s; else break; }
  return found;
}

export function datedUpTo<T>(rows: Dated<T>[] | undefined, ch: number): Dated<T>[] {
  return (rows ?? []).filter((r) => r[0] <= ch);
}

/** Lookups precomputed once per model. */
export class Index {
  readonly chapters = new Map<number, Chapter>();
  readonly chapterList: number[];
  readonly factsByEntity = new Map<string, Fact[]>();
  readonly relationsByEntity = new Map<string, Relation[]>();
  readonly eventsByEntity = new Map<string, string[]>();
  readonly arcs = new Map<string, Arc>();

  constructor(readonly m: Model) {
    for (const c of m.chapters) this.chapters.set(c.n, c);
    this.chapterList = m.chapters.map((c) => c.n);
    for (const f of m.facts) push(this.factsByEntity, f.e, f);
    for (const r of m.relations) { push(this.relationsByEntity, r.s, r); push(this.relationsByEntity, r.t, r); }
    for (const [id, e] of Object.entries(m.events)) for (const p of e.who ?? []) push(this.eventsByEntity, p, id);
    for (const a of m.arcs) this.arcs.set(a.id, a);
  }

  entity(id: string): Entity | undefined { return this.m.entities[id]; }
  visible(id: string, ch: number): boolean { const e = this.m.entities[id]; return !!e && e.first <= ch; }

  name(id: string, ch: number): string {
    const e = this.m.entities[id];
    if (!e || e.first > ch) return '〔尚未出场〕';
    return stepAt(e.names, ch)?.[1] ?? e.names[0]?.[1] ?? id;
  }

  factsAt(id: string, ch: number): Fact[] {
    return (this.factsByEntity.get(id) ?? []).filter((f) => holds(f.from, f.to, ch));
  }

  relationsAt(id: string, ch: number): Relation[] {
    return (this.relationsByEntity.get(id) ?? []).filter((r) => holds(r.from, r.to, ch) && this.visible(r.s, ch) && this.visible(r.t, ch));
  }

  label(group: string, key: string | undefined | null): string {
    if (!key) return '';
    return this.m.vocab[group]?.[key] ?? key;
  }
}

function push<K, V>(map: Map<K, V[]>, key: K, value: V) {
  const list = map.get(key);
  if (list) list.push(value); else map.set(key, [value]);
}

export function loadModel(): Model | null {
  const node = document.getElementById('nkg-model');
  const text = node?.textContent?.trim();
  if (!text || text[0] !== '{') return null; // the unfilled slot in a dev build
  return JSON.parse(text) as Model;
}
