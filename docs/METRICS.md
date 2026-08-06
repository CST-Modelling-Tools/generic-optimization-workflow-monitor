# GOW Monitor metrics

## Objective variability

The current **Objective variability** metric is the coefficient of variation
of the valid objective values observed inside the latest evaluation window.

Default window:

```text
100 evaluations
```

The window is applied before invalid results are removed. Therefore, if 8 of
the latest 100 evaluations failed, the calculation uses the 92 valid objective
values that remain.

For valid objective values:

```text
x_1, x_2, ..., x_n
```

the arithmetic mean is:

```text
mu = (1 / n) * sum(x_i)
```

The monitor uses the population standard deviation:

```text
sigma = sqrt((1 / n) * sum((x_i - mu)^2))
```

The displayed percentage is:

```text
CV_percent = 100 * sigma / abs(mu)
```

Special cases:

- Fewer than two valid objectives: `N/A`.
- `mu = 0` and `sigma = 0`: `0.0000%`.
- `mu = 0` and `sigma > 0`: `N/A`, because the coefficient is undefined.

Interpretation:

- A low percentage means recent objective values are concentrated relative to
  their mean.
- A high percentage means they are widely dispersed relative to their mean.
- Values above 100% are mathematically possible.
- The coefficient becomes unstable when the mean is close to zero.
- It does not measure convergence by itself; it must be interpreted together
  with best-so-far, recent improvement and failure rate.

The warning color above 100% is a dashboard heuristic, not a universal
scientific threshold.

## Population diversity

The diversity panel displays two complementary curves for every observed GOW
generation. Both are calculated from numeric candidate vectors in the `params`
field of `result.json` and `results.jsonl`.

Every parameter is normalized with the global observed range of the connected
run. Constant dimensions are excluded:

```text
z_gij = (x_gij - min_j) / (max_j - min_j)
```

### spread

`spread` is the sum of the marginal sample standard deviations of all active
normalized parameters:

```text
spread_g = sum_j(sample_std(z_g1j, ..., z_gnj))
```

This reproduces the intuitive width of the population across all parameter
axes. It can be larger than one because the contributions of multiple active
dimensions are added.

### ellipse_area

`ellipse_area` describes the occupied area in the two dominant PCA directions.
The monitor builds the normalized sample covariance matrix and obtains its two
largest eigenvalues, `lambda_1` and `lambda_2`. The displayed 95% confidence
ellipse area is:

```text
ellipse_area_g = pi * chi2_0.95,df=2 * sqrt(lambda_1 * lambda_2)
```

with:

```text
chi2_0.95,df=2 = 5.991464547107979
```

Interpretation:

- Both curves approaching zero indicate population collapse.
- A decreasing `spread` means the population is narrowing across parameter axes.
- A decreasing `ellipse_area` means the dominant two-dimensional search region
  is contracting.
- One curve can decrease while the other temporarily increases when the search
  rotates or redistributes variance between dimensions.
- The metrics are diagnostics. They do not prove convergence or global
  optimality.
- Historical values can be rescaled when a later candidate extends a global
  observed parameter range.

The dotted vertical line marks the latest observed generation. Missing
parameter vectors are never estimated.

## Numeric display policy

The objective keeps its existing high-precision formatting.

All other decimal values shown in metric cards, status details and the
diversity chart use fixed-point formatting with exactly two decimal places.
Scientific notation is not used for these non-objective dashboard values.
Integer counters remain integers, and elapsed time uses a clock format.

The run-time cards use the earliest observed candidate `started_at` as the
campaign start. While a run is active, elapsed time advances against the system
clock. Once the run reaches a terminal state, the timer freezes at the latest
observed `finished_at`. Evaluations per minute is the cumulative wall-clock
average:

```text
evaluations_per_minute = completed_evaluations * 60 / elapsed_seconds
```

## Resource telemetry shown in the dashboard

The resources panel intentionally displays only:

- Total host CPU utilization.
- Total host RAM utilization.
- Number of active host logical CPU cores.
- Aggregated GOW resident memory (RSS).
- Number of distinct result artifact sources.

The following cards are intentionally omitted from the dashboard:

- GPU utilization.
- GOW CPU utilization.
- GOW process-tree count.
- GOW thread count.

The process-tree reader remains an internal implementation detail because
aggregating GOW RAM across child processes still requires process discovery.
The hidden process, thread and CPU values are not presented to the operator.

CPU and RAM are sampled from the host operating system once per second.

A logical core is counted as active when its sampled utilization is at least
5%. This threshold is a display convention and can be made configurable later.

`N/A` is displayed rather than estimating unavailable data.
