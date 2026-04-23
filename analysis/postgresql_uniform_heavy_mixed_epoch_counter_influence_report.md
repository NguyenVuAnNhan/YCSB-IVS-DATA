# Epoch-to-Epoch Counter Influence Report: `postgresql_uniform_heavy_mixed`

## Scope

This report analyzes the PostgreSQL `uniform_heavy_mixed` scenario across:

- `DATA/postgresql_run1_uniform_heavy_mixed.csv`
- `DATA/postgresql_run2_uniform_heavy_mixed.csv`
- `DATA/postgresql_run3_uniform_heavy_mixed.csv`
- `DATA/postgresql_run4_uniform_heavy_mixed.csv`

The repeated benchmark phases are:

- `run`
- `reference`
- `clean-run`
- `avg-run`
- `extend`

## Method

The PostgreSQL counters in these files are cumulative, so raw values cannot be compared directly across epochs without differencing.

This report uses two complementary views:

1. Long-run drift
   Uses within-run Spearman correlations between performance series and interval counter intensity, then averages those correlations across runs.

2. Same-step epoch-to-epoch influence
   Uses Spearman correlations between performance changes from epoch `N-1 -> N` and counter deltas over the same same-phase interval.

Counter deltas are normalized as:

`(counter_N - counter_(N-1)) / total_operations_N`

This gives a per-operation pressure estimate for the interval ending at epoch `N`.

Derived counter metrics:

- `cache-hit ratio`
- `block reads/op`
- `block hits/op`
- `wal bytes/op`
- `wal records/op`
- `wal FPIs/op`
- `buffer allocs/op`
- `backend buffers/op`
- `checkpoint buffers/op`
- `cleaner buffers/op`
- `checkpoint write ms/op`
- `checkpoint sync ms/op`

Interpretation note:

- Long-run correlations are useful for identifying structural drift, but they are not causal proof.
- Same-step correlations are the better test for whether a counter moves with short-run epoch-to-epoch performance changes.
- In this report, `|rho| >= 0.15` is treated as the minimum threshold for a meaningful same-step relationship.

## Executive Summary

- All phases show strong long-run degradation: throughput falls while latency rises over time.
- The strongest long-run proxy for that drift is consistently `cleaner buffers/op`, with averaged within-run Spearman correlations between about `0.868` and `0.987` in absolute value.
- Other counters move almost in lockstep with that drift: `wal bytes/op`, `buffer allocs/op`, `backend buffers/op`, `block reads/op`, and `cache-hit ratio`.
- Same-step influence is much weaker than long-run drift.
- `run`, `avg-run`, and `reference` show no counter with `|rho| >= 0.15` against throughput or latency changes.
- `clean-run` is the clearest exception: `block reads/op` and `block hits/op` have moderate same-step ties to both throughput loss and latency growth.
- `extend` shows a smaller but consistent checkpoint signal: higher `checkpoint buffers/op` is associated with lower throughput and higher latency.
- The epoch `14 -> 15` improvement is real, but it does not coincide with lower WAL or buffer pressure. The data supports a temporary favorable steady-state effect more than a sudden counter relief event.

## Long-Run Drift

Average start-to-end change across runs:

| Phase | Throughput change | READ latency change | UPDATE latency change | EXTEND latency change |
| --- | ---: | ---: | ---: | ---: |
| `run` | `-46.8%` | `+197.3%` | `+76.2%` |  |
| `clean-run` | `-44.0%` | `+190.1%` | `+69.2%` |  |
| `avg-run` | `-21.5%` | `+108.7%` | `+18.5%` |  |
| `reference` | `-48.2%` | `+233.1%` | `+78.3%` |  |
| `extend` | `-47.5%` |  |  | `+90.9%` |

Strongest averaged within-run monotonic relationships:

| Phase | Throughput strongest driver | rho | Latency strongest driver | rho |
| --- | --- | ---: | --- | ---: |
| `run` | `cleaner buffers/op` | `-0.977` | `cleaner buffers/op` vs READ | `+0.987` |
| `clean-run` | `cleaner buffers/op` | `-0.950` | `cleaner buffers/op` vs READ | `+0.974` |
| `avg-run` | `cleaner buffers/op` | `-0.919` | `cleaner buffers/op` vs READ | `+0.971` |
| `reference` | `cleaner buffers/op` | `-0.966` | `cleaner buffers/op` vs READ | `+0.986` |
| `extend` | `cleaner buffers/op` | `-0.984` | `cleaner buffers/op` | `+0.984` |

Interpretation:

- Over the long run, the scenario behaves like a classic storage-pressure story.
- As cleaner activity, buffer churn, and WAL volume rise, throughput consistently trends down and latency trends up.
- `cleaner buffers/op` is likely acting as a compact proxy for a broader cluster of rising maintenance and writeback pressure rather than as a unique root cause by itself.

Near-tied long-run companions to `cleaner buffers/op` are:

- `wal bytes/op`
- `buffer allocs/op`
- `backend buffers/op`
- `block reads/op`
- `cache-hit ratio` with opposite sign

## Same-Step Epoch-to-Epoch Influence

Transition sample sizes:

| Phase | Transition count |
| --- | ---: |
| `run` | `385` |
| `clean-run` | `384` |
| `avg-run` | `384` |
| `reference` | `384` |
| `extend` | `385` |

Meaningful same-step relationships, `|rho| >= 0.15`:

| Phase | Target change | Counter | rho | Reading |
| --- | --- | --- | ---: | --- |
| `clean-run` | Throughput change | `block hits/op` | `-0.349` | More block-hit work per op is associated with lower next-epoch throughput |
| `clean-run` | Throughput change | `block reads/op` | `-0.348` | More block reads per op are also associated with lower throughput |
| `clean-run` | READ latency change | `block hits/op` | `+0.308` | More block-hit work per op is associated with higher READ latency |
| `clean-run` | READ latency change | `block reads/op` | `+0.240` | More block reads per op are associated with higher READ latency |
| `clean-run` | UPDATE latency change | `block reads/op` | `+0.340` | More block reads per op are associated with higher UPDATE latency |
| `clean-run` | UPDATE latency change | `block hits/op` | `+0.331` | More block-hit work per op is associated with higher UPDATE latency |
| `extend` | Throughput change | `checkpoint buffers/op` | `-0.158` | More checkpoint-buffer work is associated with lower EXTEND throughput |
| `extend` | EXTEND latency change | `checkpoint buffers/op` | `+0.158` | More checkpoint-buffer work is associated with higher EXTEND latency |

Phases with no meaningful same-step relationship above the `|rho| >= 0.15` threshold:

- `run`
- `avg-run`
- `reference`

Interpretation:

- The short-run story is much weaker than the long-run drift story.
- In `clean-run`, extra memory and I/O work per operation tracks performance deterioration within the same transition window.
- In `extend`, checkpoint-related buffer work matters, but only modestly.
- In `run`, `avg-run`, and `reference`, no single counter explains epoch-to-epoch performance changes well enough to stand out as a strong same-step driver.

## Epoch `14 -> 15` Case Study

Mean performance change from epoch `14 -> 15` across runs:

| Phase | Throughput `14 -> 15` | READ latency `14 -> 15` | UPDATE latency `14 -> 15` | EXTEND latency `14 -> 15` |
| --- | ---: | ---: | ---: | ---: |
| `run` | `1440.08 -> 1537.23` `(+6.75%)` | `185.67us -> 169.63us` `(-8.63%)` | `1190.56us -> 1120.08us` `(-5.92%)` |  |
| `clean-run` | `1495.71 -> 1564.40` `(+4.59%)` | `161.09us -> 148.40us` `(-7.88%)` | `1170.77us -> 1122.21us` `(-4.15%)` |  |
| `avg-run` | `1479.42 -> 1582.65` `(+6.98%)` | `166.68us -> 141.68us` `(-15.00%)` | `1175.47us -> 1110.66us` `(-5.51%)` |  |
| `extend` | `653.72 -> 708.81` `(+8.43%)` |  |  | `1522.85us -> 1404.08us` `(-7.80%)` |
| `reference` | `1281.98 -> 1279.72` `(-0.18%)` | `213.88us -> 216.84us` `(+1.39%)` | `1334.09us -> 1334.08us` `(-0.00%)` |  |

The `14 -> 15` improvements are unusually strong relative to the rest of the transition distribution:

- `run` throughput improvement is better than `95.6%` of other `run` transitions
- `run` READ latency improvement is better than `98.2%` of other `run` transitions
- `run` UPDATE latency improvement is better than `92.7%` of other `run` transitions
- `clean-run` READ latency improvement is better than `94.0%` of other `clean-run` transitions
- `avg-run` READ latency improvement is better than `98.4%` of other `avg-run` transitions
- `extend` latency improvement is better than `98.4%` of other `extend` transitions

Counter deltas over the same `14 -> 15` interval:

| Phase | `block reads/op` change | `buffer allocs/op` change | `wal bytes/op` change | `wal records/op` change |
| --- | ---: | ---: | ---: | ---: |
| `run` | `+13.35` | `+18.14` | `+19692.28` | `+30.93` |
| `clean-run` | `+0.23` | `+18.65` | `+19980.17` | `+33.29` |
| `avg-run` | `-0.20` | `+18.40` | `+19746.49` | `+33.49` |
| `extend` | `+12.89` | `+17.84` | `+19688.35` | `+29.99` |
| `reference` | `+4.44` | `+18.40` | `+19698.43` | `+31.60` |

Why this matters:

- The active phases improve sharply at epoch `15`.
- The shared storage counters do not drop at the same time.
- WAL volume rises by about `19.7k bytes/op` in every phase.
- Buffer allocations rise by about `18 allocs/op` in every phase.
- `reference` sees the same broad counter increases but does not improve.

So the epoch `15` jump is not well explained by a sudden fall in WAL, checkpoint, or buffer pressure.

## Interpretation

The evidence supports a two-layer explanation.

First, the scenario has a strong long-run storage-pressure drift:

- more cleaner work
- more buffer churn
- more WAL per operation
- more block-read intensity
- lower cache effectiveness

All of those move with lower throughput and higher latency over time.

Second, short-run epoch-to-epoch changes are mostly not governed by a single counter:

- `clean-run` is the one phase where block access intensity clearly matters in the same step
- `extend` shows a smaller checkpoint-buffer effect
- the other phases do not have a strong same-step counter driver

That is why epoch `15` looks special:

- performance improves strongly
- the usual pressure counters still increase
- the same counters do not predict a comparable improvement in `reference`

The most defensible reading is that epoch `15` reflects a temporary favorable workload state, likely from improved page reuse or locality after enough mixed update and extend churn, rather than a simple drop in PostgreSQL maintenance work.

## Bottom Line

- Counters explain the long-run degradation very well.
- Counters explain the short-run epoch-to-epoch changes only partially.
- `clean-run` is the main phase where block access intensity has a meaningful same-step influence.
- `extend` is somewhat sensitive to checkpoint-buffer work.
- The epoch `14 -> 15` latency drop is real, but it is not a counter-relief event. It is better understood as a transient steady-state improvement that temporarily overpowers the broader storage-pressure trend.
