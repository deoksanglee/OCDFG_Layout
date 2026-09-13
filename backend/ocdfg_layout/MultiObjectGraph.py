"""Layout of an object-centric directly-follows graph (OC-DFG).

Pipeline (see MultiObjectGraph.generate_layout_from_log):

1. build one node/edge set per object type from the case variants,
2. assign a common rank to every activity with an ILP (Gurobi),
3. lay out each object type on its own vertical axis (process_layout.Graph),
4. merge the axes one by one, choosing the axis position with the fewest
   edge crossings, and
5. place nodes horizontally with a median heuristic and compute the SVG
   coordinates the frontend draws.

`recompute_with_kept_edges` / `recompute_with_filter_value` re-run step 5 on a
filtered copy of the graph and report how far the nodes moved.
"""
import copy
import math
import statistics
import time
from collections import defaultdict

import gurobipy as gp
import numpy as np
import pandas as pd
from gurobipy import GRB

from .conf import config
from .ObjectGraph import ObjectGraph
from .ObjectNode import ObjectNode
from .process_layout.Edge import Edge
from .process_layout.geometry import segments_intersect
from .process_layout.Graph import Graph
from .process_layout.Node import Node
from .process_layout.Util import collapse_repeats

RADIUS = config['RADIUS']

MOVEMENT_KEYS = ['count', 'mean', 'min', 'max', 'scaled_mean', 'scaled_min', 'scaled_max', 'scaled_median']


def compare_node_positions(before_xy, after_xy):
    """Distance statistics between two placements ({name: (x, y)}) of the common nodes.

    Raw distances use the original coordinates; scaled distances normalise x and
    y by their respective maxima first.
    """
    common = set(before_xy) & set(after_xy)
    if not common:
        return {'count': 0, **{k: None for k in MOVEMENT_KEYS[1:]}, 'distances': {}, 'scaled_distances': {}}

    max_x = max(max(before_xy[n][0], after_xy[n][0]) for n in common)
    max_y = max(max(before_xy[n][1], after_xy[n][1]) for n in common)

    distances, scaled_distances = {}, {}
    for name in common:
        (bx, by), (ax, ay) = before_xy[name], after_xy[name]
        distances[name] = math.dist((bx, by), (ax, ay))
        dx = (ax - bx) / max_x if max_x else 0.0
        dy = (ay - by) / max_y if max_y else 0.0
        scaled_distances[name] = math.dist((0.0, 0.0), (dx, dy))

    values, scaled = list(distances.values()), list(scaled_distances.values())
    return {
        'count': len(values),
        'mean': sum(values) / len(values),
        'median': statistics.median(values),
        'min': min(values),
        'max': max(values),
        'scaled_mean': sum(scaled) / len(scaled),
        'scaled_median': statistics.median(scaled),
        'scaled_min': min(scaled),
        'scaled_max': max(scaled),
        'max_x': max_x,
        'max_y': max_y,
        'distances': distances,
        'scaled_distances': scaled_distances,
    }


class MultiObjectGraph(ObjectGraph):
    order_width = config['ORDER_WIDTH']
    rank_height = config['RANK_HEIGHT']
    node_width = config['NODE_MIN_WIDTH']
    node_height = config['NODE_HEIGHT']
    eps = config['NODE_GAP']

    # weights of the axis-position objective in determine_object_type_axis_and_merge
    LAMBDA_EDGE_CROSS = 10
    LAMBDA_AXIS_DIST = 0.3

    def __init__(self, nodes, edges, ogs, object_types=None, object_axis_order=None):
        super().__init__(nodes, edges, object_type=None)
        self.ogs = ogs                                  # {object type: ObjectGraph}
        self.object_types = list(object_types or [])
        self.object_axis_order = list(object_axis_order or [])  # left-to-right axis order
        self.org_e, self.org_e_freq, self.org_e_reverse_freq, self.org_edges = {}, {}, {}, {}

    # ============================================================ entry point
    @classmethod
    def generate_layout_from_log(cls, log):
        seq_df = cls.generate_sequence_df(log)
        object_types = set(seq_df['object_type'].tolist())

        nodes, nodes_by_ot = cls.generate_nodes(seq_df, object_types)
        edges, edges_by_ot = cls.generate_edges(seq_df, object_types, nodes)
        backbone_seq_by_ot = cls.generate_backbones(seq_df, object_types)

        node_rank = cls.assign_rank(nodes, edges)
        for ot_nodes in nodes_by_ot.values():
            for name, n in ot_nodes.items():
                n.rank = node_rank[name]

        ogs = cls.get_object_graph_by_ot(nodes_by_ot, edges_by_ot, backbone_seq_by_ot)
        g, cost1_list, cost2_list = cls.merge_object_graphs(ogs)
        g.dist_rank = cls.dist_rank(ogs)

        g.optimize_axis_order()
        g.minimize_global_crossings()
        g.relayout()
        output = g.output_graph()
        output['cost1'] = cost1_list
        output['cost2'] = cost2_list
        return output, g

    def relayout(self):
        """Horizontal placement + SVG coordinates + edge polylines for the current nodes/edges."""
        self.position_node_heuristic()
        self.calculate_visual_coordinates()
        self.org_e, self.org_e_freq = self.get_org_e()
        self.naive_drawing()

    # ===================================================== log -> nodes/edges
    @classmethod
    def generate_sequence_df(cls, log):
        variants = log['case_variants']
        seq_df = pd.DataFrame({'seq': [v['sequence'] for v in variants],
                               'freq': [v['frequency'] for v in variants],
                               'object_type': [v['object_type'] for v in variants]})
        seq_df['seq'] = seq_df.apply(lambda x: cls.add_se_node(x['seq'], x['object_type']), axis=1)
        seq_df['seq_processed'] = seq_df['seq'].apply(collapse_repeats)
        return seq_df.sort_values(by='freq', ascending=False).reset_index()

    @classmethod
    def add_se_node(cls, seq, ot):
        seq.insert(0, cls.get_start_node_name(ot))
        seq.append(cls.get_end_node_name(ot))
        return seq

    @classmethod
    def get_start_node_name(cls, ot):
        return ot + ' start'

    @classmethod
    def get_end_node_name(cls, ot):
        return ot + ' end'

    @classmethod
    def generate_nodes(cls, seq_df, object_types):
        """Global ObjectNodes (one per activity) and plain Nodes per object type."""
        nodes = {}
        nodes_by_ot = {ot: {} for ot in object_types}
        seq_df = seq_df[seq_df['object_type'].isin(object_types)]

        for seq, ot in zip(seq_df['seq_processed'].tolist(), seq_df['object_type']):
            for i, name in enumerate(seq):
                is_start, is_end = i == 0, i == len(seq) - 1

                if name in nodes:
                    nodes[name].append_object_type(ot)
                else:
                    nodes[name] = ObjectNode(name=name, is_real=True, object_types=[ot],
                                             is_start=is_start or None, is_end=(is_end and not is_start) or None)

                nodes_by_ot[ot][name] = Node(name=name, is_real=True,
                                             is_start=is_start or None, is_end=(is_end and not is_start) or None)

        return nodes, nodes_by_ot

    @classmethod
    def generate_edges(cls, seq_df, object_types, nodes):
        """Directly-follows edges, globally and per object type, with summed frequencies."""
        seq_df = seq_df[seq_df['object_type'].isin(object_types)]
        seq_df = seq_df.sort_values(by='freq', ascending=False).reset_index()

        edges = {}
        edges_by_ot = {ot: {} for ot in object_types}

        def add(store, key, freq):
            if key in store:
                store[key].freq += freq
            else:
                e = Edge(snode=nodes[key[0]], enode=nodes[key[1]], freq=freq)
                e.org_e = e
                store[key] = e

        for ot, group in seq_df.groupby('object_type', as_index=False):
            for _, item in group.reset_index(drop=True).iterrows():
                seq, freq = item['seq_processed'], item['freq']
                for pre, post in zip(seq, seq[1:]):
                    add(edges, (pre, post), freq)
                    add(edges_by_ot[ot], (pre, post), freq)
        return edges, edges_by_ot

    @classmethod
    def generate_backbones(cls, seq_df, object_types):
        """The most frequent variant of every object type."""
        seq_df = seq_df.sort_values(by='freq', ascending=False).reset_index()
        backbone_df = seq_df.groupby('object_type').head(1)
        return {item['object_type']: item['seq'] for _, item in backbone_df.iterrows()
                if item['object_type'] in object_types}

    # ========================================================= rank assignment
    @classmethod
    def assign_rank(cls, N, E):
        """ILP: one integer rank per activity minimising weighted precedence
        violations plus edge length, with every node strictly between the start
        and end node of each of its object types."""
        m = gp.Model('Rank assignment')

        var_a = {key: m.addVar(vtype=GRB.INTEGER, name=f'var_a_{key}') for key in E}   # precedence violation
        var_b = {key: m.addVar(vtype=GRB.BINARY, name=f'var_b_{key}') for key in E}    # direction indicator
        var_x = {name: m.addVar(vtype=GRB.INTEGER, name=f'var_x_{name}', lb=1) for name in N}  # rank
        var_y = {key: m.addVar(vtype=GRB.INTEGER, name=f'var_y_{key}') for key in E}   # edge length

        m.setObjective(gp.quicksum(e.freq * var_a[key] for key, e in E.items())
                       + gp.quicksum(var_y[key] for key in E), GRB.MINIMIZE)

        for (s, t) in E:
            m.addConstr(var_x[s] - var_x[t] - var_a[(s, t)] <= -1)
        for key in E:
            (s, t) = key
            m.addConstr(var_y[key] - var_x[s] + var_x[t] >= 0)
            m.addConstr(var_y[key] + var_x[s] - var_x[t] >= 0)

        ot_start = {n.object_types[0]: n.name for n in N.values() if n.is_start}
        ot_end = {n.object_types[0]: n.name for n in N.values() if n.is_end}
        for n in N.values():
            if not n.is_start and not n.is_end:
                for ot in n.object_types:
                    m.addConstr(var_x[n.name] >= var_x[ot_start[ot]] + 1)
                    m.addConstr(var_x[n.name] + 1 <= var_x[ot_end[ot]])

        eps, M = 1, 3 * len(N) + 1
        for key in E:
            (s, t) = key
            m.addConstr(var_x[s] - var_x[t] + eps - M * var_b[key] <= 0)
            m.addConstr(var_x[s] - var_x[t] - eps + M * (1 - var_b[key]) >= 0)

        start_time = time.time()
        m.optimize()
        print(f'[Rank assignment] Optimize time: {time.time() - start_time:.4f} sec')

        return {name: int(v.X) for name, v in var_x.items()}

    @classmethod
    def merge_reverse_edges(cls, edges):
        """Keep one edge per unordered node pair: A->B and B->A are laid out and drawn as a
        single double-headed edge (the more frequent direction, remembering the other one's
        frequency), so the pair costs one chain of bends and counts as one edge."""
        merged = {}
        for key, e in edges.items():
            reverse = (key[1], key[0])
            if reverse in merged:
                kept = merged[reverse]
                if e.freq > kept.freq:
                    e.reverse_freq = kept.freq
                    del merged[reverse]
                    merged[key] = e
                else:
                    kept.reverse_freq = e.freq
            else:
                merged[key] = e
        return merged

    @classmethod
    def get_object_graph_by_ot(cls, nodes_by_ot, edges_by_ot, backbone_seq_by_ot):
        graph_by_ot = {}
        for ot in nodes_by_ot:
            g = Graph(nodes_by_ot[ot], cls.merge_reverse_edges(edges_by_ot[ot]))
            layout = g.generate_layout(backbone_seq=backbone_seq_by_ot[ot], minimize_cross=True)
            graph_by_ot[ot] = ObjectGraph.from_layout(layout, ot)
        return graph_by_ot

    # ================================================================ merging
    @classmethod
    def merge_object_graphs(cls, ogs):
        """Merge the per-object-type graphs into one, starting from the main object type
        and adding the most similar remaining type each step."""
        main_object_type = cls.get_main_object_type(ogs)
        print('Main object type:', main_object_type)

        mog = cls(nodes=copy.deepcopy(ogs[main_object_type].nodes),
                  edges=copy.deepcopy(ogs[main_object_type].edges),
                  ogs={main_object_type: ogs[main_object_type]},
                  object_types=[main_object_type],
                  object_axis_order=[main_object_type])

        remaining = [ot for ot in ogs if ot != main_object_type]
        dist_rank = cls.dist_rank(ogs)
        cost1_list, cost2_list = [], []

        while remaining:
            nodes_by_ot = {ot: list(ogs[ot].nodes) for ot in ogs if ot in remaining}
            sim_object_type = cls.get_sim_object_type(mog, nodes_by_ot)
            mog, target_axis, cost1, cost2 = cls.determine_object_type_axis_and_merge(mog, ogs[sim_object_type], dist_rank)
            print(f'Merged {sim_object_type} at axis {target_axis}: {mog.object_axis_order}')
            cost1_list.append(cost1)
            cost2_list.append(cost2)
            remaining.remove(sim_object_type)

        mog.init_adj_nodes()
        return mog, cost1_list, cost2_list

    @classmethod
    def get_main_object_type(cls, ogs):
        """Object type sharing the most activities with the others (ties: longer rank span,
        higher max rank, more edges; first one wins)."""
        if not ogs:
            raise ValueError('At least one object type is needed')

        def shared_nodes(target):
            target_nodes = set(ogs[target].nodes)
            shared = set()
            for ot in ogs:
                if ot != target:
                    shared |= target_nodes & set(ogs[ot].nodes)
            return len(shared)

        def key(ot):
            og = ogs[ot]
            return (shared_nodes(ot), og.max_rank - og.min_rank, og.max_rank, len(og.edges))

        return max(ogs, key=key)

    @classmethod
    def get_sim_object_type(cls, mog, nodes_by_ot):
        """Remaining object type whose node set is closest to the merged graph (last one on ties)."""
        best, best_dist = None, 1
        for ot, nodes_b in nodes_by_ot.items():
            d = cls.dist(list(mog.nodes), nodes_b)
            if d <= best_dist:
                best, best_dist = ot, d
        return best

    @classmethod
    def dist(cls, nodes_a, nodes_b):
        """1 - Dice similarity of two node-name collections."""
        shared = len(set(nodes_a) & set(nodes_b))
        return 1 - (2 * shared) / (len(nodes_a) + len(nodes_b))

    @classmethod
    def dist_rank(cls, ogs):
        """Rank (1 = closest) of the distance between every pair of object types,
        keyed 'A-B' and 'B-A'."""
        o_types = list(ogs)
        pairs, dists = [], []
        for i, ot_a in enumerate(o_types):
            for ot_b in o_types[i + 1:]:
                nodes_a = {name for name, n in ogs[ot_a].nodes.items() if n.is_real}
                nodes_b = {name for name, n in ogs[ot_b].nodes.items() if n.is_real}
                pairs.append('-'.join([ot_a, ot_b]))
                dists.append(cls.dist(nodes_a, nodes_b))

        df = pd.DataFrame({'ots': pairs, 'dist': dists})
        df['dist_rank'] = df['dist'].rank(method='max')
        ranks = df[['ots', 'dist_rank']].set_index('ots').to_dict()['dist_rank']

        for key, val in list(ranks.items()):
            ot_a, ot_b = key.split('-')[0], key.split('-')[1]
            ranks['-'.join([ot_b, ot_a])] = val
        return ranks

    @classmethod
    def determine_object_type_axis_and_merge(cls, mog, og, dist_rank):
        """Try every axis position for `og` and keep the merge with the lowest cost."""
        target_mog, target_axis, target_metric = None, None, float('inf')

        for axis in range(len(mog.object_axis_order) + 1):
            candidate = cls.merge(mog, og, axis)
            candidate.calculate_coordinates(calculate_global_order=True)

            n_edges = len(candidate.edges)
            edge_cross_cost = candidate.get_crossing() / (n_edges * (n_edges - 1) / 2)
            axis_dist_cost = cls.get_object_type_axis_dist(candidate)

            metric = cls.LAMBDA_EDGE_CROSS * edge_cross_cost + cls.LAMBDA_AXIS_DIST * axis_dist_cost
            if metric < target_metric:
                target_mog, target_axis, target_metric = candidate, axis, metric

        target_mog.calculate_coordinates()
        # NOTE: the reported costs are those of the last candidate tried (kept for
        # compatibility with the recorded cost1/cost2 output), not of the chosen axis.
        return target_mog, target_axis, axis_dist_cost, edge_cross_cost

    @classmethod
    def merge(cls, mog, og, axis):
        """Copy of `mog` with `og` inserted as the `axis`-th vertical axis."""
        mog, og = copy.deepcopy(mog), copy.deepcopy(og)
        mog.object_axis_order.insert(axis, og.object_type)
        mog.object_types.insert(axis, og.object_type)

        shared = set(mog.nodes) & set(og.nodes)
        for name in shared:
            n = mog.nodes[name]
            # keep n.object_types in axis order
            types_in_axis_order = [ot for ot in mog.object_axis_order if ot in set(n.object_types) | {og.object_type}]
            n.insert_object_type(og.object_type, types_in_axis_order.index(og.object_type))

        mog.add_nodes({name: n for name, n in og.nodes.items() if name not in shared})
        mog.add_edges(og.edges)
        mog.ogs[og.object_type] = og
        return mog

    @classmethod
    def get_object_type_axis_dist(cls, mog):
        """Stress between the node-set distance ranks of the object types and the
        ranks of the distances between their axis centroids (0 for <= 2 axes)."""
        if len(mog.object_axis_order) <= 2:
            return 0

        dist_rank = cls.dist_rank(mog.ogs)

        xs_by_ot = defaultdict(list)
        for n in mog.nodes.values():
            for ot in n.object_types:
                xs_by_ot[ot].append([n.x])
        centroid_by_ot = {ot: np.mean(np.reshape(xs, (len(xs), -1)), axis=0) for ot, xs in xs_by_ot.items()}

        ots = list(centroid_by_ot)
        pairs, diffs = [], []
        for i, ot_a in enumerate(ots):
            for ot_b in ots[i + 1:]:
                pairs.append('-'.join([ot_a, ot_b]))
                diffs.append(math.dist(centroid_by_ot[ot_a], centroid_by_ot[ot_b]))

        df = pd.DataFrame({'ot': pairs, 'centroid_diff': diffs})
        df['centroid_diff'] = (df['centroid_diff'] - df['centroid_diff'].min()) / (max(df['centroid_diff']) - min(df['centroid_diff']))
        df['centroid_diff'] = df['centroid_diff'].rank(method='max')
        centroid_rank = df.set_index('ot').to_dict()['centroid_diff']

        a = sum((dist_rank[p] - centroid_rank[p]) ** 2 for p in pairs)
        b = sum(dist_rank[p] ** 2 for p in pairs)
        return math.sqrt(a / b)

    def add_nodes(self, nodes):
        for n in nodes.values():
            self.nodes[n.name] = copy.deepcopy(n)

    def add_edges(self, edges):
        for e in edges.values():
            self.edges[e.key] = copy.deepcopy(e)

    # ============================================= global crossing reduction
    def _axis_metric(self):
        """The merge-step cost of the current axis order (see determine_object_type_axis_and_merge)."""
        self.calculate_coordinates(calculate_global_order=True)
        n_edges = len(self.edges)
        edge_cross_cost = self.get_crossing() / (n_edges * (n_edges - 1) / 2)
        return self.LAMBDA_EDGE_CROSS * edge_cross_cost + self.LAMBDA_AXIS_DIST * self.get_object_type_axis_dist(self)

    def optimize_axis_order(self, verbose=True):
        """After the greedy merge, swap adjacent axes while that lowers the merge cost.
        The greedy step fixes each axis position when the type is added; later types can
        make another order better, which this pass picks up."""
        best = self._axis_metric()
        if verbose:
            print(f'[Axis order] cost before: {best:.4f} {self.object_axis_order}')
        improved = True
        while improved:
            improved = False
            for i in range(len(self.object_axis_order) - 1):
                order = self.object_axis_order
                order[i], order[i + 1] = order[i + 1], order[i]
                m = self._axis_metric()
                if m < best - 1e-9:
                    best, improved = m, True
                else:
                    order[i], order[i + 1] = order[i + 1], order[i]
        self.object_types = list(self.object_axis_order)
        for n in self.nodes.values():        # sub-circles follow the axis order
            n.object_types.sort(key=self.object_axis_order.index)
        self.calculate_coordinates(calculate_global_order=True)
        if verbose:
            print(f'[Axis order] cost after:  {best:.4f} {self.object_axis_order}')

    def minimize_global_crossings(self, max_iteration=20, verbose=True):
        """Reduce edge crossings of the merged graph by re-ordering nodes within each rank.

        A non-backbone node may take any free slot of its own object-type axis on its rank
        (either side of the backbone) or swap with another non-backbone node of that axis,
        so the axis order, the axis widths and the backbone columns stay as merged.
        Weighted-median sweeps (down, then up) are followed by single-node moves that are
        kept only when they lower the crossing count; the best order seen is returned.
        """
        ranks = sorted({n.rank for n in self.nodes.values()})

        # Slots every axis may use on any rank: its merged width plus `slack` extra columns on
        # each side (so bends can move next to the backbone even when the per-type layout
        # was narrower), except the backbone column.  Global orders are renumbered so the
        # widened axes still follow each other without overlapping.
        slack = config.get('AXIS_SLACK_SLOTS', 0)
        axis_slots, shift = {}, 0
        for ot in self.object_axis_order:
            og, backbone_slot = self.ogs[ot], self.get_object_type_order(ot)
            first, width = backbone_slot - abs(og.left_max_order), og.get_graph_width_order()
            for n in self.nodes.values():
                if n.object_axis == ot:
                    n.global_order += shift + slack
            new_first, new_backbone = first + shift, backbone_slot + shift + slack
            axis_slots[ot] = [slot for slot in range(new_first, new_first + width + 2 * slack) if slot != new_backbone]
            shift += 2 * slack

        groups = {}
        for n in self.nodes.values():
            if not n.is_backbone and n.object_axis in axis_slots:
                groups.setdefault((n.rank, n.object_axis), []).append(n)

        # adjacent-rank edges as (lower node, upper node) pairs, by lower rank
        by_rank = {r: [] for r in ranks}
        for e in self.edges.values():
            a, b = self.nodes[e.snode.name], self.nodes[e.enode.name]   # edge endpoints are copies
            if abs(a.rank - b.rank) == 1:
                lo, hi = (a, b) if a.rank < b.rank else (b, a)
                by_rank[lo.rank].append((lo, hi, self.edge_multiplicity(e)))

        def crossings_between(r):
            """Crossings among the edges between rank r and r + 1."""
            total, pairs = 0, by_rank.get(r, [])
            for i in range(len(pairs)):
                a1, b1, w1 = pairs[i]
                for j in range(i + 1, len(pairs)):
                    a2, b2, w2 = pairs[j]
                    if (a1.global_order - a2.global_order) * (b1.global_order - b2.global_order) < 0:
                        total += w1 * w2
            return total

        def crossings():
            return sum(crossings_between(r) for r in ranks)

        def crossings_around(r):
            """Only the crossings a node on rank r can influence."""
            return crossings_between(r - 1) + crossings_between(r)

        def free_slots(key, exclude=None):
            r, ot = key
            used = {m.global_order for m in groups[key] if m is not exclude}
            return [slot for slot in axis_slots[ot] if slot not in used]

        backbone_slot = {}
        for ot in self.object_axis_order:
            backbone_slot[ot] = next(n.global_order for n in self.nodes.values() if n.is_backbone and n.object_axis == ot)

        def median_sweep(adj_rank_offset):
            """Sort the nodes of every (rank, axis) group by the median slot of their
            neighbours on the adjacent rank (ties: the other adjacent rank) and pack them
            next to the backbone: nodes wanted left of it on the left, the rest on the right."""
            for key, ns in groups.items():
                r, ot = key
                def median_at(n, offset):
                    xs = sorted(self.nodes[m].global_order for m in self.adj_nodes.get(n.name, [])
                                if self.nodes[m].rank == r + offset)
                    return statistics.median(xs) if xs else None
                wanted = {}
                for n in ns:
                    primary, secondary = median_at(n, adj_rank_offset), median_at(n, -adj_rank_offset)
                    if primary is None:
                        primary = secondary if secondary is not None else n.global_order
                    if secondary is None:
                        secondary = primary
                    wanted[n.name] = (primary, secondary)
                bb = backbone_slot[ot]
                left = sorted([n for n in ns if wanted[n.name] < (bb, bb)], key=lambda n: wanted[n.name])
                right = sorted([n for n in ns if wanted[n.name] >= (bb, bb)], key=lambda n: wanted[n.name])
                left_slots = sorted(slot for slot in axis_slots[ot] if slot < bb)
                right_slots = sorted(slot for slot in axis_slots[ot] if slot > bb)
                # more nodes than slots on a side: overflow goes to the other side, keeping the order
                while len(left) > len(left_slots):
                    right.insert(0, left.pop())
                while len(right) > len(right_slots):
                    left.append(right.pop(0))
                for n, slot in zip(left, left_slots[len(left_slots) - len(left):]):
                    n.global_order = slot
                for n, slot in zip(right, right_slots[:len(right)]):
                    n.global_order = slot

        def nearest_slot_sweep(adj_rank_offset):
            """Alternative sweep: every node takes the free slot of its axis closest to the
            median slot of its neighbours on the adjacent rank."""
            for key, ns in groups.items():
                r, ot = key
                def desired(n):
                    xs = sorted(self.nodes[m].global_order for m in self.adj_nodes.get(n.name, [])
                                if self.nodes[m].rank == r + adj_rank_offset)
                    return statistics.median(xs) if xs else n.global_order
                wanted = {n.name: desired(n) for n in ns}
                for n in ns:
                    n.global_order = None
                for n in sorted(ns, key=lambda n: wanted[n.name]):
                    free = [slot for slot in axis_slots[ot] if slot not in {m.global_order for m in ns}]
                    n.global_order = min(free, key=lambda slot: (abs(slot - wanted[n.name]), slot))

        def local_moves():
            improved = True
            while improved:
                improved = False
                for key, ns in groups.items():
                    r = key[0]
                    for n in ns:
                        before = crossings_around(r)
                        original = n.global_order
                        # try every free slot ...
                        for slot in free_slots(key, exclude=n):
                            if slot == original:
                                continue
                            n.global_order = slot
                            c = crossings_around(r)
                            if c < before:
                                before, original, improved = c, slot, True
                        n.global_order = original
                        # ... and swapping with every other node of the group
                        for m in ns:
                            if m is n:
                                continue
                            n.global_order, m.global_order = m.global_order, n.global_order
                            c = crossings_around(r)
                            if c < before:
                                before, original, improved = c, n.global_order, True
                            else:
                                n.global_order, m.global_order = m.global_order, n.global_order

        # bend chains (virtual nodes of one original edge) that can move as a whole
        chains = []
        for chain in self.get_org_e()[0].values():
            bends = [self.nodes[v.name] for v in chain[1:-1]]
            bends = [n for n in bends if not n.is_real and not n.is_backbone and n.object_axis in axis_slots]
            if len(bends) > 1 and len({n.object_axis for n in bends}) == 1:
                chains.append(bends)

        def chain_moves():
            """Try to put every bend of a chain on the same side of its backbone (left or right,
            each bend on the free slot nearest the backbone).  Single-node moves cannot find
            this when it needs several ranks to change together."""
            for bends in chains:
                ot = bends[0].object_axis
                bb = backbone_slot[ot]
                original = [n.global_order for n in bends]
                ranks_touched = {n.rank for n in bends}
                def score():
                    return sum(crossings_between(r) for r in {rr for r in ranks_touched for rr in (r - 1, r)})
                best_score, best_slots = score(), original
                # on a tie, prefer one consistent side (the one most bends already use)
                if sum(1 for slot in original if slot > bb) * 2 >= len(original):
                    sides = (1, -1)
                else:
                    sides = (-1, 1)
                for side in sides:
                    slots = []
                    for n in bends:
                        used = {m.global_order for m in groups[(n.rank, ot)] if m is not n}
                        candidates = [slot for slot in axis_slots[ot] if (slot - bb) * side > 0 and slot not in used]
                        if not candidates:
                            slots = None
                            break
                        slots.append(min(candidates, key=lambda slot: abs(slot - bb)))
                    if slots is None:
                        continue
                    for n, slot in zip(bends, slots):
                        n.global_order = slot
                    sc = score()
                    consistent_now = len({slot > bb for slot in best_slots}) == 1
                    if sc < best_score or (sc == best_score and not consistent_now):
                        best_score, best_slots = sc, slots
                for n, slot in zip(bends, best_slots):
                    n.global_order = slot

        best = {n.name: n.global_order for n in self.nodes.values()}
        best_cross = crossings()
        if verbose:
            print(f'[Global] Edge crossings before minimization: {best_cross}')
        for i in range(max_iteration):
            # alternate direction and, every second pass, the placement strategy
            (median_sweep if (i // 2) % 2 == 0 else nearest_slot_sweep)(-1 if i % 2 == 0 else 1)
            local_moves()
            chain_moves()
            local_moves()
            c = crossings()
            if c < best_cross:
                best_cross, best = c, {n.name: n.global_order for n in self.nodes.values()}
        for n in self.nodes.values():
            n.global_order = best[n.name]
        if verbose:
            print(f'[Global] Edge crossings after minimization: {best_cross}')

    # ============================================================ coordinates
    def get_object_type_order(self, object_type):
        """Global order slot where the axis of `object_type` starts."""
        index = self.object_axis_order.index(object_type)
        order = sum(self.ogs[ot].get_graph_width_order() for ot in self.object_axis_order[:index])
        return order + abs(self.ogs[object_type].left_max_order)

    @classmethod
    def get_axis_x_coord(cls, global_order):
        return cls.order_width * (global_order + 1)

    @classmethod
    def get_node_y_coord(cls, rank):
        return cls.rank_height * rank

    @staticmethod
    def offset_x_for_object_type(x, object_axis, object_types, cur_object_type):
        """x of the sub-circle of `cur_object_type`, shifted from the node centre `x`
        by its distance from the axis type in `object_types`."""
        relative_pos = object_types.index(cur_object_type) - object_types.index(object_axis)
        return x + 2 * RADIUS * relative_pos

    def calculate_coordinates(self, calculate_global_order=False):
        """Grid coordinates from (global order, rank); used while choosing axis positions."""
        for n in self.nodes.values():
            if calculate_global_order:
                n.global_order = self.get_object_type_order(n.object_axis) + n.order
            n.x = self.get_axis_x_coord(n.global_order)
            n.y = self.get_node_y_coord(n.rank)
            for ot in n.object_types:
                n.nodes_visualized[ot] = {
                    'x': self.offset_x_for_object_type(n.x, n.object_axis, n.object_types, ot),
                    'y': n.y,
                    'r': RADIUS,
                    'objectType': ot,
                }
        self._set_edge_endpoints(y_offset=0)

    def calculate_visual_coordinates(self):
        """Final SVG coordinates from the heuristic x positions (see position_node_heuristic)."""
        for n in self.nodes.values():
            for ot in n.object_types:
                n.nodes_visualized[ot] = {
                    'x': self.offset_x_for_object_type(n.x, n.object_axis, n.object_types, ot),
                    'y': self.get_node_y_coord(n.rank),
                    'r': RADIUS,
                    'objectType': ot,
                }
        self._set_edge_endpoints(y_offset=-RADIUS)

    def _set_edge_endpoints(self, y_offset):
        for e in self.edges.values():
            s = self.nodes[e.snode.name].nodes_visualized[e.object_type]
            t = self.nodes[e.enode.name].nodes_visualized[e.object_type]
            e.x1, e.y1 = s['x'], s['y'] + y_offset
            e.x2, e.y2 = t['x'], t['y'] + y_offset

    @staticmethod
    def edge_multiplicity(e):
        """A folded A<->B pair stands for two directed edges (see merge_reverse_edges)."""
        return 2 if getattr(e.org_e, 'reverse_freq', None) is not None else 1

    def get_crossing(self):
        """Number of crossings among the straight edges (x1, y1)-(x2, y2); a crossing
        with a double-headed edge counts once per direction."""
        edges = list(self.edges.values())
        cross_num = 0
        for e1 in edges:
            for e2 in edges:
                if e1.key != e2.key and segments_intersect((e1.x1, e1.y1), (e1.x2, e1.y2), (e2.x1, e2.y1), (e2.x2, e2.y2)):
                    cross_num += self.edge_multiplicity(e1) * self.edge_multiplicity(e2)
        return cross_num / 2

    # ================================================= horizontal placement
    def position_node_heuristic(self, max_iteration=20):
        """Place nodes horizontally: start from the axis order, then repeatedly move
        every non-backbone node to the median x of its neighbours without overlaps."""
        self.set_node_width(real_node_width=config['NODE_CHAR_WIDTH'],
                            virtual_node_width=config['VIRTUAL_NODE_WIDTH'])
        for n in self.nodes.values():
            n.height = self.node_height
        self.set_node_left_right()
        xcoord, ycoord = self.init_coord()

        for _ in range(max_iteration):
            self.medianpos(xcoord)
        self.medianpos(xcoord, downward_only=True)
        self.straighten_long_edges(xcoord)

        for name, x in xcoord.items():
            self.nodes[name].x = x
        for name, y in ycoord.items():
            self.nodes[name].y = y

        self.center_layout_x()

    def set_node_left_right(self):
        """Link each node to its left/right neighbour on the same rank (by global order)."""
        self.set_rank_node()
        for rank_nodes in self.rank_node.values():
            ordered = sorted(rank_nodes.values(), key=lambda n: n.global_order)
            for prev_n, post_n in zip(ordered, ordered[1:]):
                self.nodes[prev_n.name].right_n = post_n.name
                self.nodes[post_n.name].left_n = prev_n.name

    def init_coord(self):
        """Initial x per global-order column (left to right, no overlap) and y from rank."""
        xcoord, ycoord = {}, {}
        for name, n in self.nodes.items():
            ycoord[name] = self.rank_height * n.rank

        nodes_by_order = defaultdict(list)
        for n in self.nodes.values():
            nodes_by_order[n.global_order].append(n)

        for _, nodes in sorted(nodes_by_order.items()):
            left_most_x = max([self.order_width / 2] + [self.get_node_x_left_median(xcoord, n, 0) for n in nodes])
            for n in nodes:
                xcoord[n.name] = left_most_x
        return xcoord, ycoord

    def _gap(self, a, b):
        """Minimum horizontal gap between two neighbouring nodes (smaller between edge bends)."""
        return config['VIRTUAL_NODE_GAP'] if (not a.is_real and not b.is_real) else self.eps

    def get_node_x_median(self, xcoord, n, median_value):
        """`median_value` clamped so that `n` does not overlap its left/right neighbours."""
        left_margin = -float('inf')
        if n.left_n:
            left_n = self.nodes[n.left_n]
            left_margin = xcoord[left_n.name] + left_n.width + self._gap(left_n, n)
        right_margin = float('inf')
        if n.right_n:
            right_margin = xcoord[n.right_n] - n.width - self._gap(n, self.nodes[n.right_n])

        if median_value < left_margin:
            return left_margin
        if median_value > right_margin:
            return right_margin
        return median_value

    def _neighbor_edge_freq_sum(self, n, neighbors):
        total = 0
        for adj_n in neighbors:
            for ot in self.object_types:
                for key in ((n.name, adj_n.name, ot), (adj_n.name, n.name, ot)):
                    if key in self.edges:
                        total += self.edges[key].freq
        return total

    def get_down_up_ward_priority(self):
        """Per node: summed frequency of edges to the rank below / above."""
        downward = {n.name: self._neighbor_edge_freq_sum(n, self.get_downward_neighbors(n)) for n in self.nodes.values()}
        upward = {n.name: self._neighbor_edge_freq_sum(n, self.get_upward_neighbors(n)) for n in self.nodes.values()}
        return downward, upward

    def medianpos(self, xcoord, downward_only=False):
        """One sweep moving non-backbone nodes to the median x of their lower neighbours,
        first in downward-priority order and then (unless `downward_only`) in upward order."""
        downward_priority, upward_priority = self.get_down_up_ward_priority()
        sweeps = [sorted(self.nodes.values(), key=lambda n: (downward_priority[n.name], n.rank), reverse=True)]
        if not downward_only:
            sweeps.append(sorted(self.nodes.values(), key=lambda n: (upward_priority[n.name], -n.rank), reverse=True))

        for ordered_nodes in sweeps:
            for n in ordered_nodes:
                if n.is_backbone:
                    continue
                positions = [xcoord[adj_n.name] for adj_n in self.get_downward_neighbors(n)]
                if positions:
                    xcoord[n.name] = self.get_node_x_median(xcoord, n, np.median(positions))

    def straighten_long_edges(self, xcoord, iterations=5):
        """Straighten every multi-rank edge (chain of virtual nodes between two real nodes).

        config['EDGE_STRAIGHTENING']:
          'vertical' - the bends are aligned on one vertical line (the median of their x),
                       so the edge runs straight down between its two endpoints;
          'diagonal' - the bends are put on the straight line between the endpoints;
          None       - leave the median-heuristic positions.
        Neighbours on the same rank are pushed aside; only backbone nodes stay fixed.
        """
        mode = config.get('EDGE_STRAIGHTENING')
        if not mode:
            return
        chains = [chain for chain in self.get_org_e()[0].values() if len(chain) > 2]
        for _ in range(iterations):
            for chain in chains:
                s, t = chain[0], chain[-1]
                if t.rank == s.rank:
                    continue
                bends = [self.nodes[v.name] for v in chain[1:-1] if not self.nodes[v.name].is_real]
                if not bends:
                    continue
                if mode == 'vertical':
                    x_line = statistics.median(xcoord[n.name] for n in bends)
                for n in bends:
                    if mode == 'vertical':
                        target = x_line
                    else:
                        target = xcoord[s.name] + (xcoord[t.name] - xcoord[s.name]) * (n.rank - s.rank) / (t.rank - s.rank)
                    self._move_with_push(xcoord, n, target)

    def _move_with_push(self, xcoord, n, target):
        """Move `n` to x = target, shifting non-backbone neighbours on its rank out of the way.
        If a backbone node blocks, `n` stops right next to the pushed pack."""
        gap = self._gap

        def chain(first, step):
            nodes = []
            while first:
                nodes.append(self.nodes[first])
                first = getattr(nodes[-1], step)
            return nodes

        if target < xcoord[n.name]:
            pos, prev, pushed = target, n, []          # pos: left edge of `prev`
            for m in chain(n.left_n, 'left_n'):
                if xcoord[m.name] + m.width + gap(m, prev) <= pos:
                    break
                if m.is_backbone:
                    target += (xcoord[m.name] + m.width + gap(m, prev)) - pos
                    break
                pushed.append(m)
                pos -= m.width + gap(m, prev)
                prev = m
            xcoord[n.name] = target
            right = n
            for m in pushed:
                xcoord[m.name] = min(xcoord[m.name], xcoord[right.name] - m.width - gap(m, right))
                right = m
        elif target > xcoord[n.name]:
            pos, prev, pushed = target + n.width, n, []  # pos: right edge of `prev`
            for m in chain(n.right_n, 'right_n'):
                if xcoord[m.name] >= pos + gap(prev, m):
                    break
                if m.is_backbone:
                    target -= (pos + gap(prev, m)) - xcoord[m.name]
                    break
                pushed.append(m)
                pos += gap(prev, m) + m.width
                prev = m
            xcoord[n.name] = target
            left = n
            for m in pushed:
                xcoord[m.name] = max(xcoord[m.name], xcoord[left.name] + left.width + gap(left, m))
                left = m

    def center_layout_x(self):
        """Shift the whole layout so it is centred in the configured SVG width."""
        if not self.nodes:
            return
        min_x = min(n.x - n.width / 2 for n in self.nodes.values())
        max_x = max(n.x + n.width / 2 for n in self.nodes.values())
        shift = config['SVG_WIDTH'] / 2 - (min_x + max_x) / 2

        for n in self.nodes.values():
            n.x += shift
        for e in self.edges.values():
            if e.x1 is not None:
                e.x1 += shift
            if e.x2 is not None:
                e.x2 += shift

    # ============================================================ edge paths
    def get_org_e(self):
        """Node chains of the original edges, keyed (source, target, object type):
        the real endpoints plus the virtual nodes in between, top to bottom."""
        org_edges, org_edges_freq = {}, {}
        for e in sorted(self.edges.values(), key=lambda x: x.snode.rank):
            snode_name, enode_name = e.org_e.key
            key = (snode_name, enode_name, e.object_type)
            self.org_e_reverse_freq[key] = getattr(e.org_e, 'reverse_freq', None)

            if e.snode.rank < e.enode.rank:        # forward segment
                org_edges.setdefault(key, [e.snode]).append(e.enode)
            elif e.snode.rank > e.enode.rank:      # backward segment
                org_edges.setdefault(key, [e.enode]).insert(0, e.snode)
            else:
                org_edges[key] = [e.snode, e.enode]
            org_edges_freq[key] = e.freq
        return org_edges, org_edges_freq

    def naive_drawing(self):
        """Polyline through the sub-circle centres of each original edge's node chain.

        The endpoints are the node centres: the frontend draws nodes on top of the
        edges and shortens the last segment for the arrowhead, so the stroke never
        shows a gap at the circle border regardless of its width or angle.
        """
        edges = {}
        for key, chain in self.org_e.items():
            ot = key[2]
            data = [[self.nodes[n.name].nodes_visualized[ot]['x'], self.nodes[n.name].nodes_visualized[ot]['y']]
                    for n in chain]
            edges[key] = {'freq': self.org_e_freq[key], 'reverse_freq': self.org_e_reverse_freq.get(key),
                          'data': data, 'object_type': ot}
        self.org_edges = edges

    # ================================================================ output
    def add_sub_nodes(self):
        for n in self.nodes.values():
            unit_width = n.width / len(n.object_types)
            n.sub_nodes = [{'x': n.x + unit_width * i, 'y': n.y, 'width': unit_width,
                            'height': n.height, 'object_type': ot}
                           for i, ot in enumerate(n.object_types)]

    def output_graph(self):
        """Serialisable layout for the frontend."""
        edge_crosses = self.get_crossing()
        self.add_sub_nodes()

        nodes = {name: {
            'name': name,
            'is_real': n.is_real,
            'is_backbone': n.is_backbone,
            'is_start': n.is_start,
            'is_end': n.is_end,
            'x': n.x,
            'y': n.y,
            'rank': n.rank,
            'order': n.global_order,
            'object_types': n.object_types,
            'object_axis': n.object_axis,
            'nodes_visualized': n.nodes_visualized,
            'width': n.width,
            'height': n.height,
            'sub_nodes': n.sub_nodes,
        } for name, n in self.nodes.items()}

        edges = {}
        for (s, t, _), e in self.org_edges.items():
            key = '-'.join([s, t, e['object_type']])
            edges[key] = {'key': key, 'source': s, 'target': t, 'data': e['data'],
                          'object_type': e['object_type'], 'freq': e['freq'],
                          'reverse_freq': e.get('reverse_freq')}   # set when B->A is folded into this edge
        freqs = [e['freq'] for e in self.org_edges.values()]

        max_n = max(self.nodes.values(), key=lambda n: n.x)
        return {
            'objectTypes': list(self.ogs),
            'nodes': nodes,
            'edges': edges,
            'object_axis_order': self.object_axis_order,
            'svg_width': max_n.x + max_n.width + 20,
            'svg_height': self.rank_height * (self.max_rank + 2),
            'node_width': self.node_width,
            'node_height': self.node_height,
            'radius': RADIUS,
            'edge_crosses': edge_crosses,
            'maxFreq': max(freqs, default=0),
            'minFreq': min(freqs, default=float('inf')),
        }

    # ============================================================ filtering
    def filter_edges_by_percentage(self, percentage, edges=None):
        """Top `percentage` (0..1) of `edges` (default: all) by frequency.  Edges whose
        frequency equals the highest removed frequency are removed too, but at least
        the most frequent edge(s) are always kept."""
        if not 0.0 <= percentage <= 1.0:
            raise ValueError('percentage must be between 0 and 1')
        if edges is None:
            edges = self.edges

        sorted_edges = sorted(edges.values(), key=lambda e: e.freq, reverse=True)
        num_keep = max(1, int(len(sorted_edges) * percentage))
        kept, removed = sorted_edges[:num_keep], sorted_edges[num_keep:]

        if removed:
            boundary_freq = removed[0].freq
            kept = [e for e in kept if e.freq > boundary_freq]
            if not kept:
                kept = [e for e in sorted_edges if e.freq == sorted_edges[0].freq]
        return {e.key: e for e in kept}

    def _keep_edges(self, edges):
        """Restrict the graph to `edges` and drop nodes / object types no longer used."""
        self.edges = edges

        used = {name for e in self.edges.values() for name in (e.snode.name, e.enode.name)}
        self.nodes = {name: n for name, n in self.nodes.items() if name in used}

        remaining_ots = {e.object_type for e in self.edges.values()}
        for n in self.nodes.values():
            n.object_types = [ot for ot in n.object_types if ot in remaining_ots]
            n.nodes_visualized = {ot: v for ot, v in n.nodes_visualized.items() if ot in remaining_ots}
            if n.object_axis not in remaining_ots:
                n.object_axis = n.object_types[0] if n.object_types else None
        self.object_axis_order = [ot for ot in self.object_axis_order if ot in remaining_ots]
        self.object_types = [ot for ot in self.object_types if ot in remaining_ots]
        self.ogs = {ot: og for ot, og in self.ogs.items() if ot in remaining_ots}

        for n in self.nodes.values():
            if n.left_n not in self.nodes:
                n.left_n = None
            if n.right_n not in self.nodes:
                n.right_n = None
        self.adj_nodes = {name: [adj for adj in adj_list if adj in self.nodes]
                          for name, adj_list in self.adj_nodes.items() if name in self.nodes}

    def _recompute(self, edges):
        """Re-run the placement on the filtered graph and report node movement."""
        def real_positions():
            return {name: (n.x, n.y) for name, n in self.nodes.items()
                    if n.is_real and not n.is_start and not n.is_end}

        before_xy = real_positions()
        self._keep_edges(edges)
        self.relayout()
        movement = compare_node_positions(before_xy, real_positions())

        if movement['count'] > 0:
            print('Node movement (raw)    - count: {}, mean: {:.2f}, min: {:.2f}, max: {:.2f}'.format(
                movement['count'], movement['mean'], movement['min'], movement['max']))
            print('Node movement (scaled) - mean: {:.4f}, min: {:.4f}, max: {:.4f}'.format(
                movement['scaled_mean'], movement['scaled_min'], movement['scaled_max']))
        else:
            print('Node movement - no common nodes')

        output = self.output_graph()
        output['movement'] = {k: movement[k] for k in MOVEMENT_KEYS}
        return output

    def recompute_with_kept_edges(self, kept_edge_keys):
        """Keep only the edges whose string key ('s-t-ot') is in `kept_edge_keys`."""
        kept = set(kept_edge_keys)
        return self._recompute({key: e for key, e in self.edges.items() if e.get_string_key() in kept})

    def recompute_with_filter_value(self, filter_value):
        """Keep the top `filter_value` percent (0..100) of edges by frequency."""
        return self.recompute_filtered(filter_value=filter_value)

    def recompute_filtered(self, object_types=None, filter_value=None):
        """Keep only the edges of `object_types` (None = all) and, within those, the top
        `filter_value` percent by frequency (None = all)."""
        edges = self.edges
        if object_types is not None:
            keep = set(object_types)
            edges = {key: e for key, e in edges.items() if e.object_type in keep}
        if filter_value is not None and filter_value < 100:
            edges = self.filter_edges_by_percentage(filter_value / 100.0, edges)
        if not edges:
            raise ValueError('no edges left after filtering')
        return self._recompute(edges)
