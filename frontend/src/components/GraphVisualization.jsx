import React, { useEffect, useMemo, useState } from 'react';
import { SigmaContainer, ControlsContainer, ZoomControl, FullScreenControl, useSigma, useRegisterEvents } from '@react-sigma/core';
import { useLayoutForceAtlas2 } from '@react-sigma/layout-forceatlas2';
import Graph from 'graphology';
import { EdgeArrowProgram, NodeCircleProgram } from 'sigma/rendering';
import { NodeBorderProgram } from '@sigma/node-border';
import { createEdgeCurveProgram } from '@sigma/edge-curve';

import '@react-sigma/core/lib/style.css';

// Styling Configuration matches URAxLaws
const SCHEMA_STYLING = {
  Document: { color: '#5bfff7', size: 16 },
  Article: { color: '#d3b9ff', size: 10 },
  Clause: { color: '#c3b345', size: 9 },
  Point: { color: '#ff8999', size: 8 },
  Span: { color: '#d2eecf', size: 12 },
  LegalConcept: { color: '#ffbccb', size: 12 },
  Penalty: { color: '#e1ab23', size: 15 },
  Event: { color: '#b5e6fe', size: 12 },
  Actor: { color: '#9bb273', size: 12 },
  Default: { color: '#7f8c8d', size: 10 },
};

const EDGE_COLORS = {
  ALLOWS: '#e3abb5ff',
  BELONGS_TO: '#eeb0a1ff',
  DEFINES: '#92cca9ff',
  HAS_ARTICLE: '#C4C1D9',
  HAS_CLAUSE: '#A9C6D9',
  HAS_PENALTY: '#f9df78ff',
  HAS_POINT: '#bfd594ff',
  INVOLVES: '#F2D9D0',
  MENTIONS: '#F2E8C6',
  PENALIZES: '#B0D1D9',
  PROHIBITS: '#A65A53',
  REFERENCES: '#80c3efff',
  REGULATES: '#99BFAD',
  Default: '#cccccc'
};


const generateSmartLabel = (node) => {
  const type = node.type;
  const props = node.properties || {};
  switch (type) {
    case 'Document': return props.doc_number || `Luật ${props.doc_key}`;
    case 'Article': return `Điều ${props.no}`;
    case 'Clause': return `Khoản ${props.no}`;
    case 'Point': return `Điểm ${props.no}`;
    case 'LegalConcept':
    case 'Event':
    case 'Actor': return props.name || props.name_norm;
    case 'Penalty': return props.p_type || `Phạt ${props.amount_max}`;
    case 'Span': return props.content ? props.content.substring(0, 20) + '...' : 'Text';
    default: return node.label || type;
  }
};

// Sub-component to run ForceAtlas2 Layout automatically
const ForceLayout = () => {
  const { assign } = useLayoutForceAtlas2();
  useEffect(() => {
    assign({
      settings: {
        barnesHutOptimize: false,
        strongGravityMode: false,
        gravity: 0.05,
        scalingRatio: 8,
        slowDown: 1.5,
      },
      iterations: 150
    });
  }, [assign]);
  return null;
};

// Graph interactions (Hover, Drag)
const GraphEvents = ({ setHoveredNode }) => {
  const registerEvents = useRegisterEvents();
  const sigma = useSigma();
  const [draggedNode, setDraggedNode] = useState(null);

  useEffect(() => {
    registerEvents({
      enterNode: (e) => setHoveredNode(e.node),
      leaveNode: () => setHoveredNode(null),
      downNode: (e) => {
        setDraggedNode(e.node);
        sigma.getGraph().setNodeAttribute(e.node, 'highlighted', true);
      },
      mousemovebody: (e) => {
        if (!draggedNode) return;
        const pos = sigma.viewportToGraph(e);
        sigma.getGraph().setNodeAttribute(draggedNode, 'x', pos.x);
        sigma.getGraph().setNodeAttribute(draggedNode, 'y', pos.y);
        e.preventSigmaDefault();
        e.original.preventDefault();
        e.original.stopPropagation();
      },
      mouseup: () => {
        if (draggedNode) {
          setDraggedNode(null);
          sigma.getGraph().removeNodeAttribute(draggedNode, 'highlighted');
        }
      },
      mousedown: (e) => {
        if (!sigma.getCustomBBox()) sigma.setCustomBBox(sigma.getBBox());
      }
    });
  }, [registerEvents, sigma, draggedNode, setHoveredNode]);

  return null;
};

const GraphVisualization = ({ graphData }) => {
  const [hoveredNode, setHoveredNode] = useState(null);

  const graph = useMemo(() => {
    const g = new Graph();
    if (!graphData || !graphData.nodes) return g;

    graphData.nodes.forEach((node) => {
      const type = node.type || 'Default';
      const style = SCHEMA_STYLING[type] || SCHEMA_STYLING.Default;
      const label = generateSmartLabel(node);

      if (!g.hasNode(String(node.id))) {
        g.addNode(String(node.id), {
          x: Math.random() * 100,
          y: Math.random() * 100,
          size: style.size,
          label: label,
          color: style.color,
          type: 'default', // Using NodeBorderProgram for everything
          properties: node.properties || {},
          nodeType: type
        });
      }
    });

    graphData.edges.forEach((edge, idx) => {
      const source = String(edge.source || edge.from);
      const target = String(edge.target || edge.to);
      const edgeId = edge.id ? String(edge.id) : `e${idx}`;
      const label = edge.label || edge.relationship || '';

      if (g.hasNode(source) && g.hasNode(target) && !g.hasEdge(source, target)) {
        g.addEdgeWithKey(edgeId, source, target, {
          size: 2,
          color: EDGE_COLORS[label] || EDGE_COLORS.Default,
          label: label,
          type: 'arrow'
        });
      }
    });

    return g;
  }, [graphData]);

  const sigmaSettings = useMemo(() => ({
    allowInvalidContainer: true,
    renderEdgeLabels: true,
    defaultNodeType: 'default',
    defaultEdgeType: 'arrow',
    nodeProgramClasses: {
      default: NodeBorderProgram,
      circle: NodeCircleProgram
    },
    edgeProgramClasses: {
      arrow: EdgeArrowProgram,
      curvedArrow: createEdgeCurveProgram()
    },
    labelRenderedSizeThreshold: 10,
    labelSize: 11,
    edgeLabelSize: 9
  }), []);

  if (!graphData || !graphData.nodes || graphData.nodes.length === 0) {
    return <div className="text-center text-slate-500 py-10 font-medium">Không có dữ liệu đồ thị để hiển thị</div>;
  }

  return (
    <div className="relative w-full h-full min-h-[500px] border border-slate-200 shadow-xl overflow-hidden bg-white/50 backdrop-blur-sm rounded-3xl" style={{ isolation: 'isolate' }}>
      <SigmaContainer graph={graph} settings={sigmaSettings} className="w-full h-full bg-slate-50/50">
        <ForceLayout />
        <GraphEvents setHoveredNode={setHoveredNode} />

        <ControlsContainer position={"bottom-right"} className="p-3 !bottom-4 !right-4 z-10 flex flex-col gap-2">
          <ZoomControl className="bg-white/80 backdrop-blur-md rounded-xl shadow-lg border border-slate-200 [&_button]:p-2 [&_button]:hover:bg-slate-100 transition-colors" />
          <FullScreenControl className="bg-white/80 backdrop-blur-md rounded-xl shadow-lg border border-slate-200 [&_button]:p-2 [&_button]:hover:bg-slate-100 transition-colors" />
        </ControlsContainer>

        {hoveredNode && graph.hasNode(hoveredNode) && (
          <div className="absolute top-6 left-6 bg-white/95 backdrop-blur-xl p-5 rounded-2xl shadow-2xl border border-slate-100 max-w-sm pointer-events-none z-50 transition-all duration-200 ease-out">
            <h3 className="font-bold text-slate-800 mb-3 border-b border-slate-100 pb-2 text-lg">
              {graph.getNodeAttribute(hoveredNode, 'label')}
            </h3>
            <div className="text-sm text-slate-600 space-y-2">
              <p><span className="font-semibold text-slate-700 bg-slate-100 px-2 py-1 rounded-md">Type: {graph.getNodeAttribute(hoveredNode, 'nodeType')}</span></p>
              <div className="mt-3 pt-2">
                {Object.entries(graph.getNodeAttribute(hoveredNode, 'properties')).slice(0, 5).map(([k, v]) => (
                  <p key={k} className="truncate tracking-tight"><span className="font-medium text-slate-500 capitalize">{k}:</span> <span className="text-slate-700">{String(v)}</span></p>
                ))}
              </div>
            </div>
          </div>
        )}
      </SigmaContainer>
    </div>
  );
};

export default GraphVisualization;