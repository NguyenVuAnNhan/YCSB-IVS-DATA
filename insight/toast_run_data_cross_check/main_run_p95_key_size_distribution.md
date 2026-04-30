# Main-Run p95 and Key Size Distribution

This combines main-run p95 latency with the per-epoch key/value-size distribution. Sizes come from `value_sizes_postgresql_arrayjson_TOAST_run1_zipfian_heavy_after_pure.csv`; the final histogram uses `key_sizes_postgresql_arrayjson_TOAST_zipfian_heavy_pure_run1.csv`.

## Outputs

- `main_run_p95_and_key_size_distribution_by_epoch.png`
- `main_run_p95_and_key_size_threshold_shares.png`
- `final_key_size_distribution_epoch100_histogram.png`
- `main_run_p95_with_key_size_distribution.csv`

## Selected Epochs

| Epoch | p95_us | size_p50_kib | size_p95_kib | size_p99_kib | size_max_mib | pct_gt_128k | pct_gt_256k |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 61 | 1.66 | 2.54 | 4.3 | 0.38 | 0.03 | 0.01 |
| 20 | 224 | 14.16 | 30.27 | 65.82 | 7.33 | 0.59 | 0.41 |
| 40 | 349 | 27.05 | 59.58 | 132.23 | 14.6 | 1.06 | 0.58 |
| 50 | 462 | 33.5 | 73.93 | 164.08 | 18.26 | 1.7 | 0.64 |
| 60 | 791 | 39.94 | 88.57 | 196.62 | 21.91 | 2.74 | 0.77 |
| 70 | 956 | 46.39 | 103.42 | 229.22 | 25.58 | 3.39 | 0.82 |
| 80 | 911 | 52.93 | 117.97 | 262.51 | 29.23 | 4.16 | 1.06 |
| 90 | 696 | 59.38 | 132.33 | 297.37 | 32.87 | 5.33 | 1.32 |
| 93 | 1044 | 61.33 | 136.53 | 306.84 | 33.96 | 5.81 | 1.4 |
| 97 | 2981 | 63.96 | 142.0 | 319.34 | 35.42 | 6.34 | 1.56 |
| 100 | 851 | 65.87 | 146.29 | 330.67 | 36.53 | 6.74 | 1.7 |
