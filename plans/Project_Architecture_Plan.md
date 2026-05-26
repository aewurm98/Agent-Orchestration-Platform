# **AE:ARENA — Design Constitution & Claude Redesign Build Plan**

## **Purpose of This Document**

This document serves as the authoritative product design specification and implementation guidance reference for redesigning AE:ARENA.

It is intended to:

* Align product vision  
* Standardize UX philosophy  
* Define interaction systems  
* Specify layout behavior  
* Establish visual language  
* Guide Claude during implementation  
* Reduce ambiguity during redesign iterations  
* Maintain architectural consistency across the platform

This document combines:

* Product mental model  
* UX systems  
* Interaction philosophy  
* Visual design language  
* Dashboard architecture  
* DAG semantics  
* Simulation design  
* Motion systems  
* Component inventory  
* Responsive behavior  
* Build priorities

---

# **SECTION 1 — PRODUCT IDENTITY**

## **1.1 Product Name**

| Field | Value |
| ----- | ----- |
| Product Name | AE:ARENA |
| Internal Codename | Agentic Engineering Arena |
| Product Category | Multi-Agent Orchestration Experimentation Platform |
| Core Product Type | AI-Native Operational Simulation IDE |

---

## **1.2 Core Product Definition**

### **Canonical Definition**

AE:ARENA is a multi-agent orchestration experimentation environment where users construct, evolve, simulate, analyze, and optimize workflow topologies under constrained operational environments.

---

## **1.3 Primary Value Proposition**

| Category | Description |
| ----- | ----- |
| Core Value | Rapid experimentation with organizational and agentic workflows |
| Key Differentiator | Evolutionary optimization of orchestration systems |
| Main User Benefit | Discover high-performing workflow structures automatically |
| Strategic Positioning | AI orchestration IDE \+ operational simulation platform |

---

## **1.4 Product Emotional Tone**

### **Desired Emotional Characteristics**

| Attribute | Priority |
| ----- | ----- |
| Intelligent | Critical |
| Calm | Critical |
| Tactical | High |
| Experimental | High |
| Scientific | Medium |
| Futuristic | Medium |
| Premium | High |
| Operational | Critical |

### **Avoid**

| Avoided Tone |
| ----- |
| Gamer UI |
| Crypto dashboard |
| Excessive cyberpunk |
| Cartoonish futurism |
| Overly playful UI |
| Consumer social-product aesthetics |

---

# **SECTION 2 — PRODUCT MENTAL MODEL**

## **2.1 Product Metaphor**

### **Primary Mental Model**

AE:ARENA should feel like:

“An AI-native orchestration IDE with operational command-center overlays.”

---

## **2.2 Secondary Inspirations**

| Product/System | Inspiration Type |
| ----- | ----- |
| VS Code | Workspace architecture |
| Figma | Infinite canvas interaction |
| Datadog | Operational telemetry |
| Grafana | Monitoring density |
| Notion | Information clarity |
| Superhuman | Premium interactions |
| Retool | Modular operational tooling |

---

## **2.3 User Perception Goals**

Users should immediately understand:

* This is a serious experimentation environment  
* The system is modular and composable  
* Workflows can evolve over time  
* Simulation state matters  
* Data and metrics drive optimization  
* The interface supports advanced operational complexity

---

# **SECTION 3 — PRIMARY USER TYPES**

## **3.1 User Archetypes**

| User Type | Goals | Interface Priorities |
| ----- | ----- | ----- |
| AI Systems Researcher | Experiment with orchestration structures | DAG editing, metrics, evolution |
| Platform Engineer | Test workflow reliability | Telemetry, traces, debugging |
| Operations Strategist | Model organizations | Simulation visibility |
| ML Researcher | Compare optimization strategies | Analytics, benchmarking |
| Student/Research Assistant | Learn orchestration systems | Guided workflows |

---

# **SECTION 4 — PRIMARY USER MODES**

## **4.1 Product Modes**

| Mode | Goal | UI Priority | Primary Surface |
| ----- | ----- | ----- | ----- |
| Build Mode | Construct workflows | Critical | DAG Canvas |
| Simulate Mode | Execute scenarios | Critical | Simulation Viewport |
| Analyze Mode | Inspect metrics | High | Metrics Panels |
| Evolution Mode | Optimize workflows | Critical | Evolution Dashboard |
| Compare Mode | Compare generations/runs | Medium | Comparison Panels |
| Replay Mode | Replay traces | Medium | Trace Timeline |
| Library Mode | Browse reusable assets | Medium | Asset Library |

---

## **4.2 Mode Transition Philosophy**

### **Design Principles**

* Modes should feel continuous rather than isolated  
* Context should persist across modes  
* State transitions should feel fluid  
* Users should never feel “teleported” between workflows  
* Workspace memory should persist

---

# **SECTION 5 — INFORMATION HIERARCHY**

## **5.1 Primary Hierarchy**

| Priority Rank | System Element |
| ----- | ----- |
| 1 | Simulation State |
| 2 | Active Workflow Graph |
| 3 | Live Metrics |
| 4 | Agent Execution Status |
| 5 | Evolution Progress |
| 6 | Trace Visibility |
| 7 | Historical Analytics |
| 8 | Asset Library |

---

## **5.2 Critical UX Rule**

The active orchestration graph and simulation state must always remain visually dominant.

Metrics should support workflow understanding rather than overwhelm the interface.

---

# **SECTION 6 — LAYOUT SYSTEM**

## **6.1 Core Workspace Structure**

| Region | Purpose |
| ----- | ----- |
| Left Main Panel | Simulation viewport |
| Right Main Panel | DAG / topology canvas |
| Bottom Panel | Live metrics \+ telemetry |
| Left Collapsible Rail | Asset library |
| Top Navigation | Global controls |
| Floating Panels | Inspectors/modals |

---

## **6.2 Layout Philosophy**

### **Recommended Characteristics**

| Attribute | Recommendation |
| ----- | ----- |
| Layout Style | IDE-like |
| Panel Behavior | Dockable |
| Pane Resizing | Draggable |
| State Persistence | Persistent between sessions |
| Density | Medium-high |
| Canvas Behavior | Infinite/pannable |
| Sidebar Behavior | Collapsible |
| Metrics Panel | Expandable |

---

## **6.3 Recommended Spacing System**

| Token | Value |
| ----- | ----- |
| XS | 4px |
| SM | 8px |
| MD | 12px |
| LG | 16px |
| XL | 24px |
| XXL | 32px |

---

# **SECTION 7 — VISUAL DESIGN LANGUAGE**

## **7.1 Visual Philosophy**

The visual system should communicate:

* Precision  
* Modularity  
* Operational intelligence  
* Calm complexity  
* Structured experimentation

---

## **7.2 Core UI Characteristics**

| Attribute | Recommendation |
| ----- | ----- |
| Backgrounds | Light-neutral dominant |
| Interaction Surfaces | Dark interactive anchors |
| Borders | Thin/subtle |
| Transparency | Moderate |
| Shadows | Minimal |
| Gradients | Sparse but intentional |
| Corners | Slightly rounded |
| Noise Level | Low |

---

## **7.3 Recommended Color System**

### **Foundation Neutrals**

| Purpose | Hex |
| ----- | ----- |
| Background | \#F6F7FB |
| Surface | \#FFFFFF |
| Surface Alt | \#EEF1F6 |
| Border | \#D8DFEA |
| Text Primary | \#12141A |
| Text Secondary | \#5E667A |

---

## **7.4 Signature Gradient**

```css
linear-gradient(
  135deg,
  #4F46E5 0%,
  #7C3AED 30%,
  #D946EF 60%,
  #F43F5E 85%,
  #FB923C 100%
)
```

---

# **SECTION 8 — TYPOGRAPHY SYSTEM**

## **8.1 Typography Stack**

| Usage | Font |
| ----- | ----- |
| UI Font | Inter |
| Headings | Inter Tight |
| Metrics | JetBrains Mono |
| Code/Logs | JetBrains Mono |

---

## **8.2 Typography Rules**

| Rule | Recommendation |
| ----- | ----- |
| Heading Weight | 600–700 |
| Body Weight | 400–500 |
| Metric Weight | 500–600 |
| Tracking | Slightly condensed |
| Numeric Tables | Monospaced |
| Labels | Uppercase optional |

---

# **SECTION 9 — MOTION SYSTEM**

## **9.1 Motion Philosophy**

The system should feel:

* Alive but restrained  
* Smooth but efficient  
* Technical rather than playful  
* Responsive but not flashy

---

## **9.2 Recommended Motion Timings**

| Interaction | Timing |
| ----- | ----- |
| Panel Expand | 180ms |
| Modal Open | 220ms |
| Hover Transition | 120ms |
| Node Activation | 240ms |
| Chart Updates | 300ms |
| Toast Notifications | 180ms |

---

## **9.3 Animation Guidelines**

| Effect | Usage |
| ----- | ----- |
| Soft Glow | Active nodes |
| Gradient Pulse | Live orchestration |
| Numeric Rolling | Metrics |
| Opacity Fade | Panel transitions |
| Subtle Scale | Hover emphasis |

---

# **SECTION 10 — DAG / WORKFLOW SYSTEM**

## **10.1 DAG Philosophy**

The DAG editor is the core interaction surface.

It must feel:

* Flexible  
* Modular  
* Composable  
* Observable  
* Evolvable

---

## **10.2 Node System**

| Node Type | Purpose |
| ----- | ----- |
| Agent Node | Individual AI agent |
| Orchestrator Node | Routing/controller logic |
| Memory Node | Persistent state |
| Tool Node | External capability |
| Evaluation Node | Scoring/fitness |
| Environment Node | Simulation environment |
| Human Node | Human-in-the-loop interaction |

---

## **10.3 Node Visual Hierarchy**

| Element | Visual Priority |
| ----- | ----- |
| Active Nodes | Highest |
| Failed Nodes | High |
| Selected Nodes | High |
| Inactive Nodes | Medium |
| Background Groups | Low |

---

## **10.4 Node State Colors**

| State | Color |
| ----- | ----- |
| Active | Blue |
| Orchestrating | Purple |
| Successful | Green |
| Waiting | Orange |
| Failed | Red |
| Dormant | Gray |

---

## **10.5 Edge Behavior**

| Attribute | Recommendation |
| ----- | ----- |
| Curvature | Slightly curved |
| Animation | Optional execution flow |
| Thickness | State-dependent |
| Hover Interaction | Highlight connected nodes |
| Active Flow | Soft glow animation |

---

# **SECTION 11 — SIMULATION VIEWPORT**

## **11.1 Simulation Philosophy**

The simulation viewport should feel like:

* An operational sandbox  
* A live systems environment  
* A controlled experimentation chamber

---

## **11.2 Recommended Visualization Style**

| Style Attribute | Recommendation |
| ----- | ----- |
| Visual Style | Abstract operational simulation |
| Camera | Fixed \+ pannable |
| Overlays | Telemetry-enabled |
| Timeline | Persistent |
| Playback Controls | Required |
| Event Markers | Required |

---

# **SECTION 12 — DATA VISUALIZATION SYSTEM**

## **12.1 Chart Philosophy**

Charts should emphasize:

* Trends  
* Clarity  
* Comparative analysis  
* Operational visibility

---

## **12.2 Chart Design Rules**

| Attribute | Recommendation |
| ----- | ----- |
| Gridlines | Minimal |
| Accent Usage | Sparse |
| Animation | Smooth |
| Labels | Minimal but readable |
| Glow Effects | Very subtle |
| Data Density | Medium-high |

---

# **SECTION 13 — COMMAND SYSTEM**

## **13.1 Interaction Philosophy**

AE:ARENA should support advanced power-user workflows.

---

## **13.2 Required Features**

| Feature | Priority |
| ----- | ----- |
| Command Palette | Critical |
| Keyboard Shortcuts | Critical |
| Global Search | High |
| Node Search | High |
| Quick Actions | High |
| Workspace Presets | Medium |

---

# **SECTION 14 — SYSTEM STATES & FEEDBACK**

## **14.1 Core System States**

| State | UI Treatment |
| ----- | ----- |
| Idle | Calm/static |
| Loading | Subtle shimmer |
| Running | Animated activity |
| Evolving | Pulsing orchestration |
| Failed | High-contrast alert |
| Paused | Dimmed active state |
| Completed | Stable success state |

---

## **14.2 Notification Philosophy**

| Notification Type | Treatment |
| ----- | ----- |
| Success | Minimal toast |
| Warning | Soft elevated card |
| Error | High-contrast alert |
| Critical Failure | Persistent banner |
| Live Events | Activity feed |

---

# **SECTION 15 — COMPONENT INVENTORY**

## **15.1 Core Components**

| Component | Priority |
| ----- | ----- |
| DAG Node | Critical |
| DAG Edge | Critical |
| Metrics Tile | Critical |
| Simulation Viewport | Critical |
| Evolution Timeline | Critical |
| Trace Viewer | High |
| Command Palette | High |
| Agent Inspector | High |
| Asset Library | High |
| Environment Selector | Medium |
| Comparison Panel | Medium |
| Replay Controls | Medium |

---

# **SECTION 16 — RESPONSIVE DESIGN RULES**

## **16.1 Primary Target**

| Device Type | Priority |
| ----- | ----- |
| Desktop Ultrawide | Critical |
| Standard Laptop | High |
| Tablet | Medium |
| Mobile | Low |

---

## **16.2 Responsive Philosophy**

| Rule | Recommendation |
| ----- | ----- |
| Panels | Collapsible |
| Sidebars | Dockable |
| Metrics | Stack progressively |
| DAG Canvas | Preserve visibility |
| Mobile | Read-only preferred |

---

# **SECTION 17 — IMPLEMENTATION PRIORITIES**

## **17.1 Recommended Redesign Order**

| Phase | Priority |
| ----- | ----- |
| Layout Architecture | Critical |
| DAG System | Critical |
| Simulation Viewport | Critical |
| Navigation & Workspace | Critical |
| Metrics System | High |
| Motion System | High |
| Trace Visualization | High |
| Evolution Dashboard | Medium |
| Comparison Views | Medium |

---

# **SECTION 18 — CLAUDE IMPLEMENTATION GUIDANCE**

## **18.1 Claude Responsibilities**

Claude should:

* Redesign layout architecture  
* Standardize component systems  
* Improve information hierarchy  
* Modernize interaction design  
* Implement modular workspace logic  
* Improve telemetry visibility  
* Enhance DAG usability  
* Create scalable panel systems  
* Improve simulation readability

---

## **18.2 Claude Constraints**

Claude should NOT:

* Turn the interface into a gaming UI  
* Overuse neon or cyberpunk styling  
* Reduce operational information density too aggressively  
* Remove telemetry visibility  
* Over-simplify orchestration complexity  
* Replace modular workflows with static pages

---

## **18.3 Implementation Stack Recommendations**

| Layer | Recommendation |
| ----- | ----- |
| Frontend | React \+ TypeScript |
| Styling | Tailwind CSS |
| Animation | Framer Motion |
| DAG Engine | React Flow |
| Charts | Recharts / VisX |
| State Management | Zustand |
| Panels | Dockview / custom docking |

---

# **SECTION 19 — FUTURE EXTENSIONS**

## **19.1 Future Platform Features**

| Feature | Priority |

