def linear_regression(points):
    """Ordinary least squares over (x, y) pairs. Centers x on the first
    point before fitting - raw epoch-second x-values are ~1.75e9-scale, and
    squaring them in the textbook formula subtracts two ~1e23-scale sums to
    recover a much smaller signal (catastrophic cancellation). Centering
    keeps values small and sidesteps this; slope is translation-invariant,
    so the result is unchanged either way."""
    n = len(points)
    if n < 2:
        raise ValueError("linear_regression requires at least 2 points")

    x0 = points[0][0]
    xs = [x - x0 for x, _ in points]
    ys = [y for _, y in points]

    sum_x, sum_y = sum(xs), sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_xx = sum(x * x for x in xs)

    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        raise ValueError("linear_regression: all timestamps identical (degenerate)")

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept
