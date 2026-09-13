"""Layout algorithm for object-centric directly-follows graphs (OC-DFG).

Public entry points:
    MultiObjectGraph.generate_layout_from_log(log)  -> (layout dict, MultiObjectGraph)
    MultiObjectGraph.recompute_with_filter_value(v) -> layout dict
    MultiObjectGraph.recompute_with_kept_edges(keys) -> layout dict
    preprocess.ocel_to_layout_log(ocel_dict)        -> log accepted by generate_layout_from_log
"""
from .conf import config
from .MultiObjectGraph import MultiObjectGraph
from .ObjectEdge import ObjectEdge
from .ObjectGraph import ObjectGraph
from .ObjectNode import ObjectNode

__all__ = ["config", "MultiObjectGraph", "ObjectEdge", "ObjectGraph", "ObjectNode"]
