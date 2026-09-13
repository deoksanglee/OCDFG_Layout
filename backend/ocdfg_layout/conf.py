# Drawing geometry of the OC-DFG layout (SVG user units).
config = {
    'SVG_WIDTH': 3600,          # the layout is centred in this width
    'RANK_HEIGHT': 400,         # vertical distance between ranks
    'ORDER_WIDTH': 400,         # horizontal distance between order slots (initial placement)
    'NODE_GAP': 100,            # minimum horizontal gap between neighbouring nodes
    'VIRTUAL_NODE_GAP': 20,     # gap between two neighbouring edge bends (virtual nodes)
    'NODE_MIN_WIDTH': 100,      # width reserved for a node (grows with the label length)
    'NODE_CHAR_WIDTH': 12,      # extra width per character of the activity name
    'VIRTUAL_NODE_WIDTH': 30,   # width reserved for a virtual (edge bend) node
    'NODE_HEIGHT': 40,
    'RADIUS': 20,               # radius of a node's per-object-type sub-circle
    'AXIS_SLACK_SLOTS': 2,      # extra order slots per side of every axis for the global crossing reduction
    'EDGE_STRAIGHTENING': 'vertical',  # 'vertical' | 'diagonal' | None (see MultiObjectGraph.straighten_long_edges)
}
