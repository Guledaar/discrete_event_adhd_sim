"""Generate patient pathway and capacity diagrams for demo.ipynb."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


def _box(ax, x, y, text, width=2.2, height=0.55, fc="#E8F4FD", ec="#1a5276"):
    patch = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.03,rounding_size=0.08",
        linewidth=1.5,
        facecolor=fc,
        edgecolor=ec,
    )
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=9, wrap=True)


def _arrow(ax, x1, y1, x2, y2, label=None, color="#333"):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.2,
            color=color,
            shrinkA=4,
            shrinkB=4,
        )
    )
    if label:
        ax.text((x1 + x2) / 2 + 0.15, (y1 + y2) / 2, label, fontsize=7, color="#555")


def draw_patient_pathway(out_path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 11))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 14)
    ax.axis("off")
    ax.set_title("NHS Adult Autism Assessment — Patient Pathway", fontsize=13, fontweight="bold", pad=12)

    stages = [
        (5, 13.0, "Referral\n(weekdays only)"),
        (5, 11.8, "Triage"),
        (5, 10.6, "Screening"),
        (5, 9.4, "Pre-assessment"),
        (5, 8.2, "Core assessment"),
        (5, 7.0, "Further assessment\n(if needed)"),
        (5, 5.8, "Diagnostic outcome"),
        (5, 4.6, "Post-diagnosis support\n(clinical / other)"),
        (5, 3.4, "Review loop"),
        (5, 2.0, "Discharge"),
    ]
    for x, y, label in stages:
        fc = "#FDEDEC" if "Triage" in label or "outcome" in label else "#E8F4FD"
        _box(ax, x, y, label, width=2.8, fc=fc)

    for i in range(len(stages) - 1):
        _arrow(ax, 5, stages[i][1] - 0.3, 5, stages[i + 1][1] + 0.3)

    exits = [
        (8.2, 11.8, "Reject"),
        (8.2, 10.6, "Discharge"),
        (8.2, 9.4, "Reject"),
        (8.2, 8.2, "Non-diag"),
        (8.2, 7.0, "Non-diag"),
        (8.2, 5.8, "Non-diag"),
    ]
    for x, y, label in exits:
        _box(ax, x, y, f"EXIT\n{label}", width=1.6, fc="#FADBD8", ec="#922b21")
        _arrow(ax, 6.4, y, x - 0.8, y, color="#922b21")

    _arrow(ax, 6.4, 3.4, 7.8, 2.0, label="formal / self", color="#922b21")
    _box(ax, 8.2, 2.0, "EXIT", width=1.4, fc="#FADBD8", ec="#922b21")
    ax.annotate(
        "continue support",
        xy=(4.2, 4.6),
        xytext=(1.5, 6.2),
        arrowprops=dict(arrowstyle="-|>", color="#1a5276"),
        fontsize=8,
        color="#1a5276",
    )

    ax.text(
        5,
        0.5,
        "Capacity-constrained stages use WorkforceHoursResource (Mon–Fri hours)",
        ha="center",
        fontsize=8,
        style="italic",
        color="#555",
    )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def draw_clinical_stage(out_path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4)
    ax.axis("off")
    ax.set_title("Clinical Stage Subprocess (each capacity stage)", fontsize=12, fontweight="bold")

    steps = [
        (1.5, 2, "Sample\nduration"),
        (3.8, 2, "Priority?\n(Bernoulli)"),
        (6.2, 2.8, "Priority\nqueue"),
        (6.2, 1.2, "Standard\nqueue"),
        (8.8, 2, "Wait for\nhour grant"),
        (10.5, 2, "Service\n(timeout)"),
    ]
    for x, y, t in steps:
        _box(ax, x, y, t, width=1.7)
    _arrow(ax, 2.35, 2, 2.95, 2)
    _arrow(ax, 4.65, 2.15, 5.35, 2.65, label="yes")
    _arrow(ax, 4.65, 1.85, 5.35, 1.35, label="no")
    _arrow(ax, 7.05, 2.8, 7.95, 2.2)
    _arrow(ax, 7.05, 1.2, 7.95, 1.8)
    _arrow(ax, 9.65, 2, 9.65, 2)
    ax.text(6.2, 0.4, "WorkforceHoursResource: best-fit job in remaining weekday hours", ha="center", fontsize=8, style="italic")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def draw_workforce_hours(out_path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title("WorkforceHoursResource — Daily Hour Budget", fontsize=12, fontweight="bold")

    _box(ax, 2, 4.5, "Mon–Fri:\nrelease hours\n(e.g. 24 h)", width=2.2, fc="#D5F5E3", ec="#196f3d")
    _box(ax, 6, 4.5, "Priority queue\nserved first", width=2.2)
    _box(ax, 10, 4.5, "Standard queue", width=2.2)
    _box(ax, 6, 2.5, "Best-fit grant:\nlargest job that\nfits hours_left", width=2.8, fc="#FCF3CF", ec="#9a7d0a")
    _box(ax, 6, 0.8, "Track: released / used / unused hours", width=3.2, fc="#F5EEF8", ec="#6c3483")

    _arrow(ax, 3.1, 4.5, 4.9, 4.5)
    _arrow(ax, 7.1, 4.5, 8.9, 4.5)
    _arrow(ax, 6, 4.15, 6, 3.0)
    _arrow(ax, 6, 2.0, 6, 1.15)
    ax.text(6, 5.5, "Weekends: 0 hours released", ha="center", fontsize=9, color="#922b21")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def generate_demo_diagrams(output_dir: Path | str = "assets/demo") -> dict[str, Path]:
    output_dir = Path(output_dir)
    paths = {
        "patient_pathway": draw_patient_pathway(output_dir / "01_patient_pathway.png"),
        "clinical_stage": draw_clinical_stage(output_dir / "02_clinical_stage.png"),
        "workforce_hours": draw_workforce_hours(output_dir / "03_workforce_hours.png"),
    }
    return paths


if __name__ == "__main__":
    for name, path in generate_demo_diagrams().items():
        print(f"{name}: {path}")
