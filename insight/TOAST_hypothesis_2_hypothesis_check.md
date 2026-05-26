# TOAST_hypothesis_2 Hypothesis Check

Generated: 2026-05-04

Data checked: `YCSB-IVS-DATA/TOAST_hypothesis_2/TOAST_hypothesis_2_DATA` and `YCSB-IVS-DATA/TOAST_hypothesis_2/TOAST_hypothesis_2_DATA_NOVACC`.

## Bottom Line

The TOAST_hypothesis_2 runs confirm the main root cause: Zipfian JSONB growth creates large TOAST values, and read tails get expensive as values grow. The vacuum/no-vacuum comparison also makes vacuum/pre-run cache perturbation look materially important, because the vacuum run has much larger late p95 and stronger residual peaks. But no-vacuum still has late front-loaded bursts, so vacuum is an amplifier/perturbation, not a necessary cause.

The new `pg_buffercache` snapshots refine the cache hypothesis: relation-level TOAST residency does change sharply before the run, especially after vacuum, but total TOAST-heap buffer count does not visibly rewarm during the run. The front-loaded latency still rewarms in the latency samples, so the missing piece is likely page identity / hot-subset residency rather than total relation buffer count.

## Artifacts

-   `YCSB-IVS-DATA/insight/TOAST_hypothesis_2_plots/main_run_p95_vacuum_vs_no_vacuum.png`
-   `YCSB-IVS-DATA/insight/TOAST_hypothesis_2_plots/latency_slow_reads_blks_read_residency.png`
-   `YCSB-IVS-DATA/insight/TOAST_hypothesis_2_plots/buffer_residency_snapshots.png`
-   `YCSB-IVS-DATA/insight/TOAST_hypothesis_2_plots/late_latency_by_key_size_bin.png`
-   `YCSB-IVS-DATA/insight/TOAST_hypothesis_2_epoch_summary.csv`

## Variant Summary

| variant | run p95 mean 1-20 | run p95 mean 91-100 | ratio | reference p95 1-20 | reference p95 91-100 | slow-read % 1-20 | slow-read % 91-100 | top residual peaks |
|--------|-------:|-------:|-------:|-------:|-------:|-------:|-------:|--------|
| Vacuum | 261.6 | 2590.3 | 9.90x | 61.2 | 61.0 | 0.51% | 22.65% | 98 (4203us), 95 (3099us), 84 (2511us), 73 (2079us), 60 (1285us) |
| No vacuum | 276.1 | 1644.9 | 5.96x | 66.0 | 68.9 | 0.54% | 17.47% | 86 (1889us), 97 (1882us), 83 (1705us), 74 (1293us), 65 (1141us) |

## H1. TOAST / Value-Size Amplification

Verdict: strongly confirmed. Both variants produce essentially the same value-size distribution, while the unchanging reference run stays flat.

| variant   | iter | p50 KiB | p95 KiB | p99 KiB | max MiB | rows \>128KiB |
|-----------|-----:|--------:|--------:|--------:|--------:|--------------:|
| Vacuum    |   20 |    14.2 |    30.2 |    66.2 |     7.3 |         0.58% |
| Vacuum    |   50 |    33.6 |    73.4 |   164.5 |    18.2 |         1.68% |
| Vacuum    |   80 |    53.0 |   117.3 |   263.4 |    29.2 |         4.21% |
| Vacuum    |  100 |    66.0 |   146.0 |   331.3 |    36.5 |         6.71% |
| No vacuum |   20 |    14.2 |    30.1 |    66.5 |     7.3 |         0.58% |
| No vacuum |   50 |    33.6 |    73.4 |   164.2 |    18.2 |         1.71% |
| No vacuum |   80 |    53.0 |   118.0 |   263.1 |    29.1 |         4.18% |
| No vacuum |  100 |    66.0 |   146.8 |   331.2 |    36.4 |         6.78% |

At iteration 100, forced JSONB materialization remains cheap for p95-sized keys but very expensive for the max key, while lookup-only probes remain sub-millisecond:

| variant   | probe |       size | lookup ms | materialize/serialize ms |
|-----------|-------|-----------:|----------:|-------------------------:|
| Vacuum    | p95   |    149,500 |     0.056 |                    1.113 |
| Vacuum    | p99   |    339,200 |     0.052 |                    2.109 |
| Vacuum    | max   | 38,265,600 |     0.059 |                  173.019 |
| No vacuum | p95   |    150,300 |     0.054 |                    1.215 |
| No vacuum | p99   |    339,100 |     0.070 |                    2.241 |
| No vacuum | max   | 38,154,800 |     0.062 |                  196.466 |

## H2. Variable Shared-Buffer Miss / Cache Rewarming

Verdict: supported as shared-buffer miss pressure, but the simple relation-level “TOAST heap buffers rewarm upward” version is not supported. Run-phase `blks_read` tracks residual spikes, and latency/slow-read rates are strongly front-loaded. However, total TOAST heap buffer count usually declines from before-run to after-run, while TOAST index buffers rise. That means total relation residency is too coarse; if rewarming is happening, it is rewarming the useful page subset, not increasing total TOAST heap buffers.

Do not compare before-run TOAST heap percentages directly across vacuum and no-vacuum variants: the no-vacuum table retains dead TOAST bloat, so `toast_total_bytes` is a different denominator. Within each variant, lower before-run TOAST heap percentage still tracks the long-run p95 rise, but it does not explain the local residual spikes by itself.

| variant | corr p95 vs run blks_read delta | corr residual vs run blks_read delta | corr p95 vs before-run TOAST heap % | corr residual vs before-run TOAST heap % |
|---------------|--------------:|--------------:|--------------:|--------------:|
| Vacuum | 0.917 | 0.729 | -0.755 | -0.170 |
| No vacuum | 0.589 | 0.913 | -0.769 | -0.186 |

| variant | peak iter | p95 us | q1 sample p95 | q2-4 sample p95 avg | q1 slow % | q2-4 slow % avg | run blks_read delta | before-run TOAST heap % |
|--------|-------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|
| Vacuum | 98 | 4203 | 7614 | 1915 | 48.70% | 19.57% | 68627 | 12.76% |
| Vacuum | 95 | 3099 | 5571 | 1607 | 44.74% | 16.91% | 52773 | 12.92% |
| Vacuum | 84 | 2511 | 4846 | 1352 | 38.62% | 11.77% | 44776 | 15.67% |
| Vacuum | 73 | 2079 | 4395 | 1188 | 33.14% | 7.93% | 39285 | 17.64% |
| No vacuum | 86 | 1889 | 6198 | 1433 | 23.46% | 11.81% | 29339 | 1.66% |
| No vacuum | 97 | 1882 | 6369 | 1513 | 25.87% | 16.60% | 22697 | 1.21% |
| No vacuum | 83 | 1705 | 4571 | 1260 | 20.73% | 10.68% | 20659 | 1.69% |
| No vacuum | 74 | 1293 | 1189 | 1233 | 12.27% | 7.99% | 593 | 2.34% |

## H3. Large-Key Sampling

Verdict: still an amplifier, not the full clock. Sampled `>128KiB` share has high correlation with absolute p95 because both grow over time, but weak correlation with residual spikes. Late sampled latency by key-size bin:

| variant   | key-size bin | samples | median us | p95 us | p99 us |
|-----------|--------------|--------:|----------:|-------:|-------:|
| Vacuum    | \<=64K       |   10660 |       573 |   1081 |   3919 |
| Vacuum    | 64-128K      |    9021 |       811 |   1485 |   5325 |
| Vacuum    | 128-256K     |    1003 |      1538 |   2588 |   8549 |
| Vacuum    | 256-512K     |     180 |      2666 |   4074 |  11142 |
| Vacuum    | 512K-1M      |      32 |      6480 |  10011 |  14965 |
| Vacuum    | \>1M         |     104 |     13708 | 147490 | 355378 |
| No vacuum | \<=64K       |   10689 |       581 |    851 |   3646 |
| No vacuum | 64-128K      |    8993 |       798 |   1215 |   1638 |
| No vacuum | 128-256K     |    1004 |      1528 |   2326 |   2806 |
| No vacuum | 256-512K     |     183 |      2733 |   4378 |   5637 |
| No vacuum | 512K-1M      |      33 |      7404 |  10698 |  10945 |
| No vacuum | \>1M         |      98 |     22259 | 149464 | 390413 |

## H4. Vacuum Perturbation

Verdict: materially strengthened, but vacuum is not necessary. The vacuum run has a higher late p95 mean, a higher max p95, and a higher late slow-read rate. Vacuum duration grows from sub-second early to about 691s at iteration 100, and `pg_stat_progress_vacuum` is dominated by the main TOAST relation.

Vacuum duration: iter 1 `0.566s`, iter 50 `207.8s`, iter 100 `691.3s`.

Vacuum shifted TOAST buffer residency: after `extend` to after `vacuum`, TOAST heap buffers changed by mean `-27922` pages, min `-56642` pages. At iter 98, TOAST heap changed `-53172` pages and TOAST index changed `49890` pages.

No-vacuum still shows residual peaks and front-loaded slow reads, so the better model is “pre-run cache/useful-residency perturbation, amplified by vacuum”, not “vacuum alone creates the phenomenon.”

## H5. Checkpoint / Bgwriter Rhythm

Verdict: still weak as a direct trigger. Checkpoint pressure is large during extend and vacuum, but run-phase checkpoint request deltas are mostly zero at the largest p95 peaks. `log_checkpoints` was on, but checkpoint message capture produced zero rows in both variants, so exact start/end alignment is still missing.

| variant | run epochs with checkpoint request delta \> 0 | run epochs with checkpoint write-time delta \> 0 | checkpoint log message rows | OS disk nonzero samples |
|---------------|--------------:|--------------:|--------------:|--------------:|
| Vacuum | 3 | 13 | 0 | 0 |
| No vacuum | 5 | 10 | 0 | 0 |

OS disk counters are still all zero and selected via `auto_all_fallback`, so they remain unusable for distinguishing OS-cache hits from physical I/O.

## H6. Server-Side Detoast / Serialization And Client Parse

Verdict: confirmed as cost placement, not timing. For slow reads in iterations 80-100:

| variant | mean slow latency us | query_execute share | json_parse share | value_join share |
|---------------|--------------:|--------------:|--------------:|--------------:|
| Vacuum | 2900 | 64.9% | 29.5% | 4.1% |
| No vacuum | 3133 | 59.8% | 34.1% | 4.5% |

## Updated Working Model

``` text
Zipfian JSONB appends
  -> large TOAST-backed values
  -> expensive detoast / serialization / parsing on large reads
  -> extend plus pre-run probes/checkpoints/vacuum reshuffle useful buffer residency
  -> vacuum materially increases late cache perturbation and spike amplitude
  -> early main-run reads encounter elevated shared-buffer reads and slow-read rates
  -> enough large/cold reads cross the p95 boundary
```

The major refinement is that relation-level `pg_buffercache` snapshots do not show total TOAST heap pages rewarming upward during the run. Future confirmation would need page identity or key-to-page residency, not only relation totals.