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
- `mu = 0` and `sigma = 0`: `0%`.
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

## Host resource telemetry

CPU and RAM are sampled from the host operating system once per second.

Displayed CPU information:

- Total host CPU utilization.
- Logical core count.
- Physical core count when the operating system exposes it.
- Number of active logical cores.
- Per-core utilization history.

A logical core is counted as active when its sampled utilization is at least
5%. This threshold is a display convention and can be made configurable later.

Displayed RAM information:

- Percentage of host physical memory in use.
- Used bytes.
- Total bytes.

GPU telemetry is adapter-based:

- NVIDIA GPUs are queried through `nvidia-smi` when it is available.
- The application remains functional when no supported GPU backend is present.
- AMD and Apple GPU adapters can be added without changing the dashboard
  contract.
- `N/A` is displayed rather than estimating unavailable data.

The current values are host-level measurements. Exact attribution to one GOW
process requires an explicit PID or scheduler/process contract.
