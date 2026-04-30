# TOAST Run Data Cross-Check

This cross-check compares the new `TOAST_RUN_DATA` run against the hypotheses in:

-   `json_blue_postgresql_p95_spike_hypotheses.md`
-   `json_blue_toast_evidence.md`
-   `jsonb_toast_amplification_experiment_plan.md`

## Verdict

The new run strongly confirms the JSONB/TOAST amplification hypothesis.

The older notes inferred TOAST pressure from value-size tails and PostgreSQL proxy counters. The new data adds direct relation-size, detoast-probe, and phase-control evidence:

-   main `run` p95 rises from `151.0 us` in epochs 1-20 to `1275.0 us` in epochs 91-100, an `8.44x` increase.
-   unchanged `reference` p95 stays flat, from `49.4 us` to `51.1 us`.
-   direct TOAST total size rises from `0.08 GiB` at epoch 1 to `27.72 GiB` at epoch 100.
-   forced JSONB serialization time tracks value size almost perfectly: Pearson `0.998`, Spearman `0.985`.
-   lookup-only probes stay near-flat: `0.045-0.140 ms`, even when the same key's serialized JSONB probe reaches `183.520 ms`.

## Hypothesis Check

### 1. TOAST chunk amplification is the primary driver

Supported, now directly.

The run-phase `.dbstats` file shows the heap relation itself remains about `44-45 MiB`, while the TOAST relation dominates total size:

| epoch | toast_total |  heap_total |  toast_heap |
|------:|------------:|------------:|------------:|
|     1 |  `0.08 GiB` |  `0.12 GiB` |  `0.07 GiB` |
|    20 |  `4.23 GiB` |  `4.27 GiB` |  `4.01 GiB` |
|    40 | `10.88 GiB` | `10.92 GiB` | `10.51 GiB` |
|    60 | `17.24 GiB` | `17.28 GiB` | `16.64 GiB` |
|    80 | `21.59 GiB` | `21.63 GiB` | `20.90 GiB` |
|   100 | `27.72 GiB` | `27.76 GiB` | `27.00 GiB` |

The combined CSV still shows the old storage-amplification shape: logical updates stay near `1.00/op`, while inserted tuple work, WAL, reads, and buffer allocations rise sharply by epoch 100:

| epoch | tup_inserted/op | tup_updated/op | WAL MiB/op | buffers_alloc/op | blks_read/op |
|-----------:|-----------:|-----------:|-----------:|-----------:|-----------:|
|     2 |          `2.60` |         `1.00` |   `0.0067` |           `0.32` |       `0.00` |
|    20 |         `28.27` |         `1.00` |   `0.0818` |           `4.16` |       `4.43` |
|    40 |         `57.50` |         `1.00` |   `0.1635` |          `16.02` |      `28.38` |
|    60 |         `85.50` |         `1.00` |   `0.2522` |          `25.96` |      `54.99` |
|    80 |        `115.86` |         `1.00` |   `0.3552` |          `35.32` |      `84.46` |
|   100 |        `143.98` |         `1.00` |   `0.4525` |          `44.16` |     `127.37` |

### 2. P95 jumps when the top 5% of reads cross large-value thresholds

Supported.

The final value-size distribution matches the previous JSON Blue runs almost exactly:

| epoch | mean | p50 | p90 | p95 | p99 | max | rows \>128 KiB |
|--------:|--------:|--------:|--------:|--------:|--------:|--------:|--------:|
| 1 | `2.0 KiB` | `1.7 KiB` | `2.3 KiB` | `2.6 KiB` | `4.3 KiB` | `391 KiB` | `0.00%` |
| 60 | `59.6 KiB` | `39.9 KiB` | `66.3 KiB` | `88.6 KiB` | `196.6 KiB` | `21.9 MiB` | `2.6%` |
| 80 | `79.1 KiB` | `52.9 KiB` | `88.1 KiB` | `118.0 KiB` | `262.5 KiB` | `29.2 MiB` | `3.7%` |
| 100 | `98.6 KiB` | `65.9 KiB` | `109.6 KiB` | `146.3 KiB` | `330.7 KiB` | `36.5 MiB` | `6.74%` |

Main-run p95 crosses `1000 us` in clustered windows: epochs `71-73`, `81-86`, and `93-99`.

### 3. Main run has extra physical-history cost beyond value size alone

Supported.

Late p95 means:

| phase       | first 20 epochs | last 10 epochs | increase |
|-------------|----------------:|---------------:|---------:|
| `run`       |      `151.0 us` |    `1275.0 us` |  `8.44x` |
| `clean-run` |      `129.2 us` |     `672.8 us` |  `5.21x` |
| `avg-run`   |      `121.5 us` |     `586.2 us` |  `4.82x` |
| `reference` |       `49.4 us` |      `51.1 us` |  `1.03x` |

The matched controls show large values alone are enough to hurt reads, but the append-grown main table is still materially worse late in the run.

### 4. Per-cycle VACUUM becomes a perturbation as TOAST grows

Supported as a secondary contributor.

Vacuum time grows from effectively zero early to `621.5 s` on average in the final 10 epochs. Selected vacuum durations:

| epoch | vacuum seconds |
|------:|---------------:|
|     1 |            `0` |
|    20 |            `5` |
|    40 |          `128` |
|    60 |          `331` |
|    80 |          `483` |
|   100 |          `634` |

This is likely both a symptom of TOAST growth and a contributor to cache/writeback perturbation before the following read phase.

### 5. Checkpoint/background write pressure amplifies the tail

Supported as secondary.

Run-phase cumulative `blks_read` rises from `2` at epoch 1 to `525,523,409` at epoch 100, while `buffers_alloc` rises from `12,025,177,075` to `12,233,489,199`. Temporary bytes also begin appearing late, reaching `909,499,146` bytes by epoch 100.

These signals fit the old "background pressure amplifies the tail" hypothesis, but the strongest mechanism remains direct TOAST growth plus detoast/serialization cost.

## Detoast Probe Check

The new deterministic probes are especially decisive:

| epoch | probe |        size | lookup-only | JSONB serialize | shared hits, serialize |
|-----------:|------------|-----------:|-----------:|-----------:|-----------:|
|     1 | min   |   `1.0 KiB` |  `0.059 ms` |      `0.068 ms` |                    `3` |
|     1 | p95   |   `2.6 KiB` |  `0.055 ms` |      `0.156 ms` |                   `35` |
|     1 | max   |   `391 KiB` |  `0.056 ms` |      `1.895 ms` |                  `112` |
|   100 | min   |  `48.0 KiB` |  `0.066 ms` |      `0.628 ms` |                   `80` |
|   100 | p95   | `146.3 KiB` |  `0.054 ms` |      `1.063 ms` |                   `92` |
|   100 | p99   | `330.7 KiB` |  `0.052 ms` |      `2.071 ms` |                  `118` |
|   100 | max   |  `36.5 MiB` |  `0.051 ms` |    `183.520 ms` |                 `5143` |

This confirms the exact split predicted by the experiment plan:

-   primary-key lookup remains cheap.
-   forced JSONB materialization grows with value size.
-   large hot keys require thousands of buffer hits during serialization.

## Nuances

-   The `before` and `after` value-size matrices are identical in this pasted dataset. That may be intentional if both snapshots were captured after the same size computation, but it means this folder does not independently show within-epoch before/after size deltas.
-   Some `run.dbstats` epochs have duplicate rows with `numbackends=1`; the summary above uses the `numbackends=0` rows for phase-end comparisons.
-   The `.dbstats` table-level `n_tup_ins` stays at `10000` because it is for the heap table. The broader combined CSV's `tup_inserted` counter is the better indicator for TOAST/internal insert amplification.

## Bottom Line

The new `TOAST_RUN_DATA` converts the earlier JSON Blue hypothesis from "strong proxy-supported explanation" to "directly supported mechanism." The late p95 spike is best explained by Zipfian JSONB append growth creating a large TOAST relation, followed by expensive detoast/JSONB serialization and worsening storage locality/background pressure in late read phases.