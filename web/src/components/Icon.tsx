// Small inline line icons for the navigation; no icon font, no network.
const PATHS: Record<string, string> = {
  chapter: 'M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h10',
  story: 'M4 6h16M4 12h10M4 18h13',
  people: 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M17 11a3 3 0 1 0 0-6M22 21a6 6 0 0 0-4-5.6',
  relations: 'M6 6m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0M18 6m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0M12 18m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0M8.5 7.5l2.5 8M15.5 7.5l-2.5 8M9 6h6',
  world: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
  threads: 'M4 5h16v4H4zM4 13h10v4H4zM16 13h4v6h-4z',
  lock: 'M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3',
};

export function Icon({ name, size = 16 }: { name: string; size?: number }) {
  return (
    <svg class="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d={PATHS[name] ?? ''} />
    </svg>
  );
}
