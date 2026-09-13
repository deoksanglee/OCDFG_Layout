class Node:
    """A node of a single-object directly-follows graph.

    `rank` is the vertical layer, `order` the horizontal slot within the layer
    (negative = left of the backbone, positive = right).  `is_real` is False for
    the virtual nodes inserted on edges that span more than one rank.
    """

    def __init__(self, name, is_real=None, is_backbone=None, rank=None, order=None,
                 x=None, y=None, is_start=None, is_end=None):
        self.name = name
        self.is_real = is_real
        self.is_backbone = is_backbone
        self.is_start = is_start
        self.is_end = is_end
        self.rank = rank
        self.order = order
        self.is_right = True
        self.x = x
        self.y = y

        # neighbours on the same rank, filled by set_node_left_right()
        self.left_n = None
        self.right_n = None
        self.width = 0
        self.height = 40

    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def calculate_node_x_y(self, center, order_width, rank_height):
        self.x = round(center + order_width * self.order, 5)
        self.y = rank_height * (self.rank + 1)
