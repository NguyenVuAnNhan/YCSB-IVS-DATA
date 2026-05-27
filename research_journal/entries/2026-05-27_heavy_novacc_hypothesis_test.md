# Heavy NOVACC Hypothesis Test

- Date: 2026-05-27
- Workspace: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA`
- Related repo: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS`
- Status: complete

## Context

The completed heavy NOVACC run `full_view_heavy_novacc_run1` was pulled into:

`/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA/FULL_VIEW_NOVACC/full_view_heavy_novacc_run1`

This entry records the first hypothesis-testing pass over the new data. The detailed report and CSV outputs are in:

`/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA/FULL_VIEW_NOVACC/analysis`

## Notes

The heavy NOVACC run supports the central mechanism: value growth drives TOAST/WAL/buffer work, and read latency grows when the read path touches the growing TOAST working set. Removing explicit VACUUM does not remove the phenomenon.

Key observations:

- Extend phase grows sharply from epochs 1-10 to 91-100: p95 rises from about `4.39 ms` to `62.78 ms`, WAL from about `20 KB/op` to `405 KB/op`, and TOAST blocks from about `32/op` to `436/op`.
- Main run phase also grows: p95 rises from about `0.257 ms` to `2.102 ms`, p99 from about `0.600 ms` to `6.452 ms`, and TOAST blocks from about `6.74/op` to `20.65/op`.
- Reference reads remain effectively flat and do not touch TOAST, which supports the claim that the growing value/TOAST path is the key difference.
- Run p95 correlates strongly with epoch (`rho=0.992`) and client backend relation reads (`rho=0.899`).
- Raw read samples show key size is strongly associated with latency (`rho=0.919`), but local residual p95 is weakly associated with the sampled `>128 KiB` share (`rho=0.074`). This supports "large keys amplify tails" rather than "large-key sampling is the clock."
- Selected page-identity overlap shows substantial churn: across selected epochs/events, the median TOAST heap event page already present at `before_run` is about `0.389`. This supports the useful-page-residency hypothesis, but does not prove key-to-page causality.
- Checkpoint write-time deltas do not track local p95 residuals (`rho=-0.079`), so checkpoint/bgwriter remains weak as the direct trigger.
- In epochs 80-100, sampled read latency breaks down to about `57.7%` query execution, `37.0%` JSON parse, and `3.7%` value join.

## Decisions

The vacuum hypothesis should be phrased carefully. NOVACC confirms that explicit VACUUM is not necessary for late read-tail growth. It may still be an amplifier or cache perturbation in VACC runs, but this one-run NOVACC versus two older VACC runs is not clean enough to isolate vacuum as causal.

The strongest current model remains:

```text
Zipfian JSONB appends
  -> large TOAST-backed values
  -> WAL/storage/buffer amplification during extend
  -> larger read-time TOAST working set
  -> useful TOAST page residency and shared-buffer misses shape read tails
  -> large-key reads amplify the p95/p99 tail
```

## Next Actions

- Compare this heavy NOVACC run against a clean same-host or otherwise comparable heavy VACC rerun.
- Use pg_prewarm interventions to test whether warming the TOAST index and/or heap changes read-tail latency.
- Keep page identity collection targeted; it is useful, but the full file is large enough that future pulls should be compressed first.
