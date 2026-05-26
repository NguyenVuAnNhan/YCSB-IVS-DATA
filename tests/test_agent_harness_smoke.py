from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_metrics.csv"


class AgentHarnessSmokeTest(TestCase):
    def test_mock_backend_runs_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "agent_test"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agents.run",
                    "--input",
                    str(FIXTURE),
                    "--out",
                    str(out_dir),
                    "--rounds",
                    "1",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr + result.stdout)
            for name in ["evidence_summary.json", "state.json", "agent_logs.jsonl", "report.md"]:
                self.assertTrue((out_dir / name).exists(), msg=f"missing {name}")

            evidence = json.loads((out_dir / "evidence_summary.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(evidence["latency"]["spike_windows"]), 1)
            state = json.loads((out_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["backend"], "mock")
            self.assertTrue(all(output["valid"] for output in state["agent_outputs"]))
