def inclusive_range(start: int, stop: int, step: int):
    """Return a list like range(), but always include the stop value as the last element.

    Examples:
        inclusive_range(0, 15, 2) -> [0, 2, 4, 6, 8, 10, 12, 14, 15]
        inclusive_range(15, 0, -2) -> [15, 13, 11, 9, 7, 5, 3, 1, 0]
    """
    start = int(start)
    stop = int(stop)
    step = int(step)

    if step == 0:
        raise ValueError("step cannot be 0")

    if start < stop and step < 0:
        raise ValueError("step must be positive when start < stop")
    if start > stop and step > 0:
        raise ValueError("step must be negative when start > stop")

    values = list(range(start, stop, step))

    if not values:
        return [start] if start == stop else [start, stop]

    if values[-1] != stop:
        values.append(stop)

    return values
