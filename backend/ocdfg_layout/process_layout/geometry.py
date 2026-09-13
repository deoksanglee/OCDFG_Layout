def _within_segment(a, b, x, y):
    """True if (x, y) lies in the bounding box of segment a-b, excluding its endpoints."""
    if (x, y) == a or (x, y) == b:
        return False
    return min(a[0], b[0]) <= x <= max(a[0], b[0]) and min(a[1], b[1]) <= y <= max(a[1], b[1])


def segments_intersect(a, b, c, d):
    """True if straight segments a-b and c-d cross (shared endpoints do not count).

    Points are (x, y) tuples.
    """
    a1, b1 = b[1] - a[1], a[0] - b[0]
    c1 = a1 * a[0] + b1 * a[1]

    a2, b2 = d[1] - c[1], c[0] - d[0]
    c2 = a2 * c[0] + b2 * c[1]

    det = a1 * b2 - a2 * b1
    if det == 0:  # parallel
        return False
    x = (b2 * c1 - b1 * c2) / det
    y = (a1 * c2 - a2 * c1) / det
    return _within_segment(a, b, x, y) and _within_segment(c, d, x, y)
