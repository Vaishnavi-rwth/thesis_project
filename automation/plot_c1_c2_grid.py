"""
Plot all C1-C2 waveform thumbnails as a single grid image.

Rows  = C1 values (increasing downward)
Cols  = C2 values (increasing rightward)

Output: automation/results_c1_c2/c1_c2_grid.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import pandas as pd

# ── paths ────────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent
CSV  = HERE / "results_c1_c2" / "c1_c2_map_results.csv"
PLOT_DIR = HERE / "results_c1_c2" / "plots"
OUT  = HERE / "results_c1_c2" / "c1_c2_grid.png"

# ── load CSV ─────────────────────────────────────────────────────────────────
df = pd.read_csv(CSV)

c1_vals = sorted(df["C1_F"].unique())
c2_vals = sorted(df["C2_F"].unique())

def fmt_nF(v: float) -> str:
    return f"{v * 1e9:g} nF"

nrows, ncols = len(c1_vals), len(c2_vals)

fig, axes = plt.subplots(
    nrows, ncols,
    figsize=(ncols * 2.2, nrows * 1.6),
    dpi=150,
)

for ri, c1 in enumerate(c1_vals):
    for ci, c2 in enumerate(c2_vals):
        ax = axes[ri][ci]
        row = df[(df["C1_F"] == c1) & (df["C2_F"] == c2)]

        if row.empty or row.iloc[0]["status"] != "ok":
            ax.text(0.5, 0.5, "N/A", ha="center", va="center",
                    transform=ax.transAxes, fontsize=7)
        else:
            # The CSV stores old paths; resolve against the actual plots folder
            png_name = Path(row.iloc[0]["plot_file"]).name
            png_path = PLOT_DIR / png_name
            if png_path.exists():
                img = mpimg.imread(str(png_path))
                ax.imshow(img)
            else:
                ax.text(0.5, 0.5, "missing", ha="center", va="center",
                        transform=ax.transAxes, fontsize=6, color="red")

        ax.set_xticks([])
        ax.set_yticks([])

        # label top row with C2
        if ri == 0:
            ax.set_title(fmt_nF(c2), fontsize=7, pad=2)
        # label left column with C1
        if ci == 0:
            ax.set_ylabel(fmt_nF(c1), fontsize=7, labelpad=2, rotation=0,
                          ha="right", va="center")

fig.suptitle("C\u2081–C\u2082 behaviour map  (rows = C\u2081, cols = C\u2082)",
             fontsize=11, y=1.01)
fig.text(0.5, -0.01, "C\u2082  \u2192", ha="center", fontsize=9)
fig.text(-0.01, 0.5, "C\u2081  \u2192", va="center", fontsize=9, rotation=90)

plt.tight_layout()
fig.savefig(OUT, bbox_inches="tight")
print(f"Saved: {OUT}")
