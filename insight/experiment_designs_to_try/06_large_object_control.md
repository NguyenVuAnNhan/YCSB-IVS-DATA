# Large Object Control

## Question

Would a workload that stores large values as PostgreSQL Large Objects provide cleaner key-to-page mapping than JSONB TOAST?

## Design

This is a control workload, not instrumentation for the existing JSONB experiment.

Use the `lo` extension to store each large logical value as Large Object chunks. Then map:

```text
key -> loid -> pg_largeobject.pageno -> pg_largeobject ctid/block -> pg_buffercache relblocknumber
```

## Value

Potential benefits:

- cleaner object-to-page mapping
- easier chunk-level cache residency tests
- useful comparison against TOAST behavior

## Limits

This changes the storage model:

- JSONB detoast and serialization behavior changes or disappears
- access path becomes Large Object API or `lo_get`
- cleanup requires care, for example `lo_manage`
- results are not apples-to-apples with the current ArrayJSON workload

## Recommendation

Treat this as a low-priority follow-up if page identity, `auto_explain`, and prewarm intervention still leave ambiguity.

