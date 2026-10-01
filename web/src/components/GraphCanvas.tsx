import cytoscape, { ElementDefinition } from 'cytoscape';
// @ts-expect-error the extension ships no type declarations
import fcose from 'cytoscape-fcose';
import { useEffect, useRef } from 'preact/hooks';

cytoscape.use(fcose);

export const GROUP_COLORS: Record<string, string> = {
  romance: '#d6457a', family: '#c98a1b', mentorship: '#2d8a5f', ally: '#2f6fd6', hostile: '#c8553d',
  affiliation: '#8a4fc7', identity: '#5f6b7a', possession: '#9aa7b8', place: '#9aa7b8', other: '#9aa7b8',
};
const TYPE_COLORS: Record<string, string> = {
  character: '#2f6fd6', organization: '#8a4fc7', location: '#2d8a5f', item: '#b8621b', skill: '#c23d6a',
};

const STYLE: cytoscape.StylesheetJson = [
  { selector: 'node', style: {
    'background-color': (n: cytoscape.NodeSingular) => TYPE_COLORS[n.data('type')] ?? '#5f6b7a',
    label: 'data(label)', 'font-size': 11, 'text-valign': 'bottom', 'text-margin-y': 3, color: '#1f2933',
    'text-outline-color': '#fff', 'text-outline-width': 2,
  } },
  { selector: 'node[size]', style: { width: 'data(size)', height: 'data(size)' } },
  { selector: 'node[?focus]', style: { 'border-width': 3, 'border-color': '#e8b931', 'font-weight': 'bold', 'font-size': 13 } },
  { selector: 'node[?protagonist]', style: { 'background-color': '#c23d6a' } },
  { selector: ':parent', style: {
    'background-color': (n: cytoscape.NodeSingular) => n.data('fill') ?? '#f2f5fa', 'background-opacity': 0.7,
    'border-color': (n: cytoscape.NodeSingular) => n.data('stroke') ?? '#b9c6d8', 'border-width': 1, shape: 'round-rectangle',
    label: 'data(label)', 'text-valign': 'top', 'text-halign': 'center', 'font-size': 12, 'font-weight': 'bold',
    color: '#4a5563', padding: '14px', 'text-margin-y': -2,
  } },
  { selector: ':parent[kind = "circle"]', style: { 'border-style': 'dashed' } },
  { selector: 'edge', style: {
    width: 1.6, 'line-color': (e: cytoscape.EdgeSingular) => GROUP_COLORS[e.data('group')] ?? '#9aa7b8',
    'curve-style': 'bezier', opacity: 0.75, label: 'data(label)', 'font-size': 9, color: '#6b7785',
    'text-rotation': 'autorotate', 'text-background-color': '#fff', 'text-background-opacity': 0.8, 'text-background-padding': '1px',
  } },
  { selector: 'edge[stance = "hostile"], edge[stance = "contempt"], edge[group = "hostile"]', style: { 'line-style': 'dashed' } },
  { selector: 'edge[stance = "intimate"], edge[stance = "warm"]', style: { width: 3 } },
  { selector: 'edge[?hidelabel]', style: { label: '' } },
  { selector: '.faded', style: { opacity: 0.15 } },
  { selector: 'edge.ondemand', style: { display: 'none' } },
  { selector: 'edge.ondemand.shown', style: { display: 'element' } },
];

export interface GraphProps {
  elements: ElementDefinition[];
  onPick?: (id: string, kind: 'node' | 'edge') => void;
  height?: number;
  layoutKey: string;
  /** lay out the sets without edges and reveal a person's edges only on hover/tap */
  edgesOnDemand?: boolean;
}

/** Cytoscape with compound nodes: people inside the boxes of the sets they belong to. */
export function GraphCanvas({ elements, onPick, height = 640, layoutKey, edgesOnDemand }: GraphProps) {
  const host = useRef<HTMLDivElement>(null);
  const cy = useRef<cytoscape.Core | null>(null);
  const pick = useRef(onPick);
  pick.current = onPick;

  useEffect(() => {
    const c = cytoscape({ container: host.current!, style: STYLE, minZoom: 0.15, maxZoom: 3 });
    c.on('tap', 'node', (e) => {
      if (e.target.isParent()) return;
      c.edges('.shown').removeClass('shown').removeClass('pinned');
      e.target.connectedEdges().addClass('shown pinned');
      pick.current?.(e.target.id(), 'node');
    });
    c.on('tap', 'edge', (e) => pick.current?.(e.target.id(), 'edge'));
    c.on('mouseover', 'node', (e) => {
      if (e.target.isParent()) return;
      const near = e.target.closedNeighborhood();
      c.elements().not(near).not(near.ancestors()).addClass('faded');
      e.target.connectedEdges().addClass('shown');
    });
    c.on('mouseout', 'node', () => { c.elements().removeClass('faded'); c.edges('.shown').not('.pinned').removeClass('shown'); });
    cy.current = c;
    return () => c.destroy();
  }, []);

  useEffect(() => {
    const c = cy.current;
    if (!c) return;
    c.batch(() => { c.elements().remove(); c.add(elements); if (edgesOnDemand) c.edges().addClass('ondemand'); });
    const big = elements.length > 500;
    (edgesOnDemand ? c.nodes() : c.elements()).layout({
      name: 'fcose', animate: false, randomize: true, quality: big ? 'draft' : 'default', nodeDimensionsIncludeLabels: true,
      packComponents: true, nodeRepulsion: 6000, idealEdgeLength: 70, nestingFactor: 0.6, gravityCompound: 1.2, tile: true,
    } as cytoscape.LayoutOptions).run();
    c.fit(undefined, 20);
  }, [layoutKey]);

  // cytoscape rewrites its container's style, so the height lives on a wrapper
  return (
    <div class="graph" style={{ height: `${height}px` }} data-nodes={elements.filter((e) => !('source' in e.data)).length}>
      <div ref={host} class="graph-host" />
    </div>
  );
}
