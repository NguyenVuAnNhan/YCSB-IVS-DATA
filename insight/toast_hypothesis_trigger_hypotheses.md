# TOAST Hypothesis Trigger Hypotheses

Updated: 2026-05-04

This file tracks current hypotheses for the recurring main-run p95 latency peaks in `YCSB-IVS-DATA/TOAST_HYPOTHESIS`.

The current run detects prominent main-run p95 peaks at epochs `49, 61, 73, 85, 96`, with spacing `12, 12, 12, 11`. The earlier root-cause hypothesis still stands: Zipfian JSONB appends create large TOAST-backed values, and reads of those values pay detoast / serialization / parsing cost. What remains under investigation is the trigger for the recurring peak timing.

## Current Ranking

| rank | hypothesis | current status | short verdict |
|------------------:|------------------|------------------|------------------|
| 1 | TOAST/value-size amplification | strongly supported | root cause of late tail growth |
| 2 | Variable shared-buffer miss / useful cache state | supported, refined | best immediate trigger signal, but relation totals are too coarse |
| 3 | Vacuum / pre-run cache perturbation | materially supported as amplifier | increases late p95 and spike amplitude, but is not necessary |
| 4 | Large-key sampling crossing the p95 boundary | partially supported | necessary for tail cost, not enough for timing |
| 5 | Checkpoint/bgwriter rhythm | weak as direct trigger | background pressure, not clean spike clock |
| 6 | Client-side JSON parsing | secondary support | amplifier, not primary trigger |

## TOAST_hypothesis_2 Cross-Check, 2026-05-04

The `YCSB-IVS-DATA/TOAST_hypothesis_2` vacuum and no-vacuum runs were checked in `YCSB-IVS-DATA/insight/TOAST_hypothesis_2_hypothesis_check.md`.

Main updates:

-   H1 is confirmed again: both variants reach about `146-147 KiB` p95 value size, about `331 KiB` p99, and about `36 MiB` max by iteration 100, while the reference run remains flat.
-   H2 is refined: run-phase `blks_read` and front-loaded slow-read rates still strongly track p95 spikes, but relation-level `pg_buffercache` snapshots do not show total TOAST heap buffers rewarming upward during the run. The useful cache state is probably page-identity / hot-subset residency, not total relation buffer count.
-   H4 is materially strengthened: removing vacuum reduces late p95 from about `2,590 us` to about `1,645 us` and cuts the largest observed p95 from `4,203 us` to `1,889 us`. However, no-vacuum still shows late front-loaded bursts, so vacuum is an amplifier/perturbation, not a necessary cause.
-   H5 remains weak as a direct trigger: `log_checkpoints` was enabled, but captured checkpoint-message files are empty; counter deltas still show checkpoint pressure mostly outside the exact run-phase p95 peaks.
-   The OS sampler still produced zero disk counters with `auto_all_fallback`, so it remains unable to distinguish OS-cache hits from physical reads.

## H1. TOAST / Value-Size Amplification Is The Root Cause

### Claim

Zipfian JSONB `EXTEND` operations repeatedly rewrite large JSONB values. PostgreSQL stores the enlarged values in TOAST, producing many TOAST chunks, extra WAL, more buffer churn, and expensive later reads.

### Current Evidence

-   Main `run` p95 rises from about `260.9 us` in epochs 1-20 to `2,210.9 us` in epochs 91-100.
-   `reference` p95 stays nearly flat, from about `61.2 us` to `64.4 us`.
-   Value-size tails grow steadily: by epoch 100, p95 value size is about `151 KiB`, p99 about `330 KiB`, max about `37 MiB`, and `6.67%` of rows exceed `128 KiB`.
-   Detoast probes keep key-only lookup cheap while forced JSONB serialization scales with value size. At epoch 100, max-size serialization is about `185.9 ms` with `5,114` shared hits.

### Interpretation

This explains the late tail getting expensive. It does not by itself explain why the p95 peak has a recurring `~12` epoch timing pattern.

## H2. Variable Shared-Buffer Miss / Cache Rewarming Is The Immediate Trigger

### Claim

After `extend` + `VACUUM`, some epochs enter the main `run` phase with a colder or less useful PostgreSQL shared-buffer working set for TOAST reads. Early run reads then repopulate buffers. When enough large TOAST reads miss shared buffers, p95 spikes.

### Current Evidence

-   Peak epochs are front-loaded inside the main run. First-quarter sampled p95 is much higher than quarters 2-4:
    -   epoch `49`: `1,187 us` vs `742 us`
    -   epoch `61`: `1,825 us` vs `1,095 us`
    -   epoch `73`: `3,688 us` vs `1,298 us`
    -   epoch `85`: `5,278 us` vs `1,312 us`
    -   epoch `96`: `6,273 us` vs `1,423 us`
-   Slow-read rate is also front-loaded:
    -   epoch `96`: first quarter `40.88%`, quarters 2-4 mean `14.29%`
-   `run_delta_blks_read` is locally elevated at all p95 peaks:
    -   epoch `49`: `16,775` vs local mean `9,906`
    -   epoch `61`: `23,368` vs `11,944`
    -   epoch `73`: `40,829` vs `23,220`
    -   epoch `85`: `52,376` vs `36,774`
    -   epoch `96`: `80,095` vs `47,637`

### Caveat

`pg_buffercache` was unavailable in the original `TOAST_HYPOTHESIS` capture, so shared-buffer residency was not directly measured there. TOAST_hypothesis_2 captures do include relation-level residency and show large pre-run TOAST heap/index shifts, but they do not show total TOAST heap buffers rewarming upward during the main run.

### Next Confirmation

If we continue this line, the next confirmation needs finer cache identity than relation totals: sample relation block numbers in `pg_buffercache`, map sampled keys to TOAST chunks/pages where possible, or track repeated hot-key residency across before-run and early-run snapshots.

## H3. Large-Key Sampling Pushes Enough Reads Over The p95 Boundary

### Claim

The p95 spike occurs when enough reads in an epoch hit p95/p99/max-size keys. Because p95 is a threshold statistic, a small increase in large-key hits can produce a visible jump.

### Current Evidence

-   Late top-tail reads are much larger than the rest of the sample. In epochs 80-100, the top 5% sampled-latency reads have median key size about `127.8 KiB`; the rest have median about `62.9 KiB`.
-   About `49.9%` of the late top-tail sampled reads are above `128 KiB`.
-   Late sampled latency rises sharply by key-size bin:
    -   `<=64 KiB`: p95 about `1,019 us`
    -   `128-256 KiB`: p95 about `2,856 us`
    -   `256-512 KiB`: p95 about `5,427 us`
    -   `>1 MiB`: p95 about `98,587 us`

### Evidence Against As Full Explanation

Peak epochs do not consistently sample more large keys than nearby non-peak epochs. For example, `sample_pct_gt_128k` is lower than local neighbors at epochs `49`, `61`, and `96`.

### Interpretation

Large-key sampling explains why the p95 tail is expensive, but not the recurring timing. It likely combines with cache state: large keys hurt much more when their TOAST pages are not resident.

## H4. Vacuum Perturbation Disturbs Cache And Writeback State

### Claim

Per-epoch `VACUUM (ANALYZE)` scans the growing heap/TOAST relation and disturbs useful cache state before the main run. It may also interact with dirty-page writeback and checkpoints.

### Current Evidence

-   Vacuum duration grows from near-zero early to hundreds of seconds late.
-   Vacuum progress is dominated by TOAST relation work in late epochs.
-   Vacuum duration is locally elevated at most peaks:
    -   epoch `61`: peak `327.2 s`, local mean `306.5 s`
    -   epoch `85`: peak `540.2 s`, local mean `512.1 s`
    -   epoch `96`: peak `653.1 s`, local mean `598.8 s`

### Evidence Against As Full Explanation

Vacuum happens every epoch. A simple “vacuum makes cache cold” story would predict a smoother trend, not a recurring peak pattern. Vacuum is probably a perturbation that creates the opportunity for cache damage, while another factor controls whether the damage crosses the p95 threshold.

## H5. Checkpoint / Bgwriter Rhythm Amplifies The Tail

### Claim

Checkpoint/bgwriter activity introduces a periodic rhythm that causes or amplifies every `~12` epoch p95 peak.

### Current Evidence

-   Extend and vacuum phases accumulate large checkpoint/write pressure as TOAST grows.
-   This pressure is plausibly part of the broader buffer churn environment.

### Evidence Against Direct Trigger

-   At the p95 peaks, run-phase checkpoint write/sync deltas are almost entirely absent.
-   Only epoch `49` has a non-zero run-phase checkpoint request at a p95 peak, and its run-phase `checkpoint_write_time` and `checkpoint_sync_time` are both `0`.
-   Local peak comparison is mixed: extend/vacuum checkpoint request and write-time counters do not consistently jump at exact p95 peaks.
-   Residual autocorrelation at 12 epochs is weak/mixed for checkpoint/bgwriter series:
    -   p95 residual lag-12 autocorr: `0.356`
    -   cycle checkpoint write time: `0.316`
    -   vacuum checkpoint write time: `0.079`
    -   extend checkpoint write time: `0.077`
    -   cycle checkpoint requests: `0.031`

### Interpretation

Checkpoint/bgwriter pressure is likely an upstream amplifier but is not currently supported as the clean spike clock.

## H6. Server-Side Detoast / Serialization Dominates Slow Reads; Client Parsing Amplifies

### Claim

Slow reads are mostly server-side query execution and JSONB materialization/detoast/serialization, with client-side JSON parsing adding meaningful cost.

### Current Evidence

In epochs 80-100, slow reads spend roughly:

-   `63.1%` of mean latency in `query_execute_us`
-   `31.5%` in `json_parse_us`

The detoast probes show key-only lookup remains cheap, while forced JSONB serialization grows with value size.

### Interpretation

This explains where time is spent once a slow read occurs. It does not explain the recurring timing by itself.

## Immediate Next Tests

1.  **Rerun with working `pg_buffercache` capture.** Completed in TOAST_hypothesis_2. Relation-level residency is now available and shows large pre-run shifts, but it is too coarse to prove useful hot-page rewarming.

2.  **Add early/mid/late run buffer snapshots.** Completed in TOAST_hypothesis_2 at before-run, 10%, 25%, 50%, and after-run. Total TOAST heap buffers generally do not rise during the run; the useful cache question now needs page identity or key-to-page residency.

3.  **Enable PostgreSQL checkpoint logs.** Partially completed. `log_checkpoints = on` was confirmed, but checkpoint-message capture wrote zero rows, so raw start/end alignment is still missing.

4.  **Improve OS sampler or validate device selection.** Still open. TOAST_hypothesis_2 OS disk counters are still all zero and selected with `auto_all_fallback`.

5.  **Compare vacuum/no-vacuum or reduced-vacuum variants.** Completed for no-vacuum. Removing vacuum reduces late p95 and spike amplitude, but does not eliminate late front-loaded bursts.

## Current Working Model

The best current model is:

``` text
Zipfian JSONB appends
  -> large TOAST-backed values
  -> expensive detoast / serialization / parsing
  -> extend + pre-run probes/checkpoints/vacuum churn useful buffer residency
  -> vacuum materially amplifies late cache perturbation and spike amplitude
  -> some epochs begin main run with poorer useful TOAST page residency
  -> first-quarter reads pay elevated shared-buffer read / slow-read rates
  -> enough large cold TOAST reads cross the p95 threshold
  -> recurring visible p95 peaks
```

Checkpoint/bgwriter and vacuum likely contribute to the environment, but the most direct observed trigger is variable run-phase shared-buffer miss pressure. TOAST_hypothesis_2 refines the cache story: total relation-level TOAST heap buffers do not rewarm upward during the run, so the remaining cache question is useful page identity / hot-subset residency rather than total relation residency.