// One colour per organization everywhere (faction chart, graph boxes, chips, territory), and
// one per entity type. Colours come from a stable hash of the id, so they never shift
// between chapters or views.
const HUES = [212, 280, 152, 28, 340, 190, 48, 0, 250, 120, 310, 170];

function hash(id: string): number {
  let h = 7;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h;
}

export const orgHue = (id: string) => HUES[hash(id) % HUES.length];
export const orgFill = (id: string) => `hsl(${orgHue(id)} 55% 93%)`;
export const orgStroke = (id: string) => `hsl(${orgHue(id)} 40% 62%)`;
export const orgInk = (id: string) => `hsl(${orgHue(id)} 45% 32%)`;

export const TYPE_INK: Record<string, string> = {
  character: '#2f5fb3', organization: '#7a45b5', location: '#2b7a55', item: '#a3561a', skill: '#b3365f',
  concept: '#5f6b7a', creature: '#6e5f28', level_axis: '#0f6f7c', title: '#5f6b7a',
};
export const typeInk = (type: string) => TYPE_INK[type] ?? '#5f6b7a';
