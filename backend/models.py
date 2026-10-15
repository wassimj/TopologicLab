"""Request/response contracts and supported analysis labels."""
import math
from typing import Literal
from pydantic import BaseModel,Field

SYNTAX = {
    "Integration": "Visual integration", "Choice": "Choice / betweenness",
    "Connectivity": "Connectivity", "AngularIntegration": "Angular integration",
    "AngularChoice": "Angular choice", "AngularConnectivity": "Angular connectivity",
    "DepthMap": "Total depth", "MeanDepth": "Mean depth",
    "AccessibilityCentrality": "Accessibility", "DegreeCentrality": "Degree centrality",
    "EigenVectorCentrality": "Eigenvector centrality",
    "TulipChoice":"Angular Tulip choice", "TulipIntegration":"Angular Tulip integration",
    "NAIN":"Normalized angular integration (NAIN)", "NACH":"Normalized angular choice (NACH)",
    "TulipNodeCount":"Angular radius node count", "TulipTotalDepth":"Angular total depth", "TulipTotalWeight":"Angular total weight",
}
ISO = {
    "area": "Isovist area", "perimeter": "Isovist perimeter", "compactness": "Compactness",
    "d_max": "Maximum distance", "d_min": "Minimum distance", "d_avg": "Average distance",
    "v_max": "Maximum vista", "v_min": "Minimum vista", "v_d": "Vista drift",
    "v_density": "Vista density", "symmetry": "Symmetry", "d_f": "Fractal dimension",
    "e_c": "Edge complexity", "theta": "Mean visual field angle", "occlusivity": "Occlusivity",
    "drift": "Drift", "closed_perimeter": "Closed perimeter", "average_radial": "Average radial",
    "variance": "Radial variance", "skewness": "Radial skewness",
}

class Boundary(BaseModel):
    id: int
    name: str = "Boundary"
    outer: list[list[float]]
    holes: list[list[list[float]]] = Field(default_factory=list)
    hole_types: list[Literal["hole", "obstacle"]] = Field(default_factory=list)
    elevation: float = 0
    plane: list[float] | None = None
    storey: str = "0"
    kind: str = "floor"
    source: str | None = None

class Model(BaseModel):
    name: str
    unit: Literal["m"] = "m"
    faces: list[Boundary]
    navigation_faces: list[dict] = Field(default_factory=list)
    navigation_ifc: dict = Field(default_factory=dict)
    dimension: int = 2
    storeys: list[dict] = Field(default_factory=list)
    connectors: list[dict] = Field(default_factory=list)
    lifts: list[dict] = Field(default_factory=list)
    doors: list[dict] = Field(default_factory=list)
    obstacles: list[dict] = Field(default_factory=list)
    isovist_faces: list[dict] = Field(default_factory=list)
    context: list[dict] = Field(default_factory=list)
    segments: list[list[list[float]]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class Analysis(BaseModel):
    model: Model
    boundary: int = 0
    storey: str | None = None
    kind: Literal["syntax", "isovist", "path"] = "syntax"
    metric: str = "Integration"
    spacing: float = Field(default=4, ge=.1, le=100)
    clearance: float = Field(default=0, ge=0, allow_inf_nan=False)
    graph_mode: Literal["visibility", "segments", "axial", "axial_generated", "grid_shell", "isovist_intersection"] = "visibility"
    weight: Literal["topological", "metric"] = "topological"
    normalize: bool = False
    fov: float = Field(default=360, ge=1, le=360)
    direction: float = Field(default=0, ge=0, le=360)
    point: list[float] | None = None
    radius: float | None = Field(default=None,gt=0)
    radius_type: Literal["angular","metric","topological"] = "angular"
    algorithm: Literal["exact","tulip"] = "exact"
    weighting: Literal["none","length"] = "none"
    tulip_bins: int = Field(default=1024,ge=4,le=4096)
    step: int = Field(default=2,ge=1,le=10)
    min_overlap: float = Field(default=0,ge=0)
    isovist_radius: float | None = Field(default=None,gt=.0001)
    compute_overlap: bool = True
    axial_reduce: bool = True
    axial_sampling_distance: float | None = Field(default=None, gt=0)
    axial_max_candidates: int = Field(default=10000, ge=1, le=10000)
    axial_max_samples: int = Field(default=1000, ge=1, le=10000)
    axial_tolerance: float = Field(default=.0001, gt=0, le=.1)
    path_graph: Literal["visibility", "grid_shell", "navigation"] = "navigation"
    path_start: list[float] | None = None
    path_end: list[float] | None = None
    straighten: bool = False

def finite_coords(points):
    return len(points) >= 3 and all(len(p) >= 2 and all(math.isfinite(v) and abs(v) < 1e9 for v in p[:3]) for p in points)
