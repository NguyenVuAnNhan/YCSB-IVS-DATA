# pg_prewarm Intervention

## Question

If we deliberately warm heap, TOAST heap, or TOAST index pages before the read phase, do p95 spikes shrink?

## Design

Use `pg_prewarm` as an active intervention. Run this as a separate experiment variant because it changes the cache state.

Candidate modes:

```text
toast_index
heap_toast_index
sampled_hot_toast_pages
full_toast_heap
```

Recommended first pass:

1. `toast_index`
2. `heap_toast_index`
3. `sampled_hot_toast_pages`
4. `full_toast_heap`

## Example SQL

```sql
CREATE EXTENSION IF NOT EXISTS pg_prewarm;

SELECT pg_prewarm('usertable', 'buffer');
SELECT pg_prewarm('<toast_table_name>', 'buffer');
SELECT pg_prewarm('<toast_index_name>', 'buffer');
```

For page-specific tests:

```sql
SELECT pg_prewarm('<toast_table_name>', 'buffer', 'main', first_block, last_block);
```

## Timing

Run prewarm immediately before the main run phase:

```text
after_vacuum
prewarm_start
prewarm_end
before_run
```

Record prewarm as explicit phase events so it can be aligned with p95 and buffer snapshots.

## Interpretation

If p95 spikes shrink after warming TOAST index or selected TOAST heap pages, that supports the useful-cache-residency hypothesis.

Avoid `autoprewarm` for this test because restart-time behavior muddies phase-level causality.

