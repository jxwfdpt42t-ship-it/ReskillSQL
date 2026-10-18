from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from rich.console import Console


console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a static HTML showcase report for the project.")
    parser.add_argument(
        "--live",
        type=Path,
        default=Path("reports/live_skill_compare.json"),
    )
    parser.add_argument(
        "--replay",
        type=Path,
        default=Path("reports/replay_collection.json"),
    )
    parser.add_argument(
        "--ablation",
        type=Path,
        default=Path("reports/replay_ablation.json"),
    )
    parser.add_argument("--output", type=Path, default=Path("reports/showcase/index.html"))
    args = parser.parse_args()

    html_text = render_showcase_report(
        live=_read_json(args.live),
        replay=_read_json(args.replay),
        ablation=_read_json(args.ablation),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_text, encoding="utf-8")
    console.print(f"[green]showcase report written:[/green] {args.output}")


def render_showcase_report(*, live: dict[str, Any], replay: dict[str, Any], ablation: dict[str, Any]) -> str:
    live_rows = live.get("rows", [])
    improvements = [row for row in live_rows if not row.get("before_correct") and row.get("after_correct")]
    regressions = [row for row in live_rows if row.get("before_correct") and not row.get("after_correct")]
    ablation_rows = ablation.get("variants", [])
    replay_splits = replay.get("splits", [])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Self-Reskilling Text-to-SQL Report</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #607080;
      --line: #d8e0e8;
      --panel: #f7f9fb;
      --green: #0b7a53;
      --red: #a23a3a;
      --blue: #2357a4;
      --gold: #8a6500;
    }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #ffffff;
      line-height: 1.55;
    }}
    header {{
      padding: 48px min(7vw, 72px) 28px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, #f9fbfd 0%, #ffffff 100%);
    }}
    main {{
      padding: 32px min(7vw, 72px) 64px;
      max-width: 1180px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(32px, 5vw, 58px);
      line-height: 1.05;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 42px 0 12px;
      font-size: 25px;
    }}
    h3 {{
      margin: 22px 0 8px;
      font-size: 18px;
    }}
    p {{
      max-width: 860px;
      color: var(--muted);
    }}
    .lede {{
      font-size: 18px;
      color: #324253;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
      margin-top: 24px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      background: #fff;
    }}
    .metric .label {{
      color: var(--muted);
      font-size: 13px;
    }}
    .metric .value {{
      font-size: 28px;
      font-weight: 750;
      margin-top: 4px;
    }}
    .positive {{ color: var(--green); }}
    .negative {{ color: var(--red); }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 14px 0 26px;
      font-size: 14px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 9px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: var(--panel);
      color: #334;
      font-weight: 700;
    }}
    code, pre {{
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    }}
    pre {{
      overflow: auto;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
      font-size: 12px;
    }}
    .flow {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 8px;
      margin: 16px 0 24px;
    }}
    .step {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: var(--panel);
      font-weight: 650;
    }}
    .case {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      margin: 14px 0;
      background: #fff;
    }}
    .tag {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      background: #eef4ff;
      color: var(--blue);
      font-size: 12px;
      font-weight: 700;
    }}
    footer {{
      border-top: 1px solid var(--line);
      padding: 24px min(7vw, 72px);
      color: var(--muted);
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Self-Reskilling Text-to-SQL Agent</h1>
    <p class="lede">A SQL-aware agent loop that turns execution feedback into versioned query-writing skills and tool policies, then validates the new behavior with live and replay benchmarks.</p>
    <div class="metric-grid">
      {metric_card("Live Comparison", f"{live['before_correct']}/{live['total']} -> {live['after_correct']}/{live['total']}", f"{live['accuracy_delta']:+.1%}", "positive")}
      {metric_card("Replay Collection", f"{replay['before_correct']}/{replay['total']} -> {replay['after_correct']}/{replay['total']}", f"{replay['accuracy_delta']:+.1%}", "positive")}
      {metric_card("Live Fixes / Regressions", f"{live['improvement_total']} / {live['regression_total']}", "bounded regression", "gold")}
      {metric_card("Report Inputs", "live / replay / ablation", "generated from local artifacts", "blue")}
    </div>
  </header>
  <main>
    <h2>Closed-Loop Flow</h2>
    <div class="flow">
      <div class="step">1. Inner agent writes SQL</div>
      <div class="step">2. SQLite judge executes safely</div>
      <div class="step">3. SQL-aware attribution</div>
      <div class="step">4. Skill/tool-policy patch</div>
      <div class="step">5. Candidate skill + diff</div>
      <div class="step">6. Live + replay validation</div>
    </div>

    <h2>Live Evaluation</h2>
    <p>Both sides regenerate SQL from scratch. The old skill is compared with the current live-safe skill on the same BIRD MiniDev slice.</p>
    <table>
      <tr><th>Before</th><th>After</th><th>Delta</th><th>Improvements</th><th>Regressions</th><th>Improved Categories</th></tr>
      <tr>
        <td>{live['before_correct']}/{live['total']} ({live['before_accuracy']:.2%})</td>
        <td>{live['after_correct']}/{live['total']} ({live['after_accuracy']:.2%})</td>
        <td class="positive">{live['accuracy_delta']:+.2%}</td>
        <td>{live['improvement_total']}</td>
        <td>{live['regression_total']}</td>
        <td>{escape_json(live.get('improvements_by_category', {}))}</td>
      </tr>
    </table>

    <h2>Replay Ablation</h2>
    <p>This isolates which compiled policies contribute to replay improvements without extra model calls.</p>
    {ablation_table(ablation_rows)}

    <h2>500-Example Replay Collection</h2>
    {replay_table(replay_splits)}

    <h2>Representative Live Improvements</h2>
    {case_cards(improvements[:3], "improvement")}

    <h2>Remaining Regressions</h2>
    {case_cards(regressions[:3], "regression")}
  </main>
  <footer>
    Generated from local experiment JSON files. BIRD data and reports are local artifacts; do not treat replay numbers as official BIRD leaderboard scores.
  </footer>
</body>
</html>
"""


def metric_card(label: str, value: str, note: str, tone: str) -> str:
    tone_class = {"positive": "positive", "gold": "", "blue": ""}.get(tone, "")
    return f"""<div class="metric">
      <div class="label">{html.escape(label)}</div>
      <div class="value {tone_class}">{html.escape(value)}</div>
      <div class="label">{html.escape(note)}</div>
    </div>"""


def ablation_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{html.escape(str(row['name']))}</td>"
            f"<td>{row['before_correct']}/{row['total']} ({row['before_accuracy']:.2%})</td>"
            f"<td>{row['after_correct']}/{row['total']} ({row['after_accuracy']:.2%})</td>"
            f"<td class=\"positive\">{row['accuracy_delta']:+.2%}</td>"
            f"<td>{row['improvement_total']}</td>"
            f"<td>{row['regression_total']}</td>"
            "</tr>"
        )
    return "<table><tr><th>Variant</th><th>Before</th><th>After</th><th>Delta</th><th>Fixes</th><th>Regressions</th></tr>" + "".join(body) + "</table>"


def replay_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for row in rows:
        total = row["total"]
        body.append(
            "<tr>"
            f"<td>{html.escape(str(row['label']))}</td>"
            f"<td>{row['before_correct']}/{total} ({row['before_accuracy']:.2%})</td>"
            f"<td>{row['after_correct']}/{total} ({row['after_accuracy']:.2%})</td>"
            f"<td class=\"{'positive' if row['accuracy_delta'] >= 0 else 'negative'}\">{row['accuracy_delta']:+.2%}</td>"
            f"<td>{len(row.get('improvements', []))}</td>"
            f"<td>{len(row.get('regressions', []))}</td>"
            "</tr>"
        )
    return "<table><tr><th>Split</th><th>Before</th><th>After</th><th>Delta</th><th>Fixes</th><th>Regressions</th></tr>" + "".join(body) + "</table>"


def case_cards(rows: list[dict[str, Any]], kind: str) -> str:
    if not rows:
        return "<p>No cases.</p>"
    cards = []
    for row in rows:
        cards.append(
            f"""<section class="case">
  <span class="tag">{html.escape(kind)}</span>
  <h3>{html.escape(str(row.get('id')))}: {html.escape(str(row.get('question')))}</h3>
  <p>Before: <strong>{row.get('before_reason')}</strong> | After: <strong>{row.get('after_reason')}</strong></p>
  <p>Category: {html.escape(str(row.get('after_category') or row.get('before_category') or 'unknown'))}</p>
  <h3>Before SQL</h3>
  <pre>{html.escape(str(row.get('before_sql') or ''))}</pre>
  <h3>After SQL</h3>
  <pre>{html.escape(str(row.get('after_sql') or ''))}</pre>
</section>"""
        )
    return "\n".join(cards)


def escape_json(value: Any) -> str:
    return html.escape(json.dumps(value, ensure_ascii=False))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
