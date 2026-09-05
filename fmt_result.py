import json, io

with open(r'd:\vibecoding\stock\screen_result_today.json', encoding='utf-8') as f:
    d = json.load(f)

lines = []
lines.append(f"task_id={d['task_id']}  扫描={d['total_scanned']}  匹配={d['matched_count']}  错误={d['errors']}  完成于 {d['completed_at']}")
lines.append("")
lines.append("| 排名 | 代码 | 名称 | 现价 | 涨跌幅% | 信号 | 评分 | 小时金叉距今 | 5分金叉距今 | 小时鲜 | 5分鲜 |")
for i, r in enumerate(d['results'], 1):
    lines.append("| %d | %s | %s | %.2f | %.2f | %s | %d | %s | %s | %s | %s |" % (
        i, r['code'], r['name'], r['price'], r['pct_change'], r['signal'], r['score'],
        r.get('hourly_cross_bars_ago', '-'), r.get('min_cross_bars_ago', '-'),
        '√' if r.get('hourly_fresh') else '×', '√' if r.get('min_fresh') else '×'))

with io.open(r'd:\vibecoding\stock\screen_report_today.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))
print("done")
