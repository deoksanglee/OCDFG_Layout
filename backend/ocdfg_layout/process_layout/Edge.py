class Edge:
    """A directed edge between two nodes.

    `org_e` points at the original (real) edge when this edge is one segment of a
    long edge that was split with virtual nodes.
    """

    def __init__(self, snode, enode, freq=None, org_e=None, x1=None, y1=None, x2=None, y2=None,
                 rank_assigned=False, is_backbone=None):
        self.key = (snode.name, enode.name)
        self.snode, self.enode = snode, enode
        self.freq = freq
        self.org_e = org_e
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.rank_assigned = rank_assigned
        self.is_backbone = is_backbone
        self.reverse_freq = None      # frequency of the opposite direction when the pair is drawn as one edge

    def __eq__(self, other):
        return self.snode.name == other.snode.name and self.enode.name == other.enode.name

    def __hash__(self):
        return hash((self.snode.name, self.enode.name))

    def calculate_edge_x_y(self):
        self.x1, self.y1 = self.snode.x, self.snode.y
        self.x2, self.y2 = self.enode.x, self.enode.y

    def is_online(self, x, y):
        """True if (x, y) lies within the bounding box of the edge, excluding its endpoints."""
        x1, y1 = self.snode.x, self.snode.y
        x2, y2 = self.enode.x, self.enode.y
        if (x1, y1) == (x, y) or (x2, y2) == (x, y):
            return False
        return min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2)

    def is_intersect(self, edge):
        """True if the two straight segments cross (touching endpoints do not count)."""
        a1 = self.enode.y - self.snode.y
        b1 = self.snode.x - self.enode.x
        c1 = a1 * self.snode.x + b1 * self.snode.y

        a2 = edge.enode.y - edge.snode.y
        b2 = edge.snode.x - edge.enode.x
        c2 = a2 * edge.snode.x + b2 * edge.snode.y

        det = a1 * b2 - a2 * b1
        if det == 0:
            return False
        x = round((b2 * c1 - b1 * c2) / det, 5)
        y = round((a1 * c2 - a2 * c1) / det, 5)
        return self.is_online(x, y) and edge.is_online(x, y)
