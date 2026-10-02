"""Conceptual research overview; no empirical values or established results.

Run with Python plus matplotlib. Outputs are written beside this source.
Contract: persistent, evidence-linked knowledge connects reading with later
research via explicit operations submitted by external agents. One continuous
schematic, 183 x 108 mm; editable PDF/SVG and 600 dpi PNG. No statistical data.
"""
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".agents/skills/nature-figure/scripts"))
from audit_panel_alignment import require_matplotlib_panel_alignment

OUT = Path(__file__).resolve().parent
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"], "font.size": 7,
    "pdf.fonttype": 42, "svg.fonttype": "none",
    "axes.linewidth": 0.8,
})
INK = "#233746"
GRAY = "#637581"
BLUE = "#386C92"
TEAL = "#267F7B"
EDGE = "#CBD5DC"
width_inches, height_inches = 183 / 25.4, 108 / 25.4
fig = plt.figure(figsize=(width_inches, height_inches), facecolor="white")
ax = fig.add_axes([0, 0, 1, 1])
ax.set(xlim=(0, 183), ylim=(0, 108))
ax.set_axis_off()


def text(x, y, s, size=7, color=INK, weight="normal", ha="center"):
    return ax.text(x, y, s, fontsize=size, color=color, weight=weight,
                   ha=ha, va="center", linespacing=1.4)


def box(x, y, w, h, fill="white", edge=EDGE, lw=0.7, radius=1.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=fill, edgecolor=edge, linewidth=lw))


def arrow(a, b, color=GRAY, style="-", rad=0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=7,
        linewidth=0.8, color=color, linestyle=style,
        connectionstyle=f"arc3,rad={rad}", shrinkA=0, shrinkB=0))


text(91.5, 102, "From paper reading to persistent, reusable knowledge", 11, weight="bold")
text(91.5, 95.7, "A data-management middleware for research agents", 7.5, GRAY)

# Sources and interpretation are explicitly outside the middleware.
text(23, 86.2, "Paper-derived inputs", 8, weight="bold")
for x, y in [(6, 69), (8, 70.5), (10, 72)]:
    box(x, y, 10, 11, "#F7F9FB", radius=0.5)
for y in (79.5, 77.4, 75.3):
    ax.plot([12, 17.8], [y, y], color=EDGE, lw=0.7)
text(30, 77.5, "Papers\nCode & data", 6.5)
arrow((23, 68), (23, 61))
box(4, 32, 38, 29, "#F0F5F8")
text(23, 55, "External agent", 8, BLUE, "bold")
text(23, 44.5, "Read & interpret\nJudge identity & relations", 6.3)
text(23, 26, "Understanding + evidence", 6.1, GRAY)

# The proposed data-management scope is the visual focus.
box(59, 23, 70, 66, "#F0F7F6", TEAL, 1.15, 2)
text(94, 83.4, "Knowledge middleware", 9, TEAL, "bold")
text(94, 76.8, "Persistent semantic records", 7, weight="bold")

# A small explicit graph retains concrete records and supporting context.
box(64, 61, 24, 9, "white", "#A6C5C4")
text(76, 65.5, "Method / resource", 6.1)
box(101, 61, 23, 9, "white", "#A6C5C4")
text(112.5, 65.5, "Claim + conditions", 5.8)
arrow((101, 65.5), (88, 65.5), TEAL)
text(94.5, 69, "about", 5.2, GRAY)
box(64, 46, 24, 9, "white", "#A6C5C4")
text(76, 50.5, "Experiment", 6.3)
box(101, 46, 23, 9, "white", "#A6C5C4")
text(112.5, 50.5, "Evidence", 6.3)
arrow((76, 55), (76, 61), TEAL)
arrow((112.5, 61), (112.5, 55), TEAL)
arrow((88, 50.5), (101, 50.5), TEAL)
text(94, 41.5, "Identity  ·  Provenance  ·  Versions", 6.3, TEAL)
box(64, 27, 60, 10, "#DDEDEB", edge="none")
text(94, 32, "Query  ·  Compose  ·  Update", 7, TEAL, "bold")

# Explicit write and read interfaces, with labels outside connector paths.
arrow((42, 53), (59, 53), BLUE)
text(50.5, 57, "Write", 6.1, BLUE)
arrow((59, 39), (42, 39), TEAL)
text(50.5, 43, "Retrieve", 5.8, TEAL)

# Later sessions consume stored knowledge; the agent makes task judgments.
text(159, 86.2, "Later research tasks", 8, weight="bold")
box(146, 32, 34, 47, "#F0F5F8")
text(163, 72.8, "External agent", 7.6, BLUE, "bold")
text(163, 63.3, "Method selection", 6.5)
text(163, 53.6, "Evaluation design", 6.5)
text(163, 43.9, "Result interpretation", 6.1)
arrow((129, 65), (146, 65), TEAL)
text(137.5, 69, "Retrieve", 5.8, TEAL)
arrow((146, 47), (129, 47), BLUE)
text(137.5, 51, "Query", 6.1, BLUE)
text(163, 26, "Reuse with context", 6.1, GRAY)

# A return path illustrates continuing accumulation, not autonomous inference.
ax.plot([163, 163, 94], [22, 14.5, 14.5], lw=0.8, color=TEAL)
arrow((94, 14.5), (94, 23), TEAL)
text(131, 9.2, "New readings & checks → explicit updates", 6.2, TEAL)
text(4, 14, "Across papers", 6.6, GRAY, ha="left")
text(4, 9, "Across sessions", 6.6, GRAY, ha="left")

fig.canvas.draw()
require_matplotlib_panel_alignment(fig,
    json_out=str(OUT / "overview.alignment.json"), strict=True)
fig.savefig(OUT / "overview.pdf", facecolor="white")
fig.savefig(OUT / "overview.svg", facecolor="white")
fig.savefig(OUT / "overview.png", dpi=600, facecolor="white")
plt.close(fig)
