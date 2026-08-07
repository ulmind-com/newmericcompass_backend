from app.schemas.vastu import Direction

# Upper bound (exclusive) of each 45-degree sector, walking clockwise from North.
# North is split across the 337.5-360 and 0-22.5 ranges, so it appears twice:
# once as the first bucket and once as the wrap-around bucket at 360.
_DIRECTION_UPPER_BOUNDS: list[tuple[float, Direction]] = [
    (22.5, Direction.NORTH),
    (67.5, Direction.NORTH_EAST),
    (112.5, Direction.EAST),
    (157.5, Direction.SOUTH_EAST),
    (202.5, Direction.SOUTH),
    (247.5, Direction.SOUTH_WEST),
    (292.5, Direction.WEST),
    (337.5, Direction.NORTH_WEST),
    (360.0, Direction.NORTH),
]


def get_vastu_direction(degree: float) -> Direction:
    """Map a compass bearing (degrees clockwise from North) to a Vastu direction.

    Handles the full 0-360 range, including negative/overflowing input and the
    North wrap-around (e.g. 355 degrees and 5 degrees both resolve to North).
    """
    normalized_degree = degree % 360.0

    for upper_bound, direction in _DIRECTION_UPPER_BOUNDS:
        if normalized_degree < upper_bound:
            return direction

    return Direction.NORTH
