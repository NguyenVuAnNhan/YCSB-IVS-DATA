# auto_explain Slow Reads

## Question

Do slow reads show higher PostgreSQL execution time and buffer activity, or is most of the tail outside the server?

## Design

Use `auto_explain` as targeted corroboration for focused reruns, not as continuous instrumentation for every experiment.

Recommended settings:

```sql
ALTER SYSTEM SET shared_preload_libraries = 'auto_explain';
ALTER SYSTEM SET auto_explain.log_min_duration = '2ms';
ALTER SYSTEM SET auto_explain.log_analyze = on;
ALTER SYSTEM SET auto_explain.log_buffers = on;
ALTER SYSTEM SET auto_explain.log_timing = on;
ALTER SYSTEM SET auto_explain.log_wal = on;
ALTER SYSTEM SET auto_explain.log_format = 'json';
ALTER SYSTEM SET auto_explain.sample_rate = 0.05;
```

PostgreSQL restart is required after changing `shared_preload_libraries`.

## Run Scope

Use focused windows first:

```text
45-50
56-61
68-73
81-86
94-100
```

Increase `sample_rate` or reduce `log_min_duration` only for short peak-window reruns.

## Expected Evidence

Useful signals:

- stable plan shape but larger execution time
- larger `shared read` counts on slow reads
- larger `shared hit` counts for large TOAST-backed values
- unexpected temp or WAL activity during read phases

Limits:

- does not identify exact hot/cold `relblocknumber`s
- does not explain client-side JSON parsing by itself

