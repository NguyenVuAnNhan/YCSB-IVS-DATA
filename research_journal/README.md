# YCSB-IVS Research Journal

This directory keeps durable research notes for the PostgreSQL/YCSB value-size experiments. It is separate from raw benchmark outputs so analysis notes, decisions, and experiment plans can evolve without modifying collected data.

## Layout

- `entries/`: dated research notes and experiment plans.

## Conventions

- Use dated Markdown files: `YYYY-MM-DD_short_topic.md`.
- Keep observations, interpretations, and next actions separate.
- Link or name relevant run directories, EC2 hosts, scripts, and settings when known.
- Avoid claiming causality from correlations alone; use language such as "suggests", "is consistent with", and "requires follow-up".
- Do not edit raw run directories as part of journaling.

## Current Focus

The active research question is where PostgreSQL begins to hurt as logical value size increases, especially around growing JSONB, large values, TOAST behavior, WAL amplification, cache residency, checkpoints, dead tuples, HOT-update collapse, and harness artifacts.
