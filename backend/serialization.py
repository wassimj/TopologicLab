"""JSON-safe display serialization."""
import math

def clean(v):
    if isinstance(v,(int,float)):
        return float(v) if math.isfinite(v) else None
    if isinstance(v,(list,tuple)):return [clean(x) for x in v]
    return v if isinstance(v,(str,bool)) or v is None else str(v)
