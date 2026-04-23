# PostgreSQL ArrayJSON Bigcache Zipfian Heavy Pure System Metrics Report

## Scope

-   Runs analyzed: `run4`, `run5`, and `run6` from `JSON_BLUE/`.
-   Workload family: `postgresql_arrayjson_vacuum_notfull_bigcache_*_zipfian_heavy_pure`.
-   System metrics source: watcher `.metrics` files for `reference`, `run`, `clean-run`, `avg-run`, and `extend`.
-   Performance source: matching YCSB phase rows from the corresponding CSV files.
-   Note: the watcher files in this family report `CPU` and `MemoryKB`, but `DeltaReadBytes` and `DeltaWriteBytes` are effectively zero throughout these runs, so this report focuses on CPU and memory.

## Executive Summary

-   `run` latency rises from 87.8 us to 703.0 us on average across runs, while throughput falls from 11,932.0 to 1,446.0 ops/sec (-87.8% change).
-   During the same `run` window, watcher memory climbs from 712.1 MiB to 3,214.9 MiB (351.6% growth), while CPU actually eases from 60.6% to 53.1% (-11.7% change).
-   `extend` is the opposite: CPU and memory both ramp hard. Average CPU rises from 23.8% to 61.8% (159.8% growth), and memory rises from 923.5 MiB to 6,819.2 MiB (638.7% growth).
-   Those `extend` resource increases track the performance collapse closely: latency grows from 1,659.9 us to 10,429.7 us, while throughput drops from 614.7 to 96.0 ops/sec.
-   The strongest system-level signal in the read-heavy phases is memory growth, not rising CPU. In `run`, memory has mean Spearman rho 0.833 with average latency and -0.833 with throughput, while CPU shows -0.353 and 0.353.

## Phase Summary

| Phase | Mean CPU % | Peak CPU % | Mean Memory MiB | Peak Memory MiB | Mean Throughput | Mean Avg Latency us |
|-----------|----------:|----------:|----------:|----------:|----------:|----------:|
| reference | 43.5 | 59.5 | 59.9 | 97.0 | 22,871.3 | 39.7 |
| run | 66.7 | 90.8 | 2,699.7 | 3,760.0 | 4,098.5 | 361.7 |
| clean-run | 75.9 | 99.5 | 1,131.7 | 4,289.9 | 4,731.2 | 293.4 |
| avg-run | 78.1 | 190.4 | 1,131.2 | 4,870.2 | 4,788.6 | 299.1 |
| extend | 55.0 | 90.4 | 5,808.2 | 8,682.4 | 250.2 | 5,576.5 |

## Key Findings

-   `reference` stays light: mean memory is only 59.9 MiB and mean latency is 39.7 us, which makes it a useful baseline.
-   `run`, `clean-run`, and `avg-run` all show the same shape: memory grows by roughly 351.6%, 1,520.6%, and 1,790.4% respectively, while throughput collapses by about 85% to 88%.
-   `extend` is the most resource-intensive phase overall, with the highest peak memory (8,682.4 MiB) and the largest CPU growth.
-   In the read-heavy phases, higher memory is tightly associated with worse performance: latency rho values are 0.833 for `run`, 0.920 for `clean-run`, and 0.917 for `avg-run`.
-   The watcher I/O delta fields do not add explanatory power here because they remain zero across the analyzed files. That looks like a collector limitation or a no-op field in this dataset, not evidence that the database performed no storage work.

## Interpretation

-   The system metrics reinforce the earlier database-counter story: as the bigcache Zipfian pure workload progresses, the dominant visible pressure is increasing memory footprint rather than a steadily rising CPU bottleneck.
-   For `extend`, both CPU and memory rise together, which fits a growing per-operation update cost. For later read phases, CPU does not keep climbing, but memory continues to grow and performance still degrades, suggesting the workload is becoming more state-heavy and less efficient per operation rather than simply saturating CPU.
-   Inference: the repeated updates to hot Zipfian keys appear to accumulate more in-memory working set and backend state over time, which lines up with the previously observed growth in WAL, block reads, tuple work, and latency.

## Generated Tables

-   `analysis/postgresql_arrayjson_bigcache_zipfian_heavy_pure_system_metrics_summary.csv`
-   `analysis/postgresql_arrayjson_bigcache_zipfian_heavy_pure_system_metrics_drift.csv`
-   `analysis/postgresql_arrayjson_bigcache_zipfian_heavy_pure_system_metrics_correlations.csv`