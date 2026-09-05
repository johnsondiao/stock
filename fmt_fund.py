import json, io

with open(r"d:\vibecoding\stock\screen_result_fund.json", encoding="utf-8") as f:
    d = json.load(f)

lines = [f"扫描={d['total_scanned']} 匹配={d['matched_count']} 错误={d['errors']} 完成于 {d['completed_at']}", ""]
for i, r in enumerate(d["results"], 1):
    lines.append(f"{i}. {r['code']} {r['name']}  {r['price']}  {r['pct_change']:+.2f}%  "
                 f"{r['signal']} {r['score']}分")

with io.open(r"d:\vibecoding\stock\screen_report_fund.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("done")
