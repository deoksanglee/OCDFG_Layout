from .process_layout.Node import Node


class ObjectNode(Node):
    """A node of the merged multi-object graph.

    `object_types` lists every object type whose graph contains the activity,
    `object_axis` is the type whose axis the node is drawn on and
    `nodes_visualized` holds one sub-circle per object type (see
    MultiObjectGraph.calculate_visual_coordinates).
    """

    def __init__(self, name, is_real=None, is_backbone=None, rank=None, order=None,
                 is_start=None, is_end=None, object_types=None, object_axis=None, global_order=None):
        super().__init__(name, is_real=is_real, is_backbone=is_backbone, rank=rank, order=order,
                         is_start=is_start, is_end=is_end)
        self.object_types = list(object_types) if object_types else []
        self.object_axis = object_axis
        self.global_order = global_order
        self.nodes_visualized = {}
        self.sub_nodes = []

    @classmethod
    def gen_key(cls, name, ot):
        return '-'.join([name, ot])

    def append_object_type(self, ot):
        # NOTE: set() order is intentionally kept; it feeds the rank-assignment model
        self.object_types = list(set(self.object_types + [ot]))

    def insert_object_type(self, ot, index=0):
        self.object_types.insert(index, ot)
