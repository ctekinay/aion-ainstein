import { useState, useRef, useCallback } from "react";

/* ═══════════════════════════════════════════════════════════════
   ArchiMate Interactive Viewer — Reference Template v0.2
   
   Bean-webshop accuracy + NS-viewer UX + improvements:
   - Header bar with title
   - Diagonal (direct) lines between elements
   - Draggable elements
   - Legend as filter (click to hide/show layers)
   - View-switcher, highlight/dim, side panel, zoom/pan
   - SVG export placeholder
   ═══════════════════════════════════════════════════════════════ */

// ── ArchiMate 3.1 Layer Colors ────────────────────────────────
const LAYER = {
  motivation:  { bg: "#E8D5F5", fill: "#D5B8E8", border: "#9B59B6", text: "#6C3483", label: "Motivation" },
  strategy:    { bg: "#FFF0D5", fill: "#FFE0A8", border: "#D4A024", text: "#7D6608", label: "Strategy" },
  business:    { bg: "#FFFFCC", fill: "#FFFFAA", border: "#C8C832", text: "#6B6B00", label: "Business" },
  application: { bg: "#D4F1F9", fill: "#A8E0F0", border: "#3498DB", text: "#1A5276", label: "Application" },
  technology:  { bg: "#C8E6C9", fill: "#A5D6A7", border: "#27AE60", text: "#1B5E20", label: "Technology" },
};

// ── ArchiMate 3.1 Relation Styles ─────────────────────────────
const REL_STYLES = {
  Association:    { dash: "",     color: "#666", src: "none",         tgt: "none",         label: "associated with" },
  Serving:        { dash: "",     color: "#444", src: "none",         tgt: "arrow-open",   label: "serves" },
  Composition:    { dash: "",     color: "#444", src: "diamond-fill", tgt: "none",         label: "composed of" },
  Aggregation:    { dash: "",     color: "#444", src: "diamond-open", tgt: "none",         label: "aggregates" },
  Assignment:     { dash: "",     color: "#444", src: "none",         tgt: "arrow-fill",   label: "assigned to" },
  Realization:    { dash: "6 3",  color: "#444", src: "none",         tgt: "arrow-open",   label: "realizes" },
  Triggering:     { dash: "",     color: "#444", src: "none",         tgt: "arrow-fill",   label: "triggers" },
  Flow:           { dash: "8 4",  color: "#444", src: "none",         tgt: "arrow-fill",   label: "flows to" },
  Access:         { dash: "4 3",  color: "#888", src: "none",         tgt: "arrow-open",   label: "accesses" },
  Influence:      { dash: "6 3",  color: "#9B59B6", src: "none",     tgt: "arrow-open",   label: "influences" },
  Specialization: { dash: "",     color: "#666", src: "none",         tgt: "triangle",     label: "specializes" },
};

// ── SVG Marker Definitions ────────────────────────────────────
function MarkerDefs() {
  return (
    <defs>
      <marker id="m-arrow-fill" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto-start-reverse"><polygon points="0 0, 10 3.5, 0 7" fill="#444" /></marker>
      <marker id="m-arrow-open" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto-start-reverse"><polyline points="0 0, 10 3.5, 0 7" fill="none" stroke="#444" strokeWidth="1.5" /></marker>
      <marker id="m-diamond-fill" viewBox="0 0 12 8" refX="0" refY="4" markerWidth="10" markerHeight="7" orient="auto-start-reverse"><polygon points="0 4, 6 0, 12 4, 6 8" fill="#444" /></marker>
      <marker id="m-diamond-open" viewBox="0 0 12 8" refX="0" refY="4" markerWidth="10" markerHeight="7" orient="auto-start-reverse"><polygon points="0 4, 6 0, 12 4, 6 8" fill="#fff" stroke="#444" strokeWidth="1.5" /></marker>
      <marker id="m-triangle" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><polygon points="0 0, 10 5, 0 10" fill="#fff" stroke="#666" strokeWidth="1.5" /></marker>
      <marker id="m-arrow-fill-hl" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto-start-reverse"><polygon points="0 0, 10 3.5, 0 7" fill="#E74C3C" /></marker>
      <marker id="m-arrow-open-hl" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto-start-reverse"><polyline points="0 0, 10 3.5, 0 7" fill="none" stroke="#E74C3C" strokeWidth="1.5" /></marker>
      <marker id="m-diamond-fill-hl" viewBox="0 0 12 8" refX="0" refY="4" markerWidth="10" markerHeight="7" orient="auto-start-reverse"><polygon points="0 4, 6 0, 12 4, 6 8" fill="#E74C3C" /></marker>
      <marker id="m-diamond-open-hl" viewBox="0 0 12 8" refX="0" refY="4" markerWidth="10" markerHeight="7" orient="auto-start-reverse"><polygon points="0 4, 6 0, 12 4, 6 8" fill="#fff" stroke="#E74C3C" strokeWidth="1.5" /></marker>
      <marker id="m-triangle-hl" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><polygon points="0 0, 10 5, 0 10" fill="#fff" stroke="#E74C3C" strokeWidth="1.5" /></marker>
    </defs>
  );
}

// ── ArchiMate Element Icons ───────────────────────────────────
function ArchiIcon({ type, x, y, s = 14, color = "#555" }) {
  switch (type) {
    case "Stakeholder": return <g><circle cx={x+s/2} cy={y+s*0.32} r={s*0.22} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+s/2} y1={y+s*0.54} x2={x+s/2} y2={y+s*0.78} stroke={color} strokeWidth={1.1}/><line x1={x+s*0.22} y1={y+s*0.64} x2={x+s*0.78} y2={y+s*0.64} stroke={color} strokeWidth={1.1}/><line x1={x+s/2} y1={y+s*0.78} x2={x+s*0.28} y2={y+s*0.98} stroke={color} strokeWidth={1.1}/><line x1={x+s/2} y1={y+s*0.78} x2={x+s*0.72} y2={y+s*0.98} stroke={color} strokeWidth={1.1}/></g>;
    case "Driver": return <g><rect x={x+1} y={y+s*0.15} width={s-2} height={s*0.7} rx={2} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+s*0.28} y1={y+s*0.5} x2={x+s*0.72} y2={y+s*0.5} stroke={color} strokeWidth={1}/><polygon points={`${x+s*0.65},${y+s*0.38} ${x+s*0.72},${y+s*0.5} ${x+s*0.65},${y+s*0.62}`} fill={color}/></g>;
    case "Assessment": return <g><circle cx={x+s/2} cy={y+s/2} r={s*0.42} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+s*0.32} y1={y+s*0.64} x2={x+s*0.68} y2={y+s*0.36} stroke={color} strokeWidth={1.2}/></g>;
    case "Goal": return <g><circle cx={x+s/2} cy={y+s/2} r={s*0.42} fill="none" stroke={color} strokeWidth={1.1}/><circle cx={x+s/2} cy={y+s/2} r={s*0.24} fill="none" stroke={color} strokeWidth={0.9}/><circle cx={x+s/2} cy={y+s/2} r={s*0.08} fill={color}/></g>;
    case "Outcome": return <g><circle cx={x+s/2} cy={y+s/2} r={s*0.42} fill="none" stroke={color} strokeWidth={1.1}/><polyline points={`${x+s*0.3},${y+s*0.52} ${x+s*0.44},${y+s*0.68} ${x+s*0.72},${y+s*0.34}`} fill="none" stroke={color} strokeWidth={1.3}/></g>;
    case "Principle": return <g><polygon points={`${x+s/2},${y+2} ${x+s-2},${y+s*0.42} ${x+s*0.8},${y+s-2} ${x+s*0.2},${y+s-2} ${x+2},${y+s*0.42}`} fill="none" stroke={color} strokeWidth={1.1}/></g>;
    case "Requirement": return <g><rect x={x+1} y={y+s*0.1} width={s-2} height={s*0.8} rx={2} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+s*0.25} y1={y+s*0.35} x2={x+s*0.75} y2={y+s*0.35} stroke={color} strokeWidth={0.8}/><line x1={x+s*0.25} y1={y+s*0.52} x2={x+s*0.65} y2={y+s*0.52} stroke={color} strokeWidth={0.8}/><line x1={x+s*0.25} y1={y+s*0.69} x2={x+s*0.55} y2={y+s*0.69} stroke={color} strokeWidth={0.8}/></g>;
    case "Constraint": return <g><rect x={x+1} y={y+s*0.1} width={s-2} height={s*0.8} rx={2} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+s*0.2} y1={y+s*0.35} x2={x+s*0.8} y2={y+s*0.65} stroke={color} strokeWidth={1}/></g>;
    case "Value": return <g><ellipse cx={x+s/2} cy={y+s/2} rx={s*0.44} ry={s*0.36} fill="none" stroke={color} strokeWidth={1.1}/></g>;
    case "Meaning": return <g><path d={`M${x+s*0.15},${y+s*0.5} Q${x+s*0.15},${y+s*0.15} ${x+s*0.5},${y+s*0.15} Q${x+s*0.85},${y+s*0.15} ${x+s*0.85},${y+s*0.5} Q${x+s*0.85},${y+s*0.75} ${x+s*0.5},${y+s*0.75} L${x+s*0.35},${y+s*0.92} L${x+s*0.4},${y+s*0.75} Q${x+s*0.15},${y+s*0.75} ${x+s*0.15},${y+s*0.5}Z`} fill="none" stroke={color} strokeWidth={1.1}/></g>;
    case "Capability": return <g><rect x={x+1} y={y+1} width={s-2} height={s-2} rx={2} fill="none" stroke={color} strokeWidth={1.1}/><rect x={x+s*0.55} y={y+3} width={s*0.3} height={s*0.3} rx={1} fill="none" stroke={color} strokeWidth={0.8}/></g>;
    case "Resource": return <g><rect x={x+1} y={y+1} width={s-2} height={s-2} rx={2} fill="none" stroke={color} strokeWidth={1.1}/><circle cx={x+s*0.35} cy={y+s*0.5} r={2} fill={color}/><circle cx={x+s*0.55} cy={y+s*0.5} r={2} fill={color}/><circle cx={x+s*0.75} cy={y+s*0.5} r={2} fill={color}/></g>;
    case "CourseOfAction": return <g><rect x={x+1} y={y+1} width={s-2} height={s-2} rx={s*0.4} fill="none" stroke={color} strokeWidth={1.1}/><polygon points={`${x+s*0.38},${y+s*0.28} ${x+s*0.72},${y+s*0.5} ${x+s*0.38},${y+s*0.72}`} fill={color}/></g>;
    case "ValueStream": return <g><polygon points={`${x+1},${y+s*0.2} ${x+s*0.72},${y+s*0.2} ${x+s-1},${y+s*0.5} ${x+s*0.72},${y+s*0.8} ${x+1},${y+s*0.8}`} fill="none" stroke={color} strokeWidth={1.1}/></g>;
    case "BusinessActor": return <g><circle cx={x+s/2} cy={y+s*0.25} r={s*0.18} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+s/2} y1={y+s*0.43} x2={x+s/2} y2={y+s*0.72} stroke={color} strokeWidth={1.1}/><line x1={x+s*0.22} y1={y+s*0.55} x2={x+s*0.78} y2={y+s*0.55} stroke={color} strokeWidth={1.1}/><line x1={x+s/2} y1={y+s*0.72} x2={x+s*0.28} y2={y+s*0.95} stroke={color} strokeWidth={1.1}/><line x1={x+s/2} y1={y+s*0.72} x2={x+s*0.72} y2={y+s*0.95} stroke={color} strokeWidth={1.1}/></g>;
    case "BusinessRole": return <g><ellipse cx={x+s/2} cy={y+s/2} rx={s*0.44} ry={s*0.32} fill="none" stroke={color} strokeWidth={1.1}/></g>;
    case "BusinessService": return <g><rect x={x+1} y={y+s*0.18} width={s-2} height={s*0.64} rx={s*0.32} fill="none" stroke={color} strokeWidth={1.1}/></g>;
    case "BusinessProcess": return <g><polygon points={`${x+1},${y+s*0.18} ${x+s*0.68},${y+s*0.18} ${x+s-1},${y+s*0.5} ${x+s*0.68},${y+s*0.82} ${x+1},${y+s*0.82}`} fill="none" stroke={color} strokeWidth={1.1}/></g>;
    case "BusinessObject": return <g><rect x={x+1} y={y+1} width={s-2} height={s-2} rx={1} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+1} y1={y+s*0.32} x2={x+s-1} y2={y+s*0.32} stroke={color} strokeWidth={0.8}/></g>;
    case "BusinessInterface": return <g><circle cx={x+s/2} cy={y+s*0.38} r={s*0.28} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+s/2} y1={y+s*0.66} x2={x+s/2} y2={y+s*0.95} stroke={color} strokeWidth={1.1}/></g>;
    case "BusinessEvent": return <g><path d={`M${x+1},${y+s*0.2} L${x+s*0.65},${y+s*0.2} Q${x+s-1},${y+s*0.5} ${x+s*0.65},${y+s*0.8} L${x+1},${y+s*0.8} Q${x+s*0.25},${y+s*0.5} ${x+1},${y+s*0.2}Z`} fill="none" stroke={color} strokeWidth={1.1}/></g>;
    case "BusinessFunction": return <g><rect x={x+1} y={y+s*0.18} width={s-2} height={s*0.64} rx={2} fill="none" stroke={color} strokeWidth={1.1}/><text x={x+s/2} y={y+s*0.6} textAnchor="middle" fontSize={s*0.55} fill={color} fontWeight={700} fontStyle="italic">f</text></g>;
    case "Contract": return <g><rect x={x+1} y={y+1} width={s-2} height={s-2} rx={1} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+1} y1={y+s*0.32} x2={x+s-1} y2={y+s*0.32} stroke={color} strokeWidth={0.8}/><line x1={x+1} y1={y+s*0.52} x2={x+s-1} y2={y+s*0.52} stroke={color} strokeWidth={0.8}/></g>;
    case "Product": return <g><rect x={x+1} y={y+1} width={s-2} height={s-2} rx={1} fill="none" stroke={color} strokeWidth={1.1}/><rect x={x+s*0.15} y={y+1} width={s*0.3} height={s*0.22} rx={1} fill="none" stroke={color} strokeWidth={0.8}/></g>;
    case "ApplicationComponent": return <g><rect x={x+3} y={y+1} width={s-4} height={s-2} rx={1} fill="none" stroke={color} strokeWidth={1.1}/><rect x={x} y={y+s*0.22} width={s*0.28} height={s*0.18} rx={1} fill="none" stroke={color} strokeWidth={0.9}/><rect x={x} y={y+s*0.52} width={s*0.28} height={s*0.18} rx={1} fill="none" stroke={color} strokeWidth={0.9}/></g>;
    case "ApplicationService": return <g><rect x={x+1} y={y+s*0.18} width={s-2} height={s*0.64} rx={s*0.32} fill="none" stroke={color} strokeWidth={1.1}/></g>;
    case "ApplicationInterface": return <g><circle cx={x+s/2} cy={y+s*0.38} r={s*0.28} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+s/2} y1={y+s*0.66} x2={x+s/2} y2={y+s*0.95} stroke={color} strokeWidth={1.1}/></g>;
    case "ApplicationFunction": return <g><rect x={x+1} y={y+s*0.18} width={s-2} height={s*0.64} rx={2} fill="none" stroke={color} strokeWidth={1.1}/><text x={x+s/2} y={y+s*0.6} textAnchor="middle" fontSize={s*0.55} fill={color} fontWeight={700} fontStyle="italic">f</text></g>;
    case "DataObject": return <g><rect x={x+1} y={y+1} width={s-2} height={s-2} rx={1} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+1} y1={y+s*0.32} x2={x+s-1} y2={y+s*0.32} stroke={color} strokeWidth={0.8}/></g>;
    case "Node": return <g><rect x={x+1} y={y+4} width={s-5} height={s-5} fill="none" stroke={color} strokeWidth={1.1}/><polyline points={`${x+1},${y+4} ${x+4},${y+1} ${x+s-1},${y+1} ${x+s-1},${y+s-4} ${x+s-5},${y+s-1}`} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+s-1} y1={y+1} x2={x+s-5} y2={y+4} stroke={color} strokeWidth={1.1}/></g>;
    case "SystemSoftware": return <g><circle cx={x+s/2} cy={y+s/2} r={s*0.42} fill="none" stroke={color} strokeWidth={1.1}/><circle cx={x+s/2} cy={y+s/2} r={s*0.22} fill="none" stroke={color} strokeWidth={0.8}/></g>;
    case "Artifact": return <g><rect x={x+1} y={y+1} width={s-2} height={s-2} rx={1} fill="none" stroke={color} strokeWidth={1.1}/><polyline points={`${x+s*0.6},${y+1} ${x+s*0.6},${y+s*0.32} ${x+s-1},${y+s*0.32}`} fill="none" stroke={color} strokeWidth={0.9}/></g>;
    case "CommunicationNetwork": return <g><line x1={x+2} y1={y+s/2} x2={x+s-2} y2={y+s/2} stroke={color} strokeWidth={1.2}/><circle cx={x+3} cy={y+s/2} r={2.5} fill={color}/><circle cx={x+s/2} cy={y+s/2} r={2.5} fill={color}/><circle cx={x+s-3} cy={y+s/2} r={2.5} fill={color}/></g>;
    case "Device": return <g><rect x={x+1} y={y+2} width={s-2} height={s-5} rx={2} fill="none" stroke={color} strokeWidth={1.1}/><line x1={x+s*0.3} y1={y+s-3} x2={x+s*0.7} y2={y+s-3} stroke={color} strokeWidth={1.1}/><line x1={x+s*0.2} y1={y+s-1} x2={x+s*0.8} y2={y+s-1} stroke={color} strokeWidth={1.1}/></g>;
    case "TechnologyService": return <g><rect x={x+1} y={y+s*0.18} width={s-2} height={s*0.64} rx={s*0.32} fill="none" stroke={color} strokeWidth={1.1}/></g>;
    default: return <rect x={x+1} y={y+1} width={s-2} height={s-2} rx={2} fill="none" stroke={color} strokeWidth={1}/>;
  }
}

// ══════════════════════════════════════════════════════════════
//  SAMPLE DATA — Bean Webshop
// ══════════════════════════════════════════════════════════════

const INITIAL_VIEWS = {
  overview: {
    label: "Business Overview",
    elements: [
      { id: "g1", name: "Healthier Food for Everybody", type: "Goal", layer: "motivation", x: 40, y: 30, w: 220, h: 54, doc: "Primary mission: provide healthy bean products to consumers." },
      { id: "g2", name: "Profit Sharing — Plant a Tree", type: "Goal", layer: "motivation", x: 300, y: 30, w: 220, h: 54, doc: "Social responsibility: share profits with environmental foundation." },
      { id: "st1", name: "Customer", type: "Stakeholder", layer: "motivation", x: 560, y: 20, w: 160, h: 50, doc: "End consumer purchasing beans via the webshop." },
      { id: "st2", name: "Plant a Tree Foundation", type: "Stakeholder", layer: "motivation", x: 560, y: 78, w: 180, h: 50, doc: "Environmental partner receiving profit shares." },
      { id: "d1", name: "E-commerce Automation", type: "Driver", layer: "motivation", x: 780, y: 20, w: 180, h: 50, doc: "Drive towards automated online sales and fulfillment." },
      { id: "d2", name: "Open Source Preference", type: "Driver", layer: "motivation", x: 780, y: 78, w: 180, h: 50, doc: "Strategic preference for open source software." },
      { id: "c1", name: "Sales", type: "Capability", layer: "strategy", x: 40, y: 172, w: 150, h: 50, doc: "Capability to sell beans through automated webshop." },
      { id: "c2", name: "Marketing", type: "Capability", layer: "strategy", x: 210, y: 172, w: 150, h: 50, doc: "Capability to promote bean products." },
      { id: "c3", name: "Logistics", type: "Capability", layer: "strategy", x: 380, y: 172, w: 150, h: 50, doc: "Capability to manage shipping via PostNL." },
      { id: "c4", name: "Payments", type: "Capability", layer: "strategy", x: 550, y: 172, w: 150, h: 50, doc: "Capability to process Dutch payments." },
      { id: "c5", name: "Aftercare", type: "Capability", layer: "strategy", x: 720, y: 172, w: 150, h: 50, doc: "Capability to handle customer complaints." },
      { id: "ba1", name: "Laurent", type: "BusinessActor", layer: "business", x: 40, y: 286, w: 160, h: 54, doc: "Owner, director and operator of the bean webshop." },
      { id: "br1", name: "Director", type: "BusinessRole", layer: "business", x: 230, y: 278, w: 140, h: 44, doc: "Strategic role: business decisions and partnerships." },
      { id: "br2", name: "Operator", type: "BusinessRole", layer: "business", x: 230, y: 328, w: 140, h: 44, doc: "Operational role: day-to-day webshop management." },
      { id: "ba2", name: "PostNL", type: "BusinessActor", layer: "business", x: 420, y: 286, w: 150, h: 50, doc: "External logistics partner for package delivery." },
      { id: "ba3", name: "UnitedCustomerServices", type: "BusinessActor", layer: "business", x: 600, y: 286, w: 200, h: 50, doc: "External partner handling customer complaints." },
      { id: "bs1", name: "Online Sales Service", type: "BusinessService", layer: "business", x: 40, y: 400, w: 180, h: 48, doc: "Service: browse and purchase beans online." },
      { id: "bs2", name: "Shipping Service", type: "BusinessService", layer: "business", x: 250, y: 400, w: 160, h: 48, doc: "Service: deliver orders to customers." },
      { id: "bs3", name: "Complaint Handling", type: "BusinessService", layer: "business", x: 440, y: 400, w: 170, h: 48, doc: "Service: resolve customer issues." },
      { id: "bs4", name: "Payment Processing", type: "BusinessService", layer: "business", x: 640, y: 400, w: 170, h: 48, doc: "Service: process iDEAL and Dutch payments." },
      { id: "bo1", name: "Order", type: "BusinessObject", layer: "business", x: 40, y: 476, w: 120, h: 46, doc: "A customer order with items and delivery address." },
      { id: "bo2", name: "Customer Data", type: "BusinessObject", layer: "business", x: 175, y: 476, w: 130, h: 46, doc: "Customer contact and preference information." },
      { id: "bo3", name: "Payment", type: "BusinessObject", layer: "business", x: 320, y: 476, w: 120, h: 46, doc: "Payment transaction record." },
      { id: "bo4", name: "Shipment", type: "BusinessObject", layer: "business", x: 455, y: 476, w: 120, h: 46, doc: "Package shipment tracking record." },
      { id: "bo5", name: "Complaint", type: "BusinessObject", layer: "business", x: 590, y: 476, w: 120, h: 46, doc: "Customer complaint or issue record." },
      { id: "bo6", name: "Product Catalog", type: "BusinessObject", layer: "business", x: 725, y: 476, w: 140, h: 46, doc: "Available bean products with pricing." },
      { id: "ac1", name: "Open Source Webshop", type: "ApplicationComponent", layer: "application", x: 40, y: 576, w: 200, h: 56, doc: "WooCommerce/PrestaShop — handles storefront, cart, checkout." },
      { id: "ac2", name: "Dutch Payment Gateway", type: "ApplicationComponent", layer: "application", x: 280, y: 576, w: 200, h: 56, doc: "Mollie/Adyen — processes iDEAL and Dutch payment methods." },
      { id: "ai1", name: "PostNL REST API", type: "ApplicationInterface", layer: "application", x: 520, y: 576, w: 160, h: 50, doc: "REST interface for shipping label creation and tracking." },
      { id: "ai2", name: "UCS REST API", type: "ApplicationInterface", layer: "application", x: 710, y: 576, w: 160, h: 50, doc: "REST interface for complaint ticket management." },
      { id: "do1", name: "Order DB", type: "DataObject", layer: "application", x: 80, y: 656, w: 120, h: 44, doc: "Persistent storage of orders and line items." },
      { id: "do2", name: "Customer DB", type: "DataObject", layer: "application", x: 230, y: 656, w: 120, h: 44, doc: "Customer accounts and profiles." },
      { id: "do3", name: "Product DB", type: "DataObject", layer: "application", x: 380, y: 656, w: 120, h: 44, doc: "Bean product catalog with stock levels." },
    ],
    relations: [
      { from: "g1", to: "st1", type: "Association" }, { from: "g2", to: "st2", type: "Association" },
      { from: "d1", to: "g1", type: "Influence" }, { from: "d2", to: "g1", type: "Influence" },
      { from: "c1", to: "g1", type: "Realization" }, { from: "c3", to: "g1", type: "Realization" },
      { from: "c4", to: "g1", type: "Realization" }, { from: "c5", to: "g2", type: "Realization" },
      { from: "ba1", to: "br1", type: "Assignment" }, { from: "ba1", to: "br2", type: "Assignment" },
      { from: "br2", to: "bs1", type: "Serving" }, { from: "ba2", to: "bs2", type: "Serving" },
      { from: "ba3", to: "bs3", type: "Serving" }, { from: "br2", to: "bs4", type: "Serving" },
      { from: "bs1", to: "bo1", type: "Access" }, { from: "bs1", to: "bo2", type: "Access" },
      { from: "bs1", to: "bo6", type: "Access" }, { from: "bs2", to: "bo4", type: "Access" },
      { from: "bs3", to: "bo5", type: "Access" }, { from: "bs4", to: "bo3", type: "Access" },
      { from: "ac1", to: "bs1", type: "Realization" }, { from: "ac2", to: "bs4", type: "Realization" },
      { from: "ai1", to: "bs2", type: "Realization" }, { from: "ai2", to: "bs3", type: "Realization" },
      { from: "ac1", to: "do1", type: "Access" }, { from: "ac1", to: "do2", type: "Access" },
      { from: "ac1", to: "do3", type: "Access" },
    ],
  },
};

// ══════════════════════════════════════════════════════════════
//  MAIN COMPONENT
// ══════════════════════════════════════════════════════════════

export default function ArchiMateViewer() {
  const [activeView, setActiveView] = useState(Object.keys(INITIAL_VIEWS)[0]);
  const [selected, setSelected] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 20, y: 10 });
  const [hiddenLayers, setHiddenLayers] = useState(new Set());
  const [positions, setPositions] = useState(() => {
    const pos = {};
    Object.values(INITIAL_VIEWS).forEach(v => v.elements.forEach(e => { pos[e.id] = { x: e.x, y: e.y }; }));
    return pos;
  });
  const dragging = useRef(null); // null or { type: "pan" | "element", id?, startX, startY, origX, origY }
  const svgRef = useRef(null);

  const view = INITIAL_VIEWS[activeView];
  const els = view.elements.filter(e => !hiddenLayers.has(e.layer)).map(e => ({ ...e, x: positions[e.id]?.x ?? e.x, y: positions[e.id]?.y ?? e.y }));
  const elMap = Object.fromEntries(els.map(e => [e.id, e]));
  const visibleIds = new Set(els.map(e => e.id));
  const rels = view.relations.filter(r => visibleIds.has(r.from) && visibleIds.has(r.to));

  const relatedIds = selected
    ? new Set([selected, ...rels.filter(r => r.from === selected || r.to === selected).flatMap(r => [r.from, r.to])])
    : null;
  const selectedEl = selected ? elMap[selected] : null;
  const selectedRels = selected ? rels.filter(r => r.from === selected || r.to === selected) : [];

  // Layer bounds
  const layers = ["motivation", "strategy", "business", "application", "technology"];
  const layerBounds = {};
  layers.forEach(l => {
    const le = els.filter(e => e.layer === l);
    if (!le.length) return;
    layerBounds[l] = { y: Math.min(...le.map(e => e.y)) - 20, h: Math.max(...le.map(e => e.y + e.h)) - Math.min(...le.map(e => e.y)) + 34 };
  });
  const canvasW = Math.max(980, ...els.map(e => e.x + e.w + 40));

  // Mouse handlers: pan + element drag
  const onMouseDown = useCallback((e) => {
    const elId = e.target.closest("[data-el]")?.dataset.el;
    if (elId) {
      e.stopPropagation();
      const pos = positions[elId] || { x: 0, y: 0 };
      dragging.current = { type: "element", id: elId, startX: e.clientX, startY: e.clientY, origX: pos.x, origY: pos.y };
    } else {
      dragging.current = { type: "pan", startX: e.clientX - pan.x, startY: e.clientY - pan.y };
    }
  }, [pan, positions]);

  const onMouseMove = useCallback((e) => {
    if (!dragging.current) return;
    if (dragging.current.type === "pan") {
      setPan({ x: e.clientX - dragging.current.startX, y: e.clientY - dragging.current.startY });
    } else if (dragging.current.type === "element") {
      const dx = (e.clientX - dragging.current.startX) / zoom;
      const dy = (e.clientY - dragging.current.startY) / zoom;
      setPositions(prev => ({ ...prev, [dragging.current.id]: { x: dragging.current.origX + dx, y: dragging.current.origY + dy } }));
    }
  }, [zoom]);

  const onMouseUp = useCallback(() => { dragging.current = null; }, []);

  const onWheel = useCallback((e) => {
    e.preventDefault();
    setZoom(z => Math.max(0.25, Math.min(3, z + (e.deltaY > 0 ? -0.08 : 0.08))));
  }, []);

  // Diagonal line (direct connection between element edges)
  function linePath(fromId, toId) {
    const f = elMap[fromId], t = elMap[toId];
    if (!f || !t) return "";
    const fcx = f.x + f.w / 2, fcy = f.y + f.h / 2;
    const tcx = t.x + t.w / 2, tcy = t.y + t.h / 2;
    // Find edge intersection points
    const fx = fcx + Math.max(-f.w/2, Math.min(f.w/2, (tcx - fcx) * f.h / (2 * Math.max(1, Math.abs(tcy - fcy))))) ;
    const fy = fcy + Math.max(-f.h/2, Math.min(f.h/2, (tcy - fcy) * f.w / (2 * Math.max(1, Math.abs(tcx - fcx)))));
    // Simplified: connect from center to center, the markers handle the visual
    return `M${fcx},${fcy} L${tcx},${tcy}`;
  }

  // Toggle layer visibility
  function toggleLayer(layer) {
    setHiddenLayers(prev => {
      const next = new Set(prev);
      if (next.has(layer)) next.delete(layer); else next.add(layer);
      return next;
    });
    if (selected && elMap[selected]?.layer === layer) setSelected(null);
  }

  // SVG export placeholder
  function handleExportSVG() {
    alert("SVG export — placeholder. Will use <text> elements instead of foreignObject for compatibility.");
  }

  // All layers present in this view (for legend)
  const viewLayers = [...new Set(view.elements.map(e => e.layer))].sort((a, b) => layers.indexOf(a) - layers.indexOf(b));

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui, -apple-system, sans-serif", background: "#F8F9FA", overflow: "hidden" }}>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

        {/* Header bar */}
        <div style={{ padding: "10px 16px", background: "#2C3E50", color: "#fff", display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: "0.3px" }}>ArchiMate Viewer</div>
          <div style={{ fontSize: 11, opacity: 0.7 }}>—</div>
          <div style={{ fontSize: 12, opacity: 0.85 }}>{view.label}</div>
        </div>

        {/* Toolbar: view switcher + zoom + export */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", background: "#fff", borderBottom: "1px solid #E5E7EB", flexShrink: 0 }}>
          {Object.entries(INITIAL_VIEWS).map(([key, v]) => (
            <button key={key} onClick={() => { setActiveView(key); setSelected(null); setPan({ x: 20, y: 10 }); setZoom(1); setHiddenLayers(new Set()); }}
              style={{
                padding: "4px 12px", borderRadius: 4, border: activeView === key ? "1px solid #2C3E50" : "1px solid #D1D5DB",
                background: activeView === key ? "#2C3E50" : "#fff",
                color: activeView === key ? "#fff" : "#374151",
                fontSize: 11, fontWeight: 600, cursor: "pointer",
              }}>{v.label}</button>
          ))}
          <div style={{ flex: 1 }} />
          {[{ l: "−", fn: () => setZoom(z => Math.max(0.25, z * 0.8)) },
            { l: "↺", fn: () => { setZoom(1); setPan({ x: 20, y: 10 }); } },
            { l: "+", fn: () => setZoom(z => Math.min(3, z * 1.2)) },
          ].map(({ l, fn }) => (
            <button key={l} onClick={fn} style={{
              width: 26, height: 26, borderRadius: 4, border: "1px solid #D1D5DB",
              background: "#fff", cursor: "pointer", fontSize: 13, fontWeight: 700, color: "#6B7280",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>{l}</button>
          ))}
          <div style={{ width: 1, height: 18, background: "#E5E7EB", margin: "0 2px" }} />
          <button onClick={handleExportSVG} style={{
            padding: "4px 10px", borderRadius: 4, border: "1px solid #D1D5DB",
            background: "#fff", cursor: "pointer", fontSize: 10, fontWeight: 600, color: "#374151",
          }}>↓ SVG</button>
        </div>

        {/* SVG canvas */}
        <div style={{ flex: 1, overflow: "hidden", cursor: dragging.current?.type === "pan" ? "grabbing" : "grab" }}
          onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp} onMouseLeave={onMouseUp}
          onWheel={onWheel}>
          <svg ref={svgRef} width="100%" height="100%">
            <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
              <MarkerDefs />
              {Object.entries(layerBounds).map(([l, b]) => (
                <g key={l}>
                  <rect x={-10} y={b.y} width={canvasW + 20} height={b.h} rx={6} fill={LAYER[l].bg} opacity={0.3} stroke={LAYER[l].border} strokeWidth={0.5} strokeDasharray="4 2" />
                  <text x={0} y={b.y + 13} fontSize={9.5} fontWeight={700} fill={LAYER[l].text} opacity={0.6} fontFamily="system-ui, sans-serif" style={{ textTransform: "uppercase", letterSpacing: "0.8px" }}>{LAYER[l].label}</text>
                </g>
              ))}
              {rels.map((r, i) => {
                const st = REL_STYLES[r.type] || REL_STYLES.Association;
                const isActive = relatedIds && (r.from === selected || r.to === selected);
                const dimmed = relatedIds && !isActive;
                const hl = isActive ? "-hl" : "";
                return (
                  <line key={i}
                    x1={elMap[r.from] ? elMap[r.from].x + elMap[r.from].w / 2 : 0}
                    y1={elMap[r.from] ? elMap[r.from].y + elMap[r.from].h / 2 : 0}
                    x2={elMap[r.to] ? elMap[r.to].x + elMap[r.to].w / 2 : 0}
                    y2={elMap[r.to] ? elMap[r.to].y + elMap[r.to].h / 2 : 0}
                    stroke={isActive ? "#E74C3C" : st.color}
                    strokeWidth={isActive ? 2 : 1.2}
                    strokeDasharray={st.dash}
                    opacity={dimmed ? 0.1 : 1}
                    markerEnd={st.tgt !== "none" ? `url(#m-${st.tgt}${hl})` : undefined}
                    markerStart={st.src !== "none" ? `url(#m-${st.src}${hl})` : undefined}
                  />
                );
              })}
              {els.map(el => {
                const pal = LAYER[el.layer];
                const isSel = selected === el.id;
                const dimmed = relatedIds && !relatedIds.has(el.id);
                return (
                  <g key={el.id} data-el={el.id} style={{ cursor: "grab" }}
                    onClick={e => { e.stopPropagation(); setSelected(isSel ? null : el.id); }}>
                    <rect x={el.x} y={el.y} width={el.w} height={el.h} rx={4}
                      fill={isSel ? "#FFF9E6" : pal.fill}
                      stroke={isSel ? "#E74C3C" : pal.border}
                      strokeWidth={isSel ? 2.5 : 1.2}
                      opacity={dimmed ? 0.12 : 1} />
                    <g opacity={dimmed ? 0.12 : 1}>
                      <ArchiIcon type={el.type} x={el.x + el.w - 20} y={el.y + 4} s={15} color={pal.text} />
                    </g>
                    <foreignObject x={el.x + 6} y={el.y + 4} width={el.w - 28} height={el.h - 8}>
                      <div xmlns="http://www.w3.org/1999/xhtml" style={{
                        fontSize: 11, fontWeight: 600, color: "#1a1a2e", lineHeight: 1.28,
                        opacity: dimmed ? 0.12 : 1, overflow: "hidden",
                        fontFamily: "system-ui, -apple-system, sans-serif",
                      }}>{el.name}</div>
                    </foreignObject>
                  </g>
                );
              })}
            </g>
          </svg>
        </div>

        {/* Legend (clickable to filter layers) */}
        <div style={{
          display: "flex", alignItems: "center", gap: 4, padding: "6px 12px",
          background: "#fff", borderTop: "1px solid #E5E7EB", fontSize: 10, flexShrink: 0, flexWrap: "wrap",
        }}>
          {viewLayers.map(l => {
            const isHidden = hiddenLayers.has(l);
            return (
              <button key={l} onClick={() => toggleLayer(l)} style={{
                display: "flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 3,
                border: "1px solid " + (isHidden ? "#E5E7EB" : LAYER[l].border),
                background: isHidden ? "#F3F4F6" : "#fff",
                cursor: "pointer", opacity: isHidden ? 0.45 : 1, transition: "all 0.15s",
              }}>
                <span style={{
                  width: 10, height: 10, background: isHidden ? "#D1D5DB" : LAYER[l].fill,
                  border: `1px solid ${isHidden ? "#9CA3AF" : LAYER[l].border}`,
                  borderRadius: 2, display: "inline-block",
                }} />
                <span style={{ fontWeight: 600, color: isHidden ? "#9CA3AF" : LAYER[l].text, fontSize: 10 }}>{LAYER[l].label}</span>
              </button>
            );
          })}
          <span style={{ color: "#9CA3AF", marginLeft: "auto", fontSize: 9.5 }}>Click layer to toggle · Drag elements to reposition · Scroll to zoom</span>
        </div>
      </div>

      {/* Side panel */}
      {selectedEl && (
        <div style={{
          width: 300, borderLeft: "1px solid #E5E7EB", background: "#fff", padding: "16px 18px",
          overflowY: "auto", flexShrink: 0,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 9, fontWeight: 700, color: LAYER[selectedEl.layer].text, textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 3 }}>
                {selectedEl.type.replace(/([A-Z])/g, " $1").trim()}
              </div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#111827", lineHeight: 1.3 }}>{selectedEl.name}</div>
            </div>
            <button onClick={() => setSelected(null)} style={{
              background: "none", border: "none", cursor: "pointer", fontSize: 16, color: "#9CA3AF", padding: "2px 4px",
            }}>✕</button>
          </div>
          {selectedEl.doc && <div style={{ fontSize: 12, color: "#4B5563", lineHeight: 1.55, marginBottom: 16 }}>{selectedEl.doc}</div>}
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 10px",
            background: LAYER[selectedEl.layer].bg, borderRadius: 4, fontSize: 10, fontWeight: 600,
            color: LAYER[selectedEl.layer].text, marginBottom: 16,
          }}>
            <span style={{ width: 8, height: 8, background: LAYER[selectedEl.layer].fill, border: `1px solid ${LAYER[selectedEl.layer].border}`, borderRadius: 2 }} />
            {LAYER[selectedEl.layer].label} Layer
          </div>
          {selectedRels.length > 0 && (
            <>
              <div style={{ fontSize: 10, fontWeight: 700, color: "#374151", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.5px" }}>Relations ({selectedRels.length})</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {selectedRels.map((r, i) => {
                  const isSource = r.from === selected;
                  const other = elMap[isSource ? r.to : r.from];
                  const rs = REL_STYLES[r.type] || REL_STYLES.Association;
                  if (!other) return null;
                  return (
                    <div key={i} onClick={() => setSelected(other.id)} style={{
                      padding: "7px 10px", borderRadius: 5, border: "1px solid #F3F4F6",
                      cursor: "pointer", fontSize: 11, background: "#FAFBFC",
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = "#F0F4FF"}
                    onMouseLeave={e => e.currentTarget.style.background = "#FAFBFC"}>
                      <span style={{ color: "#9CA3AF", fontSize: 10 }}>{isSource ? "→" : "←"} {rs.label}</span>
                      <div style={{ fontWeight: 600, color: "#1F2937", marginTop: 2 }}>{other.name}</div>
                      <div style={{ fontSize: 9.5, color: LAYER[other.layer].text, marginTop: 1 }}>
                        {other.type.replace(/([A-Z])/g, " $1").trim()} · {LAYER[other.layer].label}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
