"""Self-contained HTML dashboard generator.

Renders a single, dependency-free ``output/index.html`` report using
jinja2. The report summarises the optimal strategy configuration, the
institutional performance metrics (Total Return %, CAGR %, Buy & Hold benchmark
return %, Win Rate %, Profit Factor, Total Trades, Average Trade Duration),
the Sharpe/Sortino/drawdown metrics, dynamic cost (slippage %) and latency (ms)
logs, the stop-loss rule, an inline SVG Strategy-vs-Benchmark equity curve with
a legend, and a Full Parameter Sweep (Top 10) table ranked by Profit Factor then
Sharpe. No external CDN or JavaScript is referenced, so the file is fully
self-contained and viewable offline.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone

from jinja2 import Environment

DEFAULT_OUTPUT_DIR = "output"
DEFAULT_OUTPUT_FILE = "index.html"

# Strategy / benchmark stroke colours reused by the SVG and the HTML legend.
_STRATEGY_COLOUR = "#4ade80"
_BENCHMARK_COLOUR = "#60a5fa"

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
  .legend { display: flex; gap: 1.5rem; margin-bottom: .5rem; font-size: .85rem;
            color: #c3c9d8; }
  .legend .swatch { display: inline-block; width: 14px; height: 3px;
                    margin-right: .4rem; vertical-align: middle; }
  .tag-unprofitable { color: #f87171; font-weight: 600; font-size: .75rem;
                      text-transform: uppercase; letter-spacing: .04em; }
  .tag-ok { color: #4ade80; font-size: .75rem; }
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
    {% if details %}
    <div class="card"><div class="label">Period</div>
      <div class="value" style="font-size:1rem">{{ details.period_start }} &rarr; {{ details.period_end }}</div></div>
    <div class="card"><div class="label">Total Return</div>
      <div class="value {{ 'pos' if details.total_return_pct >= 0 else 'neg' }}">{{ details.total_return_pct | round(2) }}%</div></div>
    <div class="card"><div class="label">CAGR (annualized)</div>
      <div class="value {{ 'pos' if details.cagr_pct >= 0 else 'neg' }}">{{ details.cagr_pct | round(2) }}%</div></div>
    <div class="card"><div class="label">Buy &amp; Hold Benchmark</div>
      <div class="value {{ 'pos' if details.benchmark_total_return_pct >= 0 else 'neg' }}">{{ details.benchmark_total_return_pct | round(2) }}%</div></div>
    <div class="card"><div class="label">Win Rate</div>
      <div class="value">{{ details.win_rate_pct | round(1) }}%</div></div>
    <div class="card"><div class="label">Profit Factor</div>
      <div class="value">{{ details.profit_factor | round(2) }}</div></div>
    <div class="card"><div class="label">Total Trades</div>
      <div class="value">{{ details.total_trades }}</div></div>
    <div class="card"><div class="label">Avg Trade Duration</div>
      <div class="value">{{ details.avg_trade_duration_days | round(1) }} d</div></div>
    {% endif %}
    <div class="card"><div class="label">Sharpe Ratio</div>
      <div class="value {{ 'pos' if config.sharpe >= 0 else 'neg' }}">{{ config.sharpe }}</div></div>
    <div class="card"><div class="label">Sortino Ratio</div>
      <div class="value {{ 'pos' if config.sortino >= 0 else 'neg' }}">{{ config.sortino }}</div></div>
    <div class="card"><div class="label">Max Drawdown</div>
      <div class="value neg">{{ (config.max_drawdown * 100) | round(2) }}%</div></div>
    <div class="card"><div class="label">Stop Loss</div>
      <div class="value">{{ config.stop_loss }}</div></div>
  </div>

  <div class="section">
    <h2>Execution &amp; Cost Model</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      {% if details %}
      <tr><td>Dynamic slippage</td><td>{{ details.dynamic_slippage_pct | round(4) }}%</td></tr>
      <tr><td>Latency</td><td>{{ details.latency_ms | round(1) }} ms</td></tr>
      {% else %}
      <tr><td>Estimated dynamic slippage</td><td>{{ config.estimated_slippage }}</td></tr>
      <tr><td>Simulated execution delay (s)</td><td>{{ config.execution_delay_sec }}</td></tr>
      {% endif %}
      <tr><td>Stop-loss rule</td><td>Exit on {{ (config.stop_loss * 100) | round(1) }}% adverse move</td></tr>
    </table>
  </div>

  {% if equity_svg %}
  <div class="section">
    <h2>Equity Curve (cumulative return)</h2>
    {% if benchmark_present %}
    <div class="legend">
      <span><span class="swatch" style="background:{{ strategy_colour }}"></span>Strategy</span>
      <span><span class="swatch" style="background:{{ benchmark_colour }}"></span>Buy &amp; Hold Benchmark</span>
    </div>
    {% endif %}
    {{ equity_svg | safe }}
  </div>
  {% endif %}

  {% if top10 %}
  <div class="section">
    <h2>Full Parameter Sweep (Top 10)</h2>
    <p class="sub" style="margin-bottom:.5rem">Ranked by Profit Factor, then Sharpe Ratio.</p>
    <table>
      <tr>
        <th>#</th><th>Strategy</th><th>Stop Loss</th><th>Profit Factor</th>
        <th>Sharpe</th><th>Sortino</th><th>Win Rate %</th><th>Total Return %</th>
        <th>CAGR %</th><th>Max Drawdown %</th><th>Status</th>
      </tr>
      {% for row in top10 %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ row.strategy }}</td>
        <td>{{ row.stop_loss }}</td>
        <td>{{ row.profit_factor | round(2) }}</td>
        <td>{{ row.sharpe | round(3) }}</td>
        <td>{{ row.sortino | round(3) }}</td>
        <td>{{ row.win_rate_pct | round(1) }}</td>
        <td class="{{ 'pos' if row.total_return_pct >= 0 else 'neg' }}">{{ row.total_return_pct | round(2) }}</td>
        <td class="{{ 'pos' if row.cagr_pct >= 0 else 'neg' }}">{{ row.cagr_pct | round(2) }}</td>
        <td class="neg">{{ (row.max_drawdown * 100) | round(2) }}</td>
        <td>{% if row.unprofitable %}<span class="tag-unprofitable">Unprofitable</span>{% else %}<span class="tag-ok">OK</span>{% endif %}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endif %}
  {% else %}
  <div class="section">
    <p class="empty">No strategy configuration satisfied the risk constraints.</p>
    <p>Try widening the stop-loss range, relaxing the max-drawdown limit, or
       extending the historical date range in <code>config/settings.yaml</code>.</p>
  </div>

  {% if top10 %}
  <div class="section">
    <h2>Full Parameter Sweep (Top 10)</h2>
    <p class="sub" style="margin-bottom:.5rem">Ranked by Profit Factor, then Sharpe Ratio.
       No configuration satisfied the profitability / risk guardrails.</p>
    <table>
      <tr>
        <th>#</th><th>Strategy</th><th>Stop Loss</th><th>Profit Factor</th>
        <th>Sharpe</th><th>Sortino</th><th>Win Rate %</th><th>Total Return %</th>
        <th>CAGR %</th><th>Max Drawdown %</th><th>Status</th>
      </tr>
      {% for row in top10 %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ row.strategy }}</td>
        <td>{{ row.stop_loss }}</td>
        <td>{{ row.profit_factor | round(2) }}</td>
        <td>{{ row.sharpe | round(3) }}</td>
        <td>{{ row.sortino | round(3) }}</td>
        <td>{{ row.win_rate_pct | round(1) }}</td>
        <td class="{{ 'pos' if row.total_return_pct >= 0 else 'neg' }}">{{ row.total_return_pct | round(2) }}</td>
        <td class="{{ 'pos' if row.cagr_pct >= 0 else 'neg' }}">{{ row.cagr_pct | round(2) }}</td>
        <td class="neg">{{ (row.max_drawdown * 100) | round(2) }}</td>
        <td>{% if row.unprofitable %}<span class="tag-unprofitable">Unprofitable</span>{% else %}<span class="tag-ok">OK</span>{% endif %}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
  {% endif %}
  {% endif %}

  <footer>Stock-Intel quantitative pipeline &middot; self-contained report (no external dependencies).</footer>
</body>
</html>
"""


def _clean_series(curve) -> list[float]:
    """Return a list of finite floats from an equity-curve iterable."""
    if curve is None:
        return []
    out: list[float] = []
    for v in curve:
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(fv):
            out.append(fv)
    return out


def _polyline_points(values, lo, span, width, height, pad, n) -> str:
    points = []
    for i, v in enumerate(values):
        x = pad + (width - 2 * pad) * (i / (n - 1))
        y = pad + (height - 2 * pad) * (1 - (v - lo) / span)
        points.append(f"{x:.2f},{y:.2f}")
    return " ".join(points)


def _build_equity_svg(
    equity_curve,
    benchmark_curve=None,
    width: int = 720,
    height: int = 220,
) -> str:
    """Render an inline SVG line chart of the equity curve.

    When ``benchmark_curve`` is supplied (and has >= 2 finite points), a second
    series is drawn on the SAME chart, scaled to a shared min/max so the two
    curves are directly comparable, in a distinct stroke colour, with inline
    ``<text>`` legend labels. When the benchmark is absent or too short the
    function falls back to the original single-series render.

    Pure inline SVG only: no JavaScript, no external asset references.
    """
    strat = _clean_series(equity_curve)
    if len(strat) < 2:
        return ""

    bench = _clean_series(benchmark_curve)
    has_bench = len(bench) >= 2

    pad = 10
    # Shared scale across both series so they are visually comparable.
    all_vals = list(strat) + (bench if has_bench else [])
    lo, hi = min(all_vals), max(all_vals)
    span = (hi - lo) or 1.0

    strat_points = _polyline_points(strat, lo, span, width, height, pad, len(strat))

    svg = [
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'role="img" aria-label="Strategy vs benchmark equity curve">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0b1020"/>',
    ]

    if has_bench:
        bench_points = _polyline_points(
            bench, lo, span, width, height, pad, len(bench)
        )
        svg.append(
            f'<polyline fill="none" stroke="{_BENCHMARK_COLOUR}" stroke-width="2" '
            f'stroke-dasharray="6 4" points="{bench_points}"/>'
        )

    svg.append(
        f'<polyline fill="none" stroke="{_STRATEGY_COLOUR}" stroke-width="2" '
        f'points="{strat_points}"/>'
    )

    if has_bench:
        # Inline SVG legend (kept inside the chart so the SVG is self-describing
        # even without the surrounding HTML legend).
        svg.append(
            f'<rect x="{pad + 4}" y="{pad}" width="14" height="3" '
            f'fill="{_STRATEGY_COLOUR}"/>'
        )
        svg.append(
            f'<text x="{pad + 22}" y="{pad + 5}" fill="#c3c9d8" '
            f'font-size="11" font-family="sans-serif">Strategy</text>'
        )
        svg.append(
            f'<rect x="{pad + 4}" y="{pad + 14}" width="14" height="3" '
            f'fill="{_BENCHMARK_COLOUR}"/>'
        )
        svg.append(
            f'<text x="{pad + 22}" y="{pad + 19}" fill="#c3c9d8" '
            f'font-size="11" font-family="sans-serif">Buy &amp; Hold</text>'
        )

    svg.append("</svg>")
    return "".join(svg)


def generate_dashboard(
    config: dict | None,
    equity_curve=None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    output_file: str = DEFAULT_OUTPUT_FILE,
    details: dict | None = None,
    benchmark_curve=None,
) -> str:
    """Render the self-contained HTML dashboard and return its file path.

    Parameters
    ----------
    config:
        The best configuration dict from the optimizer (or ``None``). Retains
        the original 8 keys (ticker, strategy, stop_loss, sharpe, sortino,
        max_drawdown, execution_delay_sec, estimated_slippage).
    equity_curve:
        Optional iterable of cumulative-return values used to draw the inline
        SVG strategy equity curve.
    output_dir / output_file:
        Destination directory (created if missing) and filename. ``output_file``
        defaults to ``index.html`` and must not be renamed (the Cloudflare Pages
        deploy and the CI artifact-verify guard depend on ``output/index.html``).
    details:
        Optional institutional-metrics payload from the optimizer's opt-in
        details channel (total_return_pct, cagr_pct, profit_factor,
        win_rate_pct, total_trades, avg_trade_duration_days,
        benchmark_total_return_pct, latency_ms, dynamic_slippage_pct,
        period_start, period_end, sweep, top10, ...). ``None`` preserves the
        original (pre-FEAT-002) rendering.
    benchmark_curve:
        Optional iterable for the Buy & Hold benchmark equity curve. When
        provided it is drawn alongside the strategy curve with a legend. Falls
        back to ``details['benchmark_equity_curve']`` when not passed directly.
    """
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_file)

    # Benchmark curve can be passed directly or sourced from details.
    bench = benchmark_curve
    if bench is None and details is not None:
        bench = details.get("benchmark_equity_curve")

    equity_svg = ""
    if equity_curve is not None:
        equity_svg = _build_equity_svg(equity_curve, benchmark_curve=bench)

    benchmark_present = len(_clean_series(bench)) >= 2 and equity_svg != ""
    top10 = details.get("top10") if details is not None else None

    env = Environment(autoescape=True)
    template = env.from_string(_TEMPLATE)
    html = template.render(
        config=config,
        details=details,
        equity_svg=equity_svg,
        benchmark_present=benchmark_present,
        strategy_colour=_STRATEGY_COLOUR,
        benchmark_colour=_BENCHMARK_COLOUR,
        top10=top10,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    )

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    return output_path
