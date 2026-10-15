# Verification — TopologicLab

Verified on 14 October 2026 using the existing `topologicpy-occ8` environment, TopologicPy 0.9.84 and PythonOCC. No TopologicPy source was changed.

## Passed

- **33 regression tests** in `tests/test_building.py` (8.16 seconds on the final run).
- The 17 cm slab-rise boundary, rejection of larger rises, and rejection of horizontal gaps.
- IFC roof exclusion, column/wall obstruction, door passage, storey grouping and elevation fallback.
- Independent cross-storey routes through stairs, ramps and lifts. The fixture yields all 18 tread points and 17 consecutive tread edges.
- Ramp spacing at 15% of 3D centreline length, endpoint retention, ramp colour tiles and retention of a turning landing centre.
- No fabricated route when vertical connector geometry is absent.
- Storey-only subgraphs contain no other-storey nodes or vertical lift travel.
- Separate isovist planes at 1.6, 4.6 and 4.75 m for the fixture's ground, first-floor and split-level surfaces.
- Every existing space-syntax measure, including 3D angular measures, NAIN and NACH.
- All six retained graph-construction options on a 2D case.
- Geometric Dijkstra routing and horizontal-floor straightening.
- Seven in-process ASGI integration checks: health, frontend serving, actual IFC multipart upload, analysis JSON serialization, graph preparation, cross-storey routing and the retained OBJ importer.
- JavaScript syntax and a mock-DOM frontend test covering initialization, 3D projection/inverse-picking algebra across camera angles, building/storey scope and colour-range state.

## Not verified visually

The available app browser could not connect to the local preview server (connection refused/timeout). Direct local-file navigation was blocked by browser policy. No workaround browser was used. Consequently, real browser rendering, pointer gestures, high-DPI canvas hit-testing and download interactions have **not** been visually verified. The JavaScript tests are not a substitute for that review.

## Coverage limits

The included IFC4 fixture is synthetic and deliberately readable. Production IFC exporters, large models and unusual stair/ramp/lift representations have not been benchmarked. Geometry interpretation is best effort and may leave components disconnected, as specified. See README.md for the prototype's inference assumptions.


## Perspective viewport correction — 14 October 2026

Replaced mean-depth Canvas face sorting with a WebGL depth buffer. Faces render from both sides. Stencil parity preserves concave outlines and holes, and explicit polygon offsets separate coplanar floor/result/context layers. Translucent IFC context tests the surface depth buffer without writing into it. The camera now uses a 50-degree vertical perspective field of view, with camera-ray/plane picking, near-plane clipping and perspective-aware fitting. PNG export composites the WebGL surface canvas with the interaction overlay.

Passed JavaScript syntax checks; perspective foreshortening; CPU/GPU projection agreement; inverse picking across 25 camera orientations and a vertical face; near-plane clipping; concave/holed-face parity with reversed winding; and mocked WebGL depth, stencil, culling and layer-bias checks. Run `node tests/frontend-state.cjs` and `node tests/face-renderer.cjs` from this folder.

Live browser/GPU rendering remains unverified: another local preview attempt timed out. These checks validate the projection math, geometry masks and render-state setup, not actual driver rasterisation.


## IFC2x3 Duplex importer correction — 14 October 2026

Tested the user-supplied `Ifc2x3_Duplex_Architecture.ifc`. Before the correction, no stair connectors were extracted. IfcOpenShell attempted the stair flights' first `WalkingLine` representation and failed, despite usable `Body` geometry being present. Some walls similarly failed on their `Axis` representation.

The importer now explicitly selects the product's `Body` representation when available, retaining the default selection only when no Body exists. No connection threshold or TopologicPy source was changed. Both stair flights and 57 wall objects now import. Both staircases independently connect Level 1 to Level 2 at 1, 1.5, 2 and 4 m grid spacing, verified using TopologicPy Dijkstra routes. At 1 m spacing the tested attachment-to-attachment routes measure 5.5268 m and 5.5548 m.

The complete regression run passed **37 tests in 32.33 seconds**. Four parameterised tests exercise this real IFC; set `SPATIAL_DUPLEX_IFC` to its local path to run them. Without that optional file, those four tests skip. The source IFC was read without modification and is not redistributed in the package.

Restart the backend after installing the update, and reimport the IFC. Existing imported JSON/model state still lacks the stair geometry. The health revision is `building-3d-20261014-2-ifc-body`.


## TopologicPy IFC reader and box-only context — 15 October 2026

IFC import now parses once with `IFC.ModelByPath`, reads entities with `IFC.Entities`, and obtains supported world meshes with `IFC.MeshData`. The application does not open, parse or tessellate the file with IfcOpenShell. TopologicPy source remains unchanged. Parsed-entity adapters cover composite-curve extrusion profiles (including the duplex stair treads) and indexed IFC4 face sets. Extrusion caps are normalised before upward-face extraction.

Furniture and IfcOpeningElement context objects are serialized only as world-aligned bounding boxes: eight vertices and twelve triangles each. They are not triangulated from their detailed meshes for browser display. Host void relationships plus opening boxes maintain navigation passages and slab openings. Bounding furniture footprints are used conservatively for obstacle sections.

The duplex has 61 furniture boxes and 50 opening boxes. Its final context mesh contains **6,576 vertices / 11,168 triangles**, compared with the previous IfcOpenShell context's **15,546 vertices / 27,172 triangles** (about 59% fewer triangles). Within the new reader's representation set, detailed geometry would contain 24,168 triangles; box simplification reduces that to 11,168. This is a geometry-count comparison, not a measured browser frame-rate claim. The fast reader remains an approximate geometry importer; unsupported CSG/representation details are best effort.

**38 regression tests passed in 24.53 seconds**, including all prior synthetic navigation/analysis tests, both duplex staircases at four spacings, and the furniture/opening box assertions. Runtime imports/dependency lists contain no IfcOpenShell requirement. Check the installed API with `python backend/check_api.py` before deployment.

Restart the backend and reimport the IFC to replace previously imported detailed context. Health revision: `building-3d-20261015-1-topologic-ifc`.


## Three-run U-shaped demo ramp — 15 October 2026

The bundled IFC has three IfcRampFlight objects, with horizontal lengths 24 m, 12 m (the house width), and 24 m. All three slopes are 1:20, rising 1.2 m, 0.6 m, and 1.2 m. Two flat 1.5 x 1.5 m IfcSlab turning landings at z=1.2 m and z=1.8 m join the runs into a U. Runs are 1.5 m wide. A flat first-floor arrival platform joins the upper run back to the building. The former internal ramp opening remains filled.

33 regression tests passed; five optional external-duplex tests were skipped. Checks cover all three slopes/lengths, both landing areas/elevations, 15% centreline sample spacing and tiles, and a ramp-only shortest path through both landing nodes. Stair-only and lift-only routes, existing analysis measures, and separate landing eye-level isovist planes also pass.

Replace `examples/two-storey-demo.ifc` and click **3D example** again, or import the IFC manually. No backend restart is required for this fixture-only update.


## Navigation API and clearance migration — 15 October 2026

- IFC.NavigationModel now owns navigation extraction; Navigation.Graph owns floor grids and vertical circulation; Navigation.IsovistFaces supplies visibility geometry. The application retains viewport and JSON adapters.
- 46 Python checks passed in the existing topologicpy-occ8 / PythonOCC environment, with the supplied external duplex enabled. Both duplex stairs connect at grid spacings 1, 1.5, 2 and 4 m, and at 1.5 m spacing with 0.2 m clearance.
- Independent stair, three-run ramp and lift routes survive a full browser JSON / request-model round trip with both zero and 0.2 m clearance. Native BREP faces preserve small fragments during transport.
- Clearance tests cover point and edge exclusion, consumed regions, invalid inputs, graph-cache separation, endpoint snapping and safe floor straightening. Isovist sampling uses Grid.OnFace clearance while visibility continues to use the original host. The final isovist sampling adjustment passed its targeted regression.
- Frontend mock-DOM and mock-WebGL checks pass, including clearance in requests and clearing stale routes when it changes. API capability checks pass against local TopologicPy 0.9.74. These checks do not establish real-browser visual correctness.
- No original 2D app, deployed service or TopologicPy source was changed for this migration.

- Nine local ASGI checks passed: health, frontend serving, IFC multipart upload, analysis serialization, graph preparation, cross-storey routing, positive-clearance routing, invalid-clearance rejection and retained OBJ import.


## Transparent isovist voids — 15 October 2026

- Eye-level boundary labels from Navigation.IsovistFaces now survive IFC import, browser JSON transport, native BREP reconstruction, and planar analysis-host reconstruction. The browser model stores an aligned hole_types list; restored native wires receive isovistType dictionaries by geometry, avoiding dependence on BREP ring enumeration order.
- Isovist fields and point views see across transparent floor voids. Columns/walls still block visibility, and both boundary types exclude viewpoints. Visual field graph edges may cross holes; navigation points and edges still cannot. Clearance applies to sampling against the unchanged walkable face.
- Legacy model data without roles regenerates its eye-level faces through Navigation.IsovistFaces. The retained 2D special case uses that same API.
- 56 Python checks passed in the existing PythonOCC environment with the supplied duplex enabled, including both stairs, clearance routes, role round trips, cache invalidation, legacy models, view rejection, field sampling and visual/navigation graph differences.
- Eleven local ASGI checks passed, including actual IFC multipart upload, response serialization, path preparation/routing, positive and invalid clearance, visibility across a void, rejected void viewpoints and retained OBJ import. Frontend mock-DOM, mock-WebGL, syntax and API capability checks passed.
- This revision requires the updated Face.Isovist and Navigation.IsovistFaces APIs. Start/restart the local 3D service after updating the library/app. Real-browser visual verification remains outstanding. The original 2D app and deployed syntopy.io service were not changed.

## TopologicLab repository preparation — 15 October 2026

Renamed the interface, service, launcher, export files, assets and documentation
to TopologicLab. The source repository sits beside the TopologicPy checkout.
The existing PythonOCC environment was retained. All 56 Python tests passed
from the new repository, including the external duplex checks; frontend state
and rendering harnesses passed. Legacy environment-variable names remain
accepted alongside TOPOLOGICLAB_API_TOKEN and TOPOLOGICLAB_ROUTE_CACHE_DIR.
