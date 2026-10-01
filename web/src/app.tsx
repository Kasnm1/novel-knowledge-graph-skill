import { createContext } from 'preact';
import { useCallback, useContext, useEffect, useMemo, useState } from 'preact/hooks';
import { Index, Model } from './model';
import { Membership, memberships } from './sets';
import { Icon } from './components/Icon';
import { ChapterAxis } from './components/ChapterAxis';
import { Search } from './components/Search';
import { ChapterView } from './views/ChapterView';
import { PeopleView } from './views/PeopleView';
import { StoryView } from './views/StoryView';
import { RelationsView } from './views/RelationsView';
import { WorldView } from './views/WorldView';
import { ThreadsView } from './views/ThreadsView';

export type ViewName = 'chapter' | 'story' | 'people' | 'relations' | 'world' | 'threads';
export const VIEWS: [ViewName, string][] = [
  ['chapter', '本章'], ['story', '故事'], ['people', '人物'], ['relations', '关系'], ['world', '世界'], ['threads', '线索'],
];

export interface Route { view: ViewName; arg?: string }
export interface Ctx {
  ix: Index; ch: number; setCh: (n: number) => void; route: Route; go: (view: ViewName, arg?: string) => void;
  /** sets as of the current chapter, computed once per chapter for every view */
  sets: { memberships: Map<string, Membership> };
  /** spoiler lock: the furthest chapter the reader allows the page to show */
  lock: number | null; setLock: (n: number | null) => void;
}
export const AppCtx = createContext<Ctx>(null as unknown as Ctx);
export const useApp = () => useContext(AppCtx);

const lockKey = (ix: Index) => `nkg-lock:${ix.m.meta.title ?? ''}`;
function readLock(ix: Index): number | null {
  try { const v = localStorage.getItem(lockKey(ix)); return v ? Number(v) : null; } catch { return null; }
}
function clamp(ix: Index, n: number, lock: number | null): number {
  if (lock == null || n <= lock) return n;
  const allowed = ix.chapterList.filter((c) => c <= lock);
  return allowed[allowed.length - 1] ?? ix.chapterList[0];
}

function parseHash(ix: Index): { route: Route; ch: number } {
  const [path, query] = location.hash.replace(/^#\/?/, '').split('?');
  const [view, ...rest] = (path || 'chapter').split('/');
  const params = new URLSearchParams(query || '');
  const wanted = Number(params.get('c'));
  const ch = ix.chapters.has(wanted) ? wanted : ix.chapterList[0] ?? 0;
  const known = VIEWS.some(([v]) => v === view);
  return { route: { view: (known ? view : 'chapter') as ViewName, arg: rest.length ? decodeURIComponent(rest.join('/')) : undefined }, ch };
}

export function App({ model }: { model: Model }) {
  const ix = useMemo(() => new Index(model), [model]);
  const [lock, setLockState] = useState<number | null>(() => readLock(ix));
  const [state, setState] = useState(() => {
    const s = parseHash(ix), ch = clamp(ix, s.ch, readLock(ix));
    if (ch !== s.ch) history.replaceState(null, '', location.hash.replace(/c=\d+/, `c=${ch}`));
    return { ...s, ch };
  });
  const [searching, setSearching] = useState(false);
  const setLock = useCallback((n: number | null) => {
    try { n == null ? localStorage.removeItem(lockKey(ix)) : localStorage.setItem(lockKey(ix), String(n)); } catch { /* private mode: lock lasts this visit */ }
    setLockState(n);
    if (n != null && state.ch > n) setState((s) => ({ ...s, ch: clamp(ix, s.ch, n) }));
  }, [ix, state.ch]);

  useEffect(() => {
    const onHash = () => {
      const s = parseHash(ix), ch = clamp(ix, s.ch, lock);
      if (ch !== s.ch) history.replaceState(null, '', location.hash.replace(/c=\d+/, `c=${ch}`));
      setState({ ...s, ch });
    };
    addEventListener('hashchange', onHash);
    return () => removeEventListener('hashchange', onHash);
  }, [ix, lock]);

  const write = useCallback((route: Route, ch: number, replace: boolean) => {
    const hash = `#/${route.view}${route.arg ? '/' + encodeURIComponent(route.arg) : ''}?c=${ch}`;
    if (replace) history.replaceState(null, '', hash); else history.pushState(null, '', hash);
    setState({ route, ch });
  }, []);

  const setCh = useCallback((n: number) => write(state.route, clamp(ix, n, lock), true), [state.route, write, ix, lock]);
  const go = useCallback((view: ViewName, arg?: string) => write({ view, arg }, state.ch, false), [state.ch, write]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearching(true); return; }
      const typing = (e.target as HTMLElement)?.closest?.('input, textarea, select');
      if (typing) return;
      const list = ix.chapterList, i = list.indexOf(state.ch);
      if (e.key === 'ArrowLeft' && i > 0) setCh(list[i - 1]);
      if (e.key === 'ArrowRight' && i < list.length - 1) setCh(list[i + 1]);
      if (e.key === '/') { e.preventDefault(); setSearching(true); }
    };
    addEventListener('keydown', onKey);
    return () => removeEventListener('keydown', onKey);
  }, [ix, state.ch, setCh]);

  const sets = useMemo(() => ({ memberships: memberships(ix, state.ch) }), [ix, state.ch]);
  const ctx: Ctx = { ix, ch: state.ch, setCh, route: state.route, go, sets, lock, setLock };
  const { view, arg } = state.route;
  const meta = model.meta;

  return (
    <AppCtx.Provider value={ctx}>
      <div class="shell">
        <header class="top">
          <div class="brand">
            <strong>{meta.title ?? '小说知识图谱'}</strong>
            <span class="muted">已分析 {meta.chapters ?? ix.chapterList.length} 章{meta.audited ? ` · 审计卡 ${meta.audited} 章` : ''}{meta.cutoff != null ? ` · 截至第 ${meta.cutoff} 章` : ''}</span>
          </div>
          <ChapterAxis />
          <button class="search-btn" onClick={() => setSearching(true)} title="搜索（Ctrl+K）">搜索 <kbd>Ctrl K</kbd></button>
        </header>
        <nav class="nav">
          {VIEWS.map(([v, label]) => (
            <a href={`#/${v}?c=${state.ch}`} class={v === view ? 'on' : ''} data-view={v}><Icon name={v} />{label}</a>
          ))}
        </nav>
        <main class="main" data-view={view}>
          {view === 'chapter' && <ChapterView />}
          {view === 'story' && <StoryView arcId={arg} />}
          {view === 'people' && <PeopleView entityId={arg} />}
          {view === 'relations' && <RelationsView focus={arg} />}
          {view === 'world' && <WorldView tab={arg} />}
          {view === 'threads' && <ThreadsView tab={arg} />}
        </main>
        {searching && <Search onClose={() => setSearching(false)} />}
      </div>
    </AppCtx.Provider>
  );
}
