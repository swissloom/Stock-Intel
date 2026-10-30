"""Self-contained HTML dashboard generator.

Renders a single, dependency-free ``output/dashboard.html`` report using
jinja2. The report summarises the optimal strategy configuration, the
Sharpe/Sortino/drawdown metrics, dynamic cost (slippage) and latency logs, the
stop-loss rule, and an inline SVG equity curve. No external CDN or JavaScript is
referenced, so the file is fully self-contained and viewable offline.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from jinja2 import Environment

DEFAULT_OUTPUT_DIR = "output"
DEFAULT_OUTPUT_FILE = "dashboard.html"

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stock-Intel | Quant Strategy Optimization Report</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 2rem;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0b1020; color: #e6e9f0;
  }
  h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
  .sub { color: #8b93a7; margin-bottom: 1.5rem; font-size: .9rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 1rem; margin-bottom: 1.5rem; }
  .card { background: #151c33; border: 1px solid #263150; border-radius: 12px;
          padding: 1rem 1.25rem; }
  .card .label { color: #8b93a7; font-size: .75rem; text-transform: uppercase;
                 letter-spacing: .05em; }
  .card .value { font-size: 1.4rem; font-weight: 600; margin-top: .35rem; }
  .pos { color: #4ade80; } .neg { color: #f87171; }
  table { width: 100%; border-collapse: collapse; margin-top: .5rem; }
  th, td { text-align: left; padding: .5rem .75rem; border-bottom: 1px solid #263150;
           font-size: .9rem; }
  th { color: #8b93a7; font-weight: 500; }
  .section { background: #151c33; border: 1px solid #263150; border-radius: 12px;
             padding: 1.25rem 1.5rem; margin-bottom: 1.5rem; }
  .section h2 { font-size: 1.05rem; margin: 0 0 .75rem; }
  .empty { color: #f87171; font-weight: 600; }
  footer { color: #5a6176; font-size: .8rem; margin-top: 2rem; }
  svg { width: 100%; height: auto; }
</style>
</head>
<body>
  <h1>Stock-Intel &mdash; Quantitative Strategy Optimization</h1>
  <div class="sub">Generated {{ generated_at }} &middot; Walk-forward backtest report</div>

  {% if config %}
  <div class="grid">
    <div class="card"><div class="label">Ticker</div>
      <div class="value">{{ config.ticker }}</div></div>
    <div class="card"><div class="label">Optimal Strategy</div>
      <div class="value">{{ config.strategy }}</div></div>
    <div class="card"><div class="label">Sharpe Ratio</div>
      <div class="value {{ 'pos' if config.sharpe >= 0 else 'neg' }}">{{ config.sharpe }}</div></div>
    <div class="card"><div class="label">Sortino Ratio</div>
      <div class="value {{ 'pos' if config.sortino >= 0 else 'neg' }}">{{ config.sortino }}</div></div>
    <div class="card"><div class="label">Max Drawdown</div>
      <div class="value neg">{{ config.max_drawdown }}</div></div>
    <div class="card"><div class="label">Stop Loss</div>
      <div class="value">{{ config.stop_loss }}</div></div>
  </div>

  <div class="section">
    <h2>Execution &amp; Cost Model</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Estimated dynamic slippage</td><td>{{ config.estimated_slippage }}</td></tr>
      <tr><td>Simulated execution delay (s)</td><td>{{ config.execution_delay_sec }}</td></tr>
      <tr><td>Stop-loss rule</td><td>Exit on {{ (config.stop_loss * 100) | round(1) }}% adverse move</td></tr>
    </table>
  </div>

  {% if equity_svg %}
  <div class="section">
    <h2>Equity Curve (cumulative return)</h2>
    {{ equity_svg | safe }}
  </div>
  {% endif %}
  {% else %}
  <div class="section">
    <p class="empty">No strategy configuration satisfied the risk constraints.</p>
    <p>Try widening the stop-loss range, relaxing the max-drawdown limit, or
       extending the historical date range in <code>config/settings.yaml</code>.</p>
  </div>
  {% endif %}

  <footer>Stock-Intel quantitative pipeline &middot; self-contained report (no external dependencies).</footer>
</body>
</html>
"""


def _build_equity_svg(equity_curve, width: int = 720, height: int = 220) -> str:
    """Render a simple inline SVG line chart from an equity curve iterable."""
    values = [float(v) for v in equity_curve if v is not None]
    if len(values) < 2:
        return ""

    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pad = 10
    n = len(values)

    points = []
    for i, v in enumerate(values):
        x = pad + (width - 2 * pad) * (i / (n - 1))
        y = pad + (height - 2 * pad) * (1 - (v - lo) / span)
        points.append(f"{x:.2f},{y:.2f}")

    polyline = " ".join(points)
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'role="img" aria-label="Equity curve">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1020"/>'
        f'<polyline fill="none" stroke="#4ade80" stroke-width="2" '
        f'points="{polyline}"/>'
        f"</svg>"
    )


def generate_dashboard(
    config: dict | None,
    equity_curve=None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    output_file: str = DEFAULT_OUTPUT_FILE,
) -> str:
    """Render the self-contained HTML dashboard and return its file path.

    Parameters
    ----------
    config:
        The best configuration dict from the optimizer (or ``None``).
    equity_curve:
        Optional iterable of cumulative-return values used to draw the inline
        SVG equity curve.
    output_dir / output_file:
        Destination directory (created if missing) and filename.
    """
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_file)

    equity_svg = _build_equity_svg(equity_curve) if equity_curve is not None else ""

    env = Environment(autoescape=True)
    template = env.from_string(_TEMPLATE)
    html = template.render(
        config=config,
        equity_svg=equity_svg,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    )

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    return output_path
