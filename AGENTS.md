# TopologicLab implementation rules

The user authorised migration to the new TopologicPy IFC and Navigation APIs on 2026-10-15. Delegate IFC navigation extraction, grids, connectors and clearance to those APIs. Keep display and transport adapters in TopologicLab.

Reuse existing TopologicPy public APIs for graph analyses, angular analyses, isovists, Dijkstra routing and straightening. Preserve the existing topologicpy-occ8 environment and PythonOCC backend. Never create another environment or silently replace the backend.

Keep the agreed rules: IFC building input; retained 2D formats; roofs excluded; world metres; containment then elevation fallback; obstacles and openings respected; 17 cm maximum slab rise; no horizontal-gap bridging; per-tread and landing points; ramps sampled at 15% of centreline length; lift door and cabin points; nearest reachable attachments; whole-building graph default and storey-only subgraphs; strictly planar isovists 1.6 m above each walking elevation. Incomplete IFC geometry may remain disconnected without warnings or invented connections.

Regression-test geometry and connection changes with the included IFC fixture. Keep this app separate from the original 2D prototype and any deployed service unless the user requests deployment.
