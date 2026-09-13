class Component:
    """A connected component of non-backbone nodes, placed left or right of the backbone."""

    def __init__(self, nodes):
        self.nodes = nodes
        self.is_right = True

    def __len__(self):
        return len(self.nodes)

    def move_to_left(self):
        self.is_right = False
        for n in self.nodes:
            n.is_right = False

    def move_to_right(self):
        self.is_right = True
        for n in self.nodes:
            n.is_right = True
