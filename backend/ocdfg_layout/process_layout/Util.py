def collapse_repeats(seq):
    """Collapse directly repeated activities: [a, a, b, a] -> [a, b, a]."""
    collapsed = []
    for item in seq:
        if not collapsed or item != collapsed[-1]:
            collapsed.append(item)
    return collapsed
