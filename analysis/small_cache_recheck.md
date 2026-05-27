# Small Cache Recheck

Date: 2026-05-28

## Scope

This recheck revisits the older PostgreSQL array-JSON runs that used the pre-4GB cache configuration.

Important mapping detail:

- `postgresql-IVS3.conf` and `postgresql-IVS4.conf` set `shared_buffers = 128MB`.
- `postgresql-IVS5.conf` sets `shared_buffers = 4GB`.
- The plain `run3` array-JSON data is duplicated as `JSON_BLUE/...bigcache_run3...`, so `run3` belongs with the 4GB/big-cache family.
- The clearest small-cache heavy Zipfian pair is therefore `run1` and `run2`; the 4GB comparison family is `run3` through `run6`.

Derived CSVs from this pass:

- `analysis/small128_vs_big4gb_phase_rows.csv`
- `analysis/small128_vs_big4gb_summary.csv`

## Heavy Zipfian Pure Result

The old small-cache heavy Zipfian runs already support the cache-residency hypothesis.

Run-phase late-window comparison, epochs 91-100:

| cache profile | runs | run p95 mean | run p99 mean | throughput | block reads/op | cache-hit ratio |
|---|---:|---:|---:|---:|---:|---:|
| 128MB | 2 | 4492 us | 9049 us | 850 ops/s | 194.1 | 0.772 |
| 4GB | 4 | 1543 us | 5378 us | 1412 ops/s | 119.5 | 0.859 |

Threshold timing:

| cache profile | first epoch p95 > 1ms | first epoch p95 > 2ms |
|---|---:|---:|
| 128MB run1 | 53 | 57 |
| 128MB run2 | 49 | 56 |
| 4GB run3 | 59 | 97 |
| 4GB run4 | 71 | 95 |
| 4GB run5 | 70 | 97 |
| 4GB run6 | 70 | 84 |

Interpretation: smaller shared buffers shift the read-tail phase change earlier and make late read phases substantially worse. That is consistent with the current useful-TOAST-page residency model.

## Uniform And Light Nuance

The older uniform and light runs add an important caveat.

Uniform heavy pure with the older small-cache data shows cache pressure but not the same tail-spike shape:

- Late run p95 is about `686-695 us` for runs 1-2.
- Late run block reads/op rises to about `46`.
- Delta cache-hit ratio falls to about `0.64`.
- No run crosses `1ms` P95.

Light Zipfian pure also remains mostly sub-millisecond even under 128MB:

- 128MB light Zipfian late run p95 is about `701-720 us`.
- It does show large cumulative `blks_read`, unlike the 4GB light run.
- The 4GB light run has p95 near `996 us`, so host/run variance is too large to call this a clean cache-size A/B.

Interpretation: small cache increases read pressure, but cache pressure alone is not sufficient. The large-tail behavior needs the growing JSONB/TOAST value-size path, especially Zipfian growth that creates large hot values.

## Missing Insight

The old small-cache data does not overturn the current model; it sharpens it:

```text
Smaller shared_buffers
  -> useful TOAST working set exceeds cache earlier
  -> block reads/op rise earlier
  -> p95/p99 phase change shifts left

but

large TOAST-backed values and Zipfian large-key reads
  -> determine whether that cache pressure becomes a visible tail-latency spike
```

So the next reduced-cache experiment should not simply be "small cache light workload". The best test is a controlled cache-size sweep at the same workload and host:

- 4GB baseline
- 1GB
- 512MB
- 128MB

Run it for both light and heavy Zipfian pure. The expected result is that the heavy Zipfian phase change moves left as cache shrinks, while the light run may show more reads/op before it shows the full late-tail spike.

## Caveats

- These old runs have coarser observability: no `pg_statio_user_tables`, no page identity, no `pg_stat_io`, and no direct TOAST relation counters.
- The old CSV counters are cumulative; the recheck uses same-phase epoch deltas normalized by operation count.
- Host/run differences remain confounders, especially in the light comparison.
