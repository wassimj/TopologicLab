# TopologicLab

TopologicLab is a 2D and 3D spatial-analysis workspace powered by TopologicPy, with space syntax, isovists and shortest paths over a building-wide navigation graph. The building pipeline now uses TopologicPy’s IFC.NavigationModel, Navigation.Graph and Navigation.IsovistFaces APIs.

## Run

Clone the repository alongside your TopologicPy checkout, then open its folder:

```text
git clone https://github.com/wassimj/TopologicLab.git
cd TopologicLab
```


Use the existing `topologicpy-occ8` environment:

```powershell
.\start.ps1
```

Or activate that environment and run:

```text
python launch.py
```

Open the address printed by the launcher, normally http://127.0.0.1:8017. If that port is occupied, the launcher chooses a free port.

The environment needs the current local TopologicPy navigation, clearance and isovist boundary-type APIs, NumPy, Shapely 2 or later, FastAPI, Uvicorn, python-multipart and the existing TopologicPy/PythonOCC setup. `backend/web-requirements.txt` lists the web and import dependencies. The launcher does not install packages, change TopologicPy or create an environment.

## Try the building

Click **3D example**, then **Run analysis**. The included IFC4 example has two storeys, 18 treads, an external U-shaped ramp, a lift with two doors, a wall doorway, a column, a split-level slab and an excluded roof. The ramp has three 1.5 m-wide runs: 24 m, 12 m (the house width), and 24 m, all at 1:20. Two 1.5 x 1.5 m turning landings sit at z=1.2 m and z=1.8 m. A flat arrival platform connects the upper run to the first floor. The combined horizontal sloping run remains 60 m for the 3 m storey rise. The former internal ramp opening is filled. You can also import `examples/two-storey-demo.ifc` manually.

- Drag to rotate; right-drag or Shift-drag to pan; scroll to zoom.
- Use the viewport buttons for top view, 3D view and fitting the building.
- Select a storey and enable **Isolate selected storey** to inspect it. Isolation changes display only.
- **Whole building** is the default graph-analysis scope. **Selected storey only** builds an induced storey graph and excludes paths through other storeys.
- In **Shortest Path**, click start A and destination B. You can change the isolated storey between those clicks. Choose-start/end buttons let you replace either endpoint. Routes minimise geometric distance using TopologicPy's Dijkstra implementation.
- Optional straightening acts only on contiguous horizontal floor portions; stairs, ramps and lift travel retain their geometry.
- Isovists use the selected storey. Choose a grid field or interactive viewpoint. Eye-level faces sit 1.6 m above each distinct walking elevation, including split levels. Use field-of-view and direction controls for directional isovists.
- Colours, colour limits, opacity, hover inspection and graph display work with the resulting 3D geometry. Export JSON, CSV or a viewport PNG. JSON includes the complete graph and model; CSV includes Z and storey. PNG captures the current viewport; its legend remains in the interface.

Isovists distinguish transparent floor voids from opaque obstacles using the latest TopologicPy boundary labels. You can see across a genuine opening, but cannot select a viewpoint or navigate within it. Columns and walls remain opaque. The isovist field graph shows visual relationships across voids; navigation graphs retain their walkable domains. Eye-height classification comes from `Navigation.IsovistFaces`; merged void/obstacle boundaries are opaque as a whole. Boundary roles survive IFC import, JSON export, and analysis requests. Older model data lacking labels is rebuilt through the API during analysis. No extra interface setting is required.

## Geometry and navigation

IFC is the building input. Existing DXF, OBJ, Rhino and BREP imports retain their horizontal-face import behaviour and feed the same graph pipeline as the 2D special case.

TopologicPy’s IFC.ModelByPath parses each file once. IFC.NavigationModel extracts the walking surfaces, obstacles and stairs, ramps and lifts; Navigation.Graph constructs the building graph; Navigation.IsovistFaces supplies the horizontal visibility faces. The viewport uses a separate display mesh adapter from the same parsed model. Furniture and openings use bounding boxes (8 vertices, 12 triangles) in the browser. Runtime import does not use IfcOpenShell. Native BREP face data and retained solid obstacle data travel with the model, so small IFC fragments and exact obstacle sections survive the browser/API round trip and JSON export.

**Boundary clearance** defaults to 0 m. Positive values keep navigation/visibility grid points and edges away from exposed boundaries and obstacles, while preserving physically adjoining slab and step seams. Narrow passages and connectors can disappear or become disconnected. Stair clearance acts on the assembly width; it does not shrink each tread independently. Original surviving display tiles still receive colours. Isovist fields move their sampling points inward but measure visibility against the original eye-level face. Clearance is available for navigation and visibility grids, not imported segment or axial networks. Changing clearance or spacing clears stale results and paths. Path snapping and straightening respect clearance; choose route endpoints inside the remaining usable area.

The XY grid has a common origin and is projected onto each slab plane. Shared slab boundaries connect only when their height difference is at most 17 cm. Corner contacts and horizontal gaps do not create floor edges. Navigation tiles retain their true 3D coordinates and holes.

Stair points come from horizontal tread and landing geometry. Physically adjoining steps connect; missing steps are not filled in. Ramp centrelines come from horizontal sections through upward ramp faces. Samples are spaced at 15% of total 3D centreline length, with endpoints and horizontal landing centres retained. The last interval may be shorter. Ramp sample nodes colour the corresponding ramp bands. Separate landing slabs can join ramp endpoints.

Lift doors are associated geometrically with a lift footprint. Each served floor gets a door point and cabin-centre point. Consecutive served stops connect vertically; lift nodes have no result tiles and are not coloured. Door/cabin and connector/floor attachments are checked against available walkable geometry and obstacles. Connector attachments choose the nearest reachable floor-graph point.

The application uses the public TopologicPy IFC and Navigation APIs for extraction, grids and connector construction. TopologicPy also provides graph analysis, angular analysis, isovists, Dijkstra routing and straightening. Angular measures use full 3D segment directions. Because those APIs return segment scores, a navigation tile shows the mean of the scores on its incident segments. Lifts participate in graph analysis but are not coloured.

Existing visibility, grid, imported segment, imported axial, generated axial and isovist-intersection options are retained. Imported-network options require usable segment input; IFC buildings usually use a grid, visibility or generated axial graph. Each storey's planar network is joined to the vertical connectors.

## Prototype limits

Geometry inference is best effort. Opening and furniture bounds are conservative axis-aligned approximations. Complex CSG cuts and representation types unsupported by the fast IFC reader may not reproduce full BIM-kernel geometry. Ambiguous or missing tread, ramp, landing, lift or door geometry can leave disconnected components. The app does not fabricate connections or display malformed-IFC warnings. Roof exclusion and walkability follow IFC type information plus upward-facing slab geometry; this is not a semantic walkability classifier.

Ramp extraction assumes a ramp progresses through elevation and has one continuous cross-section at each sampled height. Unresolvable or branching geometry can remain disconnected. Stairs are inferred from adjoining horizontal surfaces; steps without usable tread faces remain unconnected. Lift association uses geometric proximity and available door geometry. Sloping-floor obstacle cuts use the surface's lower, middle and upper elevations. These approximations are suitable for the requested demo and need testing against your own IFC models.

Uploads retain the existing 25 MB limit. Graphs are limited to 10,000 points; visibility and all-pairs analyses can become expensive. The viewport uses a perspective camera and WebGL depth-buffered, double-sided faces, with a translucent IFC context layer. Concave faces and holes use stencil masks. Coplanar result layers have explicit depth bias. WebGL is required. Graphs, paths and interaction markers use a separate overlay canvas.

## Verification

Run in the same environment:

```text
python -m pytest tests -q
```

See `VERIFICATION.md` for the checks completed and the browser-preview limitation.


## Repository and configuration

Project name: **TopologicLab**. The application uses TopologicPy as its geometry
and analysis dependency; it does not bundle or replace that library.

Run `python backend/check_api.py` in your existing environment before starting.
A current TopologicPy checkout containing Navigation, IFC navigation adapters,
clearance and isovist boundary roles is required; the version number alone may
not establish support for these APIs.

- `TOPOLOGICLAB_API_TOKEN`: optional bearer token for the analysis API.
- `TOPOLOGICLAB_ROUTE_CACHE_DIR`: optional routing-cache location.
- `ALLOWED_ORIGINS`: comma-separated allowed frontend origins when serving the
  frontend and API separately.
- `TOPOLOGICLAB_DUPLEX_IFC`: optional path to the external duplex IFC for tests.

The earlier `SPATIAL_API_TOKEN` and `SPATIAL_ROUTE_CACHE_DIR` variables remain
accepted for existing installations. New setups should use the TopologicLab names.
Do not commit tokens or `.env` files. The supplied two-storey demo is included;
external IFC files used for testing are not part of this repository.

## License

Licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
