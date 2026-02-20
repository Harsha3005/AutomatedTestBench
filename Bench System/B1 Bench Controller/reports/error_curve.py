"""
Matplotlib error curve generator for ISO 4064 test certificates.

Produces a PNG image matching the Chart.js visualization in error_curve.js.
Uses Agg backend for headless rendering (no display required).
"""

import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


def generate_error_curve_image(test_summary, width=7.0, height=3.5, dpi=150):
    """
    Generate an error curve PNG from a TestSummary dataclass.

    Args:
        test_summary: TestSummary with .q_points list of QPointSummary
        width: Figure width in inches
        height: Figure height in inches
        dpi: Resolution (150 default for print quality)

    Returns:
        bytes: PNG image data
    """
    q_points = test_summary.q_points

    # Separate pass/fail points
    pass_flows, pass_errors, pass_labels = [], [], []
    fail_flows, fail_errors, fail_labels = [], [], []

    for qp in q_points:
        if qp.error_pct is None:
            continue
        flow = qp.target_flow_lph or qp.actual_flow_lph
        if not flow or flow <= 0:
            continue
        if qp.passed:
            pass_flows.append(flow)
            pass_errors.append(qp.error_pct)
            pass_labels.append(qp.q_point)
        else:
            fail_flows.append(flow)
            fail_errors.append(qp.error_pct)
            fail_labels.append(qp.q_point)

    # Build MPE envelope from q_points (unique flow/mpe pairs, sorted)
    mpe_map = {}
    for qp in q_points:
        flow = qp.target_flow_lph or qp.actual_flow_lph
        if flow and flow > 0 and qp.mpe_pct:
            mpe_map[flow] = abs(qp.mpe_pct)
    mpe_flows = sorted(mpe_map.keys())
    mpe_upper = [mpe_map[f] for f in mpe_flows]
    mpe_lower = [-mpe_map[f] for f in mpe_flows]

    # Create figure
    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    # MPE envelope (dashed red with fill between)
    mpe_color = (239/255, 68/255, 68/255, 0.6)
    mpe_fill = (239/255, 68/255, 68/255, 0.05)
    if mpe_flows:
        ax.plot(mpe_flows, mpe_upper, color=mpe_color, linewidth=2,
                linestyle='--', label='MPE Limit', zorder=1)
        ax.plot(mpe_flows, mpe_lower, color=mpe_color, linewidth=2,
                linestyle='--', zorder=1)
        ax.fill_between(mpe_flows, mpe_lower, mpe_upper,
                        color=mpe_fill, zorder=0)

    # Pass points (green circles)
    if pass_flows:
        ax.scatter(pass_flows, pass_errors, c='#10b981', edgecolors='#059669',
                   linewidths=1.5, s=60, zorder=3, label='Pass')

    # Fail points (red X markers)
    if fail_flows:
        ax.scatter(fail_flows, fail_errors, c='#ef4444', edgecolors='#dc2626',
                   linewidths=1.5, s=60, marker='X', zorder=3, label='Fail')

    # Zero reference line
    ax.axhline(y=0, color='#cbd5e1', linewidth=0.8, zorder=0)

    # Logarithmic X-axis
    ax.set_xscale('log')

    # Axis labels
    ax.set_xlabel('Flow Rate (L/h)', fontsize=11, fontweight='600', color='#64748b')
    ax.set_ylabel('Error (%)', fontsize=11, fontweight='600', color='#64748b')

    # Grid
    ax.grid(True, which='major', color=(0, 0, 0, 0.04), linewidth=0.5)
    ax.grid(True, which='minor', color=(0, 0, 0, 0.02), linewidth=0.3)

    # Tick styling
    ax.tick_params(axis='both', labelsize=9, colors='#94a3b8')
    ax.xaxis.set_major_formatter(ticker.ScalarFormatter())
    ax.xaxis.get_major_formatter().set_scientific(False)
    ax.yaxis.set_major_formatter(ticker.PercentFormatter(decimals=0))

    # Y-axis padding
    all_errors = pass_errors + fail_errors
    if all_errors and mpe_upper:
        y_max = max(max(abs(e) for e in all_errors), max(mpe_upper))
        ax.set_ylim(-y_max * 1.3, y_max * 1.3)
    elif mpe_upper:
        y_max = max(mpe_upper)
        ax.set_ylim(-y_max * 1.3, y_max * 1.3)

    # Legend
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(loc='upper right', fontsize=9, framealpha=0.9,
                  edgecolor='#e2e8f0')

    # Spine styling
    for spine in ax.spines.values():
        spine.set_color('#e2e8f0')
        spine.set_linewidth(0.8)

    plt.tight_layout(pad=0.5)

    # Render to PNG bytes
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf.read()
