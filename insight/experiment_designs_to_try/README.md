# Experiment Designs To Try

Generated: 2026-05-15

These notes collect follow-up experiments for the TOAST_hypothesis_2 cache and latency investigation. The goal is to keep the ideas separate from completed analysis while making each one concrete enough to implement or run later.

## Designs

| file | purpose | priority |
|---|---|---:|
| `01_pg_buffercache_page_identity.md` | Track page identity and useful cache survival during early run windows. | High |
| `02_auto_explain_slow_reads.md` | Use sampled execution plans with buffers to validate whether slow reads are server-side and page-heavy. | Medium |
| `03_pg_stat_statements_phase_cost.md` | Capture per-phase aggregate query cost, buffer reads/hits, I/O timing, and WAL from PostgreSQL. | Medium |
| `04_pg_freespacemap_fragmentation.md` | Measure heap and TOAST free-space fragmentation across VACC and NOVACC. | Medium |
| `05_pg_prewarm_intervention.md` | Actively warm selected relations/pages before run to test whether p95 spikes shrink. | High |
| `06_large_object_control.md` | Optional control workload using Large Objects for cleaner key-to-page chunk mapping. | Low |

## Recommended Order

1. Run with `pg_buffercache` page identity and `pg_freespacemap` enabled.
2. Add `pg_stat_statements` snapshots around phases to check aggregate server-side cost.
3. Add `auto_explain` only for focused peak-window reruns.
4. Run `pg_prewarm` intervention variants after page-identity data identifies likely useful pages.
5. Consider the Large Object control only if JSONB/TOAST page identity remains ambiguous.
