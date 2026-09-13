import copy
from collections import defaultdict, deque

from .Component import Component
from .Edge import Edge
from .Node import Node


class Graph:
    """Layered layout of a single-object directly-follows graph.

    Node ranks are assigned outside (MultiObjectGraph.assign_rank); this class
    places the most frequent variant (the *backbone*) on order 0, balances the
    remaining connected components left and right of it and orders the nodes of
    each rank with a weighted-median heuristic to reduce edge crossings.
    """
    order_width = 200
    rank_height = 150
    node_width = 100
    node_height = 40
    eps = 100  # minimum horizontal gap between neighbouring nodes

    def __init__(self, nodes, edges):
        self.nodes = nodes
        # keep only edges whose endpoints are in `nodes`, bound to these node objects
        self.edges = {}
        for key, e in edges.items():
            if e.snode.name in self.nodes and e.enode.name in self.nodes:
                e.snode, e.enode = self.nodes[e.snode.name], self.nodes[e.enode.name]
                self.edges[key] = e

        self.backbone = None
        self.org_edges = {}
        self.rank_size = defaultdict(int)
        self.virtual_nodes = [n for n in self.nodes.values() if not n.is_real]

        self.init_adj_nodes()
        self.update_rank_bounds()
        self.update_order_bounds()

    def __sub__(self, other):
        nodes = {name: n for name, n in self.nodes.items() if name not in other.nodes}
        edges = {key: e for key, e in self.edges.items() if key not in other.edges}
        return Graph(nodes, edges)

    def copy(self):
        g = copy.deepcopy(self)
        for e in g.edges.values():
            if e.snode.name in g.nodes and e.enode.name in g.nodes:
                e.snode, e.enode = g.nodes[e.snode.name], g.nodes[e.enode.name]
        return g

    # ------------------------------------------------------------------ bounds
    def update_rank_bounds(self):
        ranks = [n.rank for n in self.nodes.values() if n.rank is not None]
        if ranks:
            self.min_rank, self.max_rank = min(ranks), max(ranks)

    def update_order_bounds(self):
        orders = [n.order for n in self.nodes.values() if n.order is not None]
        self.right_max_order = max((o for o in orders if o >= 0), default=0)
        self.left_max_order = min((o for o in orders if o < 0), default=0)

    def get_rank_size(self, rank):
        if rank not in self.rank_size:
            self.rank_size[rank] = len([n for n in self.nodes.values() if n.rank == rank])
        return self.rank_size[rank]

    # --------------------------------------------------------------- adjacency
    def init_adj_nodes(self):
        adj_nodes = defaultdict(list)
        for e in self.edges.values():
            s, t = e.snode.name, e.enode.name
            if s in self.nodes and t in self.nodes and t not in adj_nodes[s]:
                adj_nodes[s].append(t)
                if s not in adj_nodes[t]:
                    adj_nodes[t].append(s)
        self.adj_nodes = adj_nodes

    def dfs(self, start_name, consider_assigned_edge=False):
        """Nodes reachable from `start_name` (undirected), in visiting order."""
        visited = []
        stack = deque([self.nodes[start_name]])
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.append(node)
            adj = [self.nodes[name] for name in self.adj_nodes[node.name]]
            if consider_assigned_edge:
                adj = [m for m in adj if self._edge_rank_assigned(node.name, m.name)]
            stack.extend(adj)
        return visited

    def _edge_rank_assigned(self, a, b):
        return any(key in self.edges and self.edges[key].rank_assigned is True
                   for key in ((a, b), (b, a)))

    def get_components(self, exclude_backbone=True, consider_assigned_edge=False):
        g = self - self.backbone if exclude_backbone else self
        components, visited = [], set()
        for name in g.nodes:
            if name not in visited:
                c = Component(g.dfs(name, consider_assigned_edge))
                components.append(c)
                visited.update(n.name for n in c.nodes)
        return components

    def get_downward_neighbors(self, n):
        return [self.nodes[m] for m in self.adj_nodes[n.name] if self.nodes[m].rank == n.rank + 1]

    def get_upward_neighbors(self, n):
        return [self.nodes[m] for m in self.adj_nodes[n.name] if self.nodes[m].rank == n.rank - 1]

    # ---------------------------------------------------------------- backbone
    def set_backbone(self, backbone_seq):
        """Flag the nodes of the most frequent variant and return them as a graph."""
        for name, n in self.nodes.items():
            n.is_backbone = name in backbone_seq

        backbone_edges = {}
        ordered = sorted((n for n in self.nodes.values() if n.is_backbone), key=lambda n: n.rank)
        for pre, post in zip(ordered, ordered[1:]):
            key = (pre.name, post.name)
            if key in self.edges:
                self.edges[key].is_backbone = True
                backbone_edges[key] = self.edges[key]

        return Graph(dict(self.nodes), backbone_edges)

    def get_backbone(self):
        nodes = {name: n for name, n in self.nodes.items() if n.is_backbone}
        edges = {key: e for key, e in self.edges.items() if e.snode.is_backbone and e.enode.is_backbone}
        return Graph(nodes, edges)

    # ------------------------------------------------------------------ layout
    def generate_layout(self, backbone_seq, minimize_cross=True):
        """Order the nodes of each rank along the backbone and return the virtual graph."""
        self.backbone = self.set_backbone(backbone_seq)
        g = self.make_virtual_graph()
        for e in g.edges.values():
            e.rank_assigned = True
        g.backbone = g.get_backbone()

        g.balance_components()
        g.set_rank_node()
        if minimize_cross:
            g.minimize_cross()
        return g

    def make_virtual_graph(self):
        """Split every edge spanning more than one rank with virtual nodes."""
        edges = {}
        for key, e in self.edges.items():
            rank_diff = int(abs(e.snode.rank - e.enode.rank))
            if rank_diff <= 1:
                edges[key] = e
                continue

            direction = 1 if e.enode.rank > e.snode.rank else -1
            is_backbone = key in self.backbone.edges
            vns = [Node(name=f'vn{len(self.virtual_nodes) + i}', is_real=False, is_backbone=is_backbone,
                        rank=e.snode.rank + direction * (i + 1))
                   for i in range(rank_diff - 1)]
            # insertion order matters downstream (adjacency lists follow it)
            edges[(e.snode.name, vns[0].name)] = Edge(e.snode, vns[0], org_e=e, freq=e.freq)
            edges[(vns[-1].name, e.enode.name)] = Edge(vns[-1], e.enode, org_e=e, freq=e.freq)
            for pre, post in zip(vns, vns[1:]):
                edges[(pre.name, post.name)] = Edge(pre, post, org_e=e, freq=e.freq)
            self.virtual_nodes.extend(vns)

        self.nodes.update({v.name: v for v in self.virtual_nodes})
        return Graph(self.nodes, edges)

    def balance_components(self):
        """Distribute the non-backbone components so both sides have similar node counts."""
        comps = self.get_components(exclude_backbone=True, consider_assigned_edge=True)
        comps.sort(key=len, reverse=True)

        right, left = 0, 0
        for c in comps:
            if abs(left - (right + len(c))) <= abs((left + len(c)) - right):
                c.move_to_right()
                right += len(c)
            else:
                c.move_to_left()
                left += len(c)

        self.components = comps
        self.assign_order()
        self.update_order_bounds()

    def assign_order(self):
        for n in self.backbone.nodes.values():
            n.order = 0

        right, left = defaultdict(list), defaultdict(list)
        for c in self.components:
            for n in c.nodes:
                (right if c.is_right else left)[n.rank].append(n)

        for nodes in right.values():
            for i, n in enumerate(nodes):
                n.order = i + 1
        for nodes in left.values():
            for i, n in enumerate(nodes):
                n.order = -(i + 1)

    def set_rank_node(self):
        rank_node = defaultdict(dict)
        for name, n in self.nodes.items():
            rank_node[n.rank][name] = n
        self.rank_node = rank_node

    def set_node_width(self, real_node_width=12, virtual_node_width=30):
        for n in self.nodes.values():
            if n.is_real:
                n.width = max(real_node_width * len(n.name.replace(' ', '')), self.node_width)
            else:
                n.width = virtual_node_width

    def position_node(self):
        self.set_node_width(real_node_width=20)
        center = self.order_width * (abs(self.left_max_order) + 1)
        for n in self.nodes.values():
            n.calculate_node_x_y(center, self.order_width, self.rank_height)
        for e in self.edges.values():
            e.calculate_edge_x_y()

    def get_node_x_left_median(self, xcoord, n, median_value):
        """`median_value`, pushed right so that `n` does not overlap its left neighbour."""
        if not n.left_n:
            return median_value
        left_n = self.nodes[n.left_n]
        left_margin = xcoord[left_n.name] + (left_n.width + n.width) / 2 + self.eps
        return max(median_value, left_margin)

    # ------------------------------------------------------ crossing reduction
    def graph_from_order(self, right_v_r_i, left_v_r_i):
        """Apply the per-rank orders in `right_v_r_i` / `left_v_r_i` to the nodes and position them."""
        nodes = {}
        for r, names in right_v_r_i.items():
            for i, name in enumerate(names):
                nodes[name] = self.nodes[name]
                nodes[name].rank, nodes[name].order = r, i
        for r, names in left_v_r_i.items():
            for i, name in enumerate(names):
                nodes[name] = self.nodes[name]
                nodes[name].rank, nodes[name].order = r, -len(names) + i

        g = Graph(nodes, self.edges)
        g.position_node()
        return g

    def init_order(self):
        """Initial order value per node: 0 for the backbone, order / rank size otherwise."""
        right_v_r_i, left_v_r_i = defaultdict(dict), defaultdict(dict)

        for name, n in self.backbone.nodes.items():
            right_v_r_i[n.rank][name] = 0

        for name, n in (self - self.backbone).nodes.items():
            val = round(n.order / self.get_rank_size(n.rank), 5)
            (right_v_r_i if n.is_right else left_v_r_i)[n.rank][name] = val

        right_v_r_i = self._sorted_order(right_v_r_i)
        left_v_r_i = self._sorted_order(left_v_r_i)
        return self.graph_from_order(right_v_r_i, left_v_r_i), right_v_r_i, left_v_r_i

    @staticmethod
    def _sorted_order(v_r_i):
        return {r: dict(sorted(v_r_i[r].items(), key=lambda x: x[1])) for r in sorted(v_r_i)}

    def wmedian(self, right_v_r_i, left_v_r_i, iteration, downward=True):
        """One weighted-median sweep (only on even iterations) followed by re-positioning."""
        if iteration % 2 == 0:
            step = -1 if downward else 1
            for r in range(1, self.max_rank):
                for v_r_i in (right_v_r_i, left_v_r_i):
                    if r in v_r_i:
                        for name in v_r_i[r]:
                            v_r_i[r][name] = self.median_value(name, r + step)
                        v_r_i[r] = dict(sorted(v_r_i[r].items(), key=lambda x: x[1]))
        self.graph_from_order(right_v_r_i, left_v_r_i)

    def median_value(self, name, adj_rank):
        if self.nodes[name].is_backbone:
            return 0

        P = sorted(self.nodes[m].order for m in self.adj_nodes[name] if self.nodes[m].rank == adj_rank)
        m = len(P) // 2
        eps = 0.0001
        if not P:
            return 1 + eps if self.nodes[name].is_right else -1 - eps
        if len(P) % 2 == 1:
            return P[m]
        if len(P) == 2:
            return (P[0] + P[1]) / 2
        left = P[m - 1] - P[0]
        right = P[-1] - P[m]
        return (P[m - 1] * right + P[m] * left) / (left + right)

    def get_crossing(self):
        """Number of edge crossings between straight-line edges of adjacent ranks.

        Horizontal edges (same rank) spanning several orders are bent through a
        temporary point above/below the rank so they can cross other edges.
        """
        edges = {}
        for key, e in self.edges.items():
            if e.snode.rank == e.enode.rank and abs(e.snode.order - e.enode.order) > 1:
                tick = 0.5 * self.rank_height / max(self.right_max_order, abs(self.left_max_order))
                order_diff = abs(e.snode.order - e.enode.order)
                bend = Node(name=f'bend{len(edges)}', is_real=False, is_backbone=False)
                bend.x = (e.snode.x + e.enode.x) / 2 - 0.5
                if e.snode.order < e.enode.order:
                    bend.y, bend.rank = e.snode.y - tick * order_diff, e.snode.rank - 1
                else:
                    bend.y, bend.rank = e.snode.y + tick * order_diff, e.enode.rank + 1
                e1 = Edge(snode=e.snode, enode=bend, org_e=e.org_e)
                e2 = Edge(snode=bend, enode=e.enode, org_e=e.org_e)
                edges[e1.key], edges[e2.key] = e1, e2
            else:
                edges[key] = e

        crossing = 0
        for key1, e1 in edges.items():
            for key2, e2 in edges.items():
                if key1 == key2:
                    continue
                if min(e1.snode.rank, e1.enode.rank) == min(e2.snode.rank, e2.enode.rank) and e1.is_intersect(e2):
                    crossing += 1
        return int(crossing / 2)

    def minimize_cross(self, max_iteration=20, verbose=True):
        """Weighted-median crossing reduction: downward sweeps, then upward sweeps.

        The node orders (and positions) are updated in place.
        """
        g, right_v_r_i, left_v_r_i = self.init_order()
        if verbose:
            print(f'Edge crossings before minimization: {g.get_crossing()}')

        for downward in (True, False):
            for iteration in range(max_iteration):
                g.wmedian(right_v_r_i, left_v_r_i, iteration, downward=downward)

        if verbose:
            print(f'Edge crossings after minimization: {g.get_crossing()}')
