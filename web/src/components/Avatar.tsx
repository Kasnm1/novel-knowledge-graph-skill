import { useApp } from '../app';
import { orgFill, orgInk, typeInk } from '../palette';

/** A round initial: tinted by the person's primary organization at this chapter, gold ring for the protagonist. */
export function Avatar({ id, size = 28 }: { id: string; size?: number }) {
  const { ix, ch, sets } = useApp();
  const e = ix.entity(id);
  if (!e) return null;
  const name = ix.name(id, ch);
  const org = e.type === 'character' ? sets.memberships.get(id)?.primary : e.type === 'organization' ? id : undefined;
  const bg = org ? orgFill(org) : '#eef1f5';
  const ink = org ? orgInk(org) : typeInk(e.type);
  const initial = [...name.replace(/[〔〕\[\]]/g, '')][0] ?? '?';
  return (
    <span class={`avatar${e.tier === 'protagonist' ? ' pro' : ''}`} aria-hidden="true"
      style={{ width: `${size}px`, height: `${size}px`, fontSize: `${Math.round(size * 0.46)}px`, background: bg, color: ink }}>
      {initial}
    </span>
  );
}
