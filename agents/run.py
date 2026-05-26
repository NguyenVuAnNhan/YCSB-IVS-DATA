from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import __version__
from .backends import ROLE_ORDER, build_backend
from .evidence import build_evidence_summary, utc_now
from .models import validate_agent_output
from .report import render_report


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, default=str) + "\n")


def run_harness(args: argparse.Namespace) -> dict[str, Path]:
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "agent_logs.jsonl"
    if log_path.exists() and not args.append:
        log_path.unlink()

    evidence = build_evidence_summary(args.input, max_files=args.max_files, max_rows_per_file=args.max_rows_per_file)
    evidence_path = out_dir / "evidence_summary.json"
    write_json(evidence_path, evidence)

    backend = build_backend(args.backend)
    state: dict[str, Any] = {
        "schema_version": "agent-state-v1",
        "harness_version": __version__,
        "created_at_utc": utc_now(),
        "input": str(Path(args.input).expanduser()),
        "output_dir": str(out_dir),
        "rounds_requested": args.rounds,
        "backend": backend.name,
        "roles": ROLE_ORDER,
        "safety": {
            "mode": "read_only",
            "agent_shell_access": False,
            "benchmark_data_mutation": False,
            "human_approval_required_for_experiment_changes": True,
        },
        "evidence_summary_path": str(evidence_path),
        "agent_outputs": [],
    }

    append_jsonl(log_path, {"event": "start", "created_at_utc": utc_now(), "backend": backend.name, "input": args.input})
    for round_index in range(1, args.rounds + 1):
        for role in ROLE_ORDER:
            raw_output = backend.generate(role, round_index, evidence, state)
            validation = validate_agent_output(raw_output, role, round_index)
            validation["created_at_utc"] = utc_now()
            validation["backend"] = backend.name
            state["agent_outputs"].append(validation)
            append_jsonl(
                log_path,
                {
                    "event": "agent_output",
                    "created_at_utc": validation["created_at_utc"],
                    "round": round_index,
                    "role": role,
                    "backend": backend.name,
                    "valid": validation["valid"],
                    "errors": validation["errors"],
                    "raw_output": raw_output,
                },
            )

    report = render_report(evidence, state)
    report_path = out_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")

    state_path = out_dir / "state.json"
    write_json(state_path, state)
    append_jsonl(log_path, {"event": "finish", "created_at_utc": utc_now(), "report": str(report_path), "state": str(state_path)})

    return {
        "out_dir": out_dir,
        "evidence_summary": evidence_path,
        "state": state_path,
        "agent_logs": log_path,
        "report": report_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local read-only multi-agent latency-spike investigation.")
    parser.add_argument("--input", required=True, help="CSV, JSON, parquet, .metrics file, existing evidence_summary.json, or directory.")
    parser.add_argument("--out", required=True, help="Output directory for evidence_summary.json, state.json, agent_logs.jsonl, and report.md.")
    parser.add_argument("--rounds", type=int, default=1, help="Number of adversarial analysis rounds to run.")
    parser.add_argument("--backend", default=None, help="Backend name. Defaults to AGENT_LLM_BACKEND or mock.")
    parser.add_argument("--max-files", type=int, default=50, help="Maximum files to read when --input is a directory.")
    parser.add_argument("--max-rows-per-file", type=int, default=None, help="Optional row cap per input file.")
    parser.add_argument("--append", action="store_true", help="Append to an existing agent_logs.jsonl instead of replacing it.")
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be >= 1")
    if args.max_files < 1:
        parser.error("--max-files must be >= 1")
    return args


def main() -> None:
    paths = run_harness(parse_args())
    print(f"Wrote report: {paths['report']}")
    print(f"Wrote state: {paths['state']}")
    print(f"Wrote evidence summary: {paths['evidence_summary']}")
    print(f"Wrote agent logs: {paths['agent_logs']}")


if __name__ == "__main__":
    main()
