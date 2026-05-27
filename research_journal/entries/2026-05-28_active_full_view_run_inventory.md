# Active FULL_VIEW Run Inventory

- Date: 2026-05-28
- Workspace: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA`
- Related repo: `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS`
- Status: active

## Context

This entry corrects the experiment inventory after checking local artifacts, Codex session history, and the active EC2 hosts.

The important distinction is:

- Completed and pulled locally: usable for analysis now.
- Active remotely: real runs, but not yet final evidence until `exit_status.txt`, derived metrics, and pullback checks exist.
- Failed/partial: do not count as completed evidence.

## Notes

Confirmed completed local runs:

| Run | Host/IP | Local path | Status |
| --- | --- | --- | --- |
| Heavy NOVACC | `13.236.86.169` / `ip-172-31-13-109` | `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA/FULL_VIEW_NOVACC/full_view_heavy_novacc_run1` | `exit_status=0`, pulled and analyzed |
| Heavy VACC run 1 | `43.220.1.203` / `ip-172-31-13-109` | `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA/FULL_VIEW/full_view_run1` | `exit_status=0`, pulled |
| Heavy VACC run 2 | `3.106.232.96` / `ip-172-31-8-159` | `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA/FULL_VIEW/full_view_run2_3_106_232_96` | `exit_status=0`, pulled |

Confirmed active remote runs:

| Run | Host/IP | Remote path | Observed status |
| --- | --- | --- | --- |
| Heavy pg_prewarm heap + TOAST index | `3.104.54.25` / `ip-172-31-8-159`, user `ubuntu` | `/home/ubuntu/ycsb-ec2-bundle/experiment_scripts/benchruns/full_view_heavy_prewarm_heap_toast_index_run1` | Active in tmux `ycsb`; at `2026-05-27T15:08Z`, around `reference_97`; no final `exit_status.txt` yet |
| Heavy VACC clean run 3 | `3.107.72.70` / `ip-172-31-7-101`, user `ycsb` via `ubuntu` sudo | `/home/ycsb/ycsb-ec2-bundle/experiment_scripts/benchruns/full_view_heavy_vacc_run3` | Active in tmux `ycsb`; at `2026-05-27T14:57Z`, finished `extend_98` and entered vacuum; no final pull yet |
| Heavy pg_prewarm TOAST index only | `16.176.19.144` / `ip-172-31-13-109`, user `ubuntu` | `/home/ubuntu/ycsb-ec2-bundle/experiment_scripts/benchruns/full_view_heavy_prewarm_toast_index_run3` | Active in tmux `ycsb`; `run1`/`run2` failed before vacuum due instrumentation optional-field handling; `run3` passed epoch 1 vacuum, recorded TOAST-index-only `pg_prewarm` status `ok`, and completed epoch 1 run phase |

The active VACC run 3 had an earlier failed start from a missing `../analysis/Data/Workload_data` output directory, but the current tmux stream shows the later run is alive and writing `full_view_run3_zipfian_heavy_pure.csv`. Treat the failed start as a launch hiccup, not the status of the current run.

Known partial/salvaged local data:

| Run | Local path | Status |
| --- | --- | --- |
| `full_view_run2` from `3.107.72.70` | `/home/nhan/Desktop/Projects/YCSB/YCSB-IVS-DATA/SALVAGED_3_107_72_70/full_view_run2` | Partial/salvaged; manifest lacks final exit/end status |

## Decisions

The current evidence inventory should be:

1. Heavy NOVACC: completed, pulled, analyzed.
2. Heavy VACC: completed historical full-visibility runs `full_view_run1` and `full_view_run2` are available locally.
3. Heavy VACC clean run 3: active remotely, not yet pulled.
4. Heavy pg_prewarm heap + TOAST index: active remotely, not yet pulled.
5. Heavy pg_prewarm TOAST-index-only: active remotely as clean `run3`, not yet pulled.

Do not mark the two active remote runs as completed until they have final `exit_status.txt`, derived outputs, and local artifact validation.

## Next Actions

- Monitor `3.104.54.25`, `3.107.72.70`, and `16.176.19.144` for completion.
- Compress each completed remote run directory before SCP or rsync pullback.
- Validate manifest, samples, snapshots, derived metrics, and sampler error logs after pullback.
- Add completed-run journal entries for VACC run 3 and pg_prewarm after the artifacts are local.
