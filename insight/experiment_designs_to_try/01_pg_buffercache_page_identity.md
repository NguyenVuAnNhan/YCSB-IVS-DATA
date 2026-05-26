# pg_buffercache Page Identity

## Question

Does p95 latency spike when the useful heap, TOAST heap, or TOAST index page set is displaced before the read phase and then rewarmed during early run operations?

## Design

Collect relation-level residency plus sampled page identity for:

- `usertable`
- TOAST heap
- TOAST index

Use `(relation_role, relfilenode, relforknumber, relblocknumber)` as the page identity key. Keep `relforknumber = 0` initially.

## Capture Schedule

All epochs:

```text
before_run
run_progress_5pct
run_progress_10pct
after_run
```

Focus windows:

```text
45-50
56-61
68-73
81-86
94-100
```

Focus-window events:

```text
after_extend
after_vacuum
before_run
run_progress_1pct
run_progress_2pct
run_progress_5pct
run_progress_10pct
run_progress_25pct
run_progress_50pct
after_run
```

## Current Harness Knobs

```bash
SPIKE_TRIGGER_PAGE_IDENTITY_ENABLED=1
SPIKE_TRIGGER_BUFFER_PROGRESS_PCTS="1 2 5 10 25 50"
SPIKE_TRIGGER_PAGE_IDENTITY_SAMPLE_MOD=32
SPIKE_TRIGGER_PAGE_IDENTITY_MIN_USAGECOUNT=4
```

Set `SPIKE_TRIGGER_PAGE_IDENTITY_SAMPLE_MOD=1` for full capture.

## Analysis

For each relation role and event pair:

```text
survival_pct = pages(before_run intersect run_5pct) / pages(before_run)
new_pct = pages(run_5pct - before_run) / pages(run_5pct)
evicted_pct = pages(before_run - run_5pct) / pages(before_run)
```

Compare VACC and NOVACC at known peak and non-peak epochs.

