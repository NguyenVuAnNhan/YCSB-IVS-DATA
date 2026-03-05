from pathlib import Path
import csv

import matplotlib.pyplot as plt
import pandas as pd


DATA_DIR = Path("DATA")
OUTPUT_DIR = Path("results/postgresql_epoch_p95")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def make_plot(csv_path: Path, out_dir: Path) -> Path:
    # Robust parsing: keep Epoch/Operation from the left and p95 from the right.
    # This tolerates occasional malformed middle columns.
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        _ = next(reader, None)  # header
        for row in reader:
            if len(row) < 6:
                continue
            rows.append(
                {
                    "Epoch": row[0],
                    "Operation": row[5],
                    "95thPercentileLatency(us)": row[-3],
                }
            )

    df = pd.DataFrame(rows)
    df["Operation"] = df["Operation"].astype(str).str.upper()
    df["Epoch"] = pd.to_numeric(df["Epoch"], errors="coerce")
    df["95thPercentileLatency(us)"] = pd.to_numeric(df["95thPercentileLatency(us)"], errors="coerce")
    df = df.dropna(subset=["Epoch", "Operation", "95thPercentileLatency(us)"])

    operations = ["READ", "INSERT", "UPDATE", "EXTEND"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=False, sharey=False)
    axes = axes.flatten()

    for ax, operation in zip(axes, operations):
        op_df = df[df["Operation"] == operation]
        if op_df.empty:
            # Keep a blank canvas when this operation is absent in the file.
            ax.set_title(operation)
            ax.set_xlabel("Epoch")
            ax.set_ylabel("P95 Latency (us)")
            ax.grid(False)
            continue

        by_epoch = (
            op_df.groupby("Epoch", as_index=False)["95thPercentileLatency(us)"]
            .mean()
            .sort_values("Epoch")
        )
        ax.plot(by_epoch["Epoch"], by_epoch["95thPercentileLatency(us)"], marker="o")
        ax.set_title(operation)
        ax.set_xlabel("Epoch")
        ax.set_ylabel("P95 Latency (us)")
        ax.grid(True, alpha=0.3)

    fig.suptitle(f"{csv_path.stem}: Epoch vs P95 Latency by Operation", y=1.02)
    fig.tight_layout()

    out_path = out_dir / f"{csv_path.stem}_epoch_vs_p95.png"
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main() -> None:
    files = sorted(DATA_DIR.glob("postgresql_*.csv"))
    if not files:
        raise RuntimeError("No PostgreSQL files found in DATA/")

    generated = []
    for csv_path in files:
        generated.append(make_plot(csv_path, OUTPUT_DIR))

    print(f"Generated {len(generated)} plot(s) in {OUTPUT_DIR}")
    for p in generated:
        print(p)


if __name__ == "__main__":
    main()
