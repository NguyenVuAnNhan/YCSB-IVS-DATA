# Highlighted Main-Run p95 Latency Peaks

Detected with `scipy.signal.find_peaks` using prominence `>=80 us`, distance `>=5 epochs`, then keeping the five most prominent peaks.

## Outputs

- `main_run_p95_and_key_size_distribution_peaks_highlighted.png`
- `main_run_p95_and_key_size_threshold_shares_peaks_highlighted.png`
- `main_run_p95_latency_peaks.csv`

## Peaks

| peak | Epoch | p95_us | prominence | size_p95_kib | size_p99_kib | pct_gt_128k | pct_gt_256k |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 48 | 516 | 111.0 | 71.01 | 157.83 | 1.58 | 0.63 |
| 2 | 59 | 808 | 317.0 | 87.5 | 192.62 | 2.64 | 0.77 |
| 3 | 71 | 1133 | 496.0 | 104.69 | 232.45 | 3.41 | 0.85 |
| 4 | 84 | 2033 | 1366.0 | 123.74 | 276.67 | 4.57 | 1.15 |
| 5 | 97 | 2981 | 2130.0 | 142.0 | 319.34 | 6.34 | 1.56 |
