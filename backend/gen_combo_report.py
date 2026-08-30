"""生成组合策略选股报告手机版 HTML（配合 Edge 无头打印转 PDF）"""
import json
import sqlite3
from pathlib import Path

DB = r"d:\vibecoding\stock\backend\data\stock.db"
OUT = Path(r"d:\vibecoding\stock\combo_report.html")

conn = sqlite3.connect(DB)
row = conn.execute(
    "SELECT result_json, params, created_at FROM screen_task ORDER BY created_at DESC LIMIT 1"
).fetchone()
conn.close()

result = json.loads(row[0])
created = row[2]
stocks = result["results"]

cards = []
for i, s in enumerate(stocks, 1):
    score = s["score"]
    score_cls = "hot" if score >= 88 else ("warm" if score >= 75 else "cool")
    cards.append(f"""
<div class="stock-page">
  <div class="stock-head">
    <div class="rank">#{i}</div>
    <div class="info">
      <div class="name">{s['code']} {s['name']}</div>
      <div class="meta">现价 {s['price']:.2f} 元 · 涨跌 {s['pct_change']:+.2f}%</div>
    </div>
    <div class="score {score_cls}">{score}分</div>
  </div>
  <div class="tags">
    <span>60分金叉 {s.get('hourly_cross_bars_ago')}根前</span>
    <span>5分金叉 {s.get('min_cross_bars_ago')}根前</span>
    <span>{'60分新鲜' if s.get('hourly_fresh') else '60分较早'}</span>
    <span>{'5分新鲜' if s.get('min_fresh') else '5分较早'}</span>
  </div>
  <img src="charts/combo{i:02d}_{s['code']}.png" alt="{s['code']}">
</div>""")

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>组合策略选股报告</title>
<style>
  @page {{ size: 96mm 200mm; margin: 6mm 5mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Microsoft YaHei", sans-serif; font-size: 10px; color: #222; }}
  .cover {{
    background: linear-gradient(135deg, #1a2a4a, #2c3e6b);
    color: #fff; border-radius: 10px; padding: 18px 14px; margin-bottom: 10px;
  }}
  .cover h1 {{ font-size: 17px; margin-bottom: 5px; }}
  .cover .sub {{ font-size: 9.5px; color: #b8c4e0; line-height: 1.6; }}
  .cover .big {{ font-size: 26px; color: #ffd76e; font-weight: bold; margin: 8px 0 2px; }}
  .cover .big small {{ font-size: 10px; color: #b8c4e0; font-weight: normal; }}
  h2 {{
    font-size: 12px; color: #1a2a4a; margin: 12px 0 6px;
    border-left: 4px solid #e8b93c; padding-left: 7px;
  }}
  .list-table {{ width: 100%; border-collapse: collapse; font-size: 8.5px; }}
  .list-table th {{ background: #2c3e6b; color: #fff; padding: 3.5px 3px; text-align: left; font-weight: normal; }}
  .list-table td {{ border-bottom: 1px solid #dde3ee; padding: 3.5px 3px; }}
  .list-table tr:nth-child(even) td {{ background: #f5f7fb; }}
  .stock-page {{ page-break-before: always; }}
  .stock-page:first-of-type {{ page-break-before: auto; }}
  .stock-head {{
    display: flex; align-items: center; gap: 8px;
    background: #f5f7fb; border-radius: 8px; padding: 8px 10px; margin-bottom: 6px;
  }}
  .rank {{ font-size: 16px; font-weight: bold; color: #e8b93c; }}
  .info {{ flex: 1; }}
  .name {{ font-size: 12px; font-weight: bold; color: #1a2a4a; }}
  .meta {{ font-size: 9px; color: #667; margin-top: 1px; }}
  .score {{ font-size: 14px; font-weight: bold; padding: 3px 8px; border-radius: 6px; color: #fff; }}
  .score.hot {{ background: #c0392b; }}
  .score.warm {{ background: #e67e22; }}
  .score.cool {{ background: #5d7290; }}
  .tags {{ margin-bottom: 6px; }}
  .tags span {{
    display: inline-block; background: #eef2f9; border: 1px solid #d5deed;
    color: #3a5580; border-radius: 4px; padding: 1px 6px; font-size: 8.5px; margin: 1px 2px 1px 0;
  }}
  .stock-page img {{ width: 100%; border-radius: 6px; display: block; }}
  .note {{ font-size: 8.5px; color: #778; margin-top: 8px; line-height: 1.6; }}
</style>
</head>
<body>

<div class="cover">
  <h1>组合策略选股报告</h1>
  <div class="sub">60分钟定方向 · 日线确认趋势 · 5分钟定入场（四段漏斗）</div>
  <div class="big">{len(stocks)} <small>只入选 / 扫描 {result['total_scanned']} 只</small></div>
  <div class="sub">数据截至 2026-08-28 收盘 · 报告生成 {created}</div>
</div>

<h2>入选清单</h2>
<table class="list-table">
  <tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>分</th><th>60分金叉</th><th>5分金叉</th></tr>
  {''.join(f"<tr><td>{i}</td><td>{s['code']}</td><td>{s['name']}</td><td>{s['price']:.2f}</td><td><b>{s['score']}</b></td><td>{s.get('hourly_cross_bars_ago')}根前</td><td>{s.get('min_cross_bars_ago')}根前</td></tr>" for i, s in enumerate(stocks, 1))}
</table>
<div class="note">
  评分含义: 98=双周期新鲜金叉+价格确认 / 90=5分新鲜+价格确认 / 75=仅5分新鲜 / 62=金叉在窗口内但不新鲜。<br>
  图表说明: 每只股票三张图——日线(趋势确认) → 60分钟(定方向) → 5分钟(定入场)，黄色三角为金叉位置。
</div>

{''.join(cards)}

</body>
</html>
"""

OUT.write_text(html, encoding="utf-8")
print(f"report generated: {OUT} ({len(stocks)} stocks)")
