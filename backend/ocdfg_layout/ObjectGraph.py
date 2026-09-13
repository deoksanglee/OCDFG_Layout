from .ObjectEdge import ObjectEdge
from .ObjectNode import ObjectNode
from .process_layout.Graph import Graph


class ObjectGraph(Graph):
    """The laid-out directly-follows graph of a single object type."""

    def __init__(self, nodes, edges, object_type):
        super().__init__(nodes, edges)
        self.object_type = object_type

    @classmethod
    def from_layout(cls, layout, ot):
        """Wrap a laid-out single-object Graph into an ObjectGraph tagged with `ot`.

        Virtual nodes are renamed '<name>-<ot>' so they stay unique after merging.
        """
        nodes, edges = {}, {}

        for name, n in layout.nodes.items():
            if not n.is_real:
                name = ObjectNode.gen_key(name, ot)
            nodes[name] = ObjectNode(name=name, is_real=n.is_real, is_backbone=n.is_backbone,
                                     rank=n.rank, order=n.order, is_start=n.is_start, is_end=n.is_end,
                                     object_types=[ot], object_axis=ot)

        for e in layout.edges.values():
            sname = e.snode.name if e.snode.is_real else ObjectNode.gen_key(e.snode.name, ot)
            ename = e.enode.name if e.enode.is_real else ObjectNode.gen_key(e.enode.name, ot)
            key = ObjectEdge.gen_key((sname, ename), ot)
            edges[key] = ObjectEdge(snode=nodes[sname], enode=nodes[ename], object_type=ot,
                                    freq=e.freq, org_e=e.org_e)

        og = cls(nodes=nodes, edges=edges, object_type=ot)
        og.set_backbone_graph()
        return og

    def set_backbone_graph(self):
        nodes = {name: n for name, n in self.nodes.items() if n.is_backbone}
        edges = {key: e for key, e in self.edges.items() if e.is_backbone}
        self.backbone = ObjectGraph(nodes=nodes, edges=edges, object_type=self.object_type)

    def get_graph_width_order(self):
        """Number of order slots the graph occupies (left part + backbone + right part)."""
        return abs(self.left_max_order) + self.right_max_order + 1
