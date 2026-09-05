# 汇总今日两口径选股结果 + 板块分布
import io
import json
import pandas as pd

ind = pd.read_csv(r"d:\vibecoding\stock\industry_map.csv",
                  encoding="utf-8-sig", dtype=str)
code2sec = dict(zip(ind["code"], ind["sector"]))

HOLD = {"600218", "000089", "000900", "600261", "600202", "000498",
        "600195", "601949", "600051", "600497", "000630"}

lines = []
for tag, path in [("原版 ma_combo", r"d:\vibecoding\stock\screen_result_today.json"),
                  ("基本面过滤版(<20元+PE10~1000)",
                   r"d:\vibecoding\stock\screen_result_fund.json")]:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    lines.append(f"===== {tag} =====")
    lines.append(f"扫描 {d['total_scanned']} / 命中 {d['matched_count']} / "
                 f"错误 {d['errors']} / {d['completed_at']}")
    sec_cnt = {}
    for i, r in enumerate(d["results"], 1):
        sec = code2sec.get(r["code"], "未分类")
        sec_cnt[sec] = sec_cnt.get(sec, 0) + 1
        mark = " ←持仓" if r["code"] in HOLD else ""
        lines.append(
            f"{i:2}. {r['code']} {r['name']} [{sec}] {r['price']} "
            f"{r['pct_change']:+.2f}% {r['signal']} {r['score']}分 "
            f"时叉{r.get('hourly_cross_bars_ago','-')} "
            f"分叉{r.get('min_cross_bars_ago','-')}{mark}")
    top = sorted(sec_cnt.items(), key=lambda x: -x[1])[:5]
    lines.append("板块分布Top5: " + ", ".join(f"{s}×{c}" for s, c in top))
    lines.append("")

with io.open(r"d:\vibecoding\stock\screen_today_full.txt", "w",
             encoding="utf-8") as f:
    f.write("\n".join(lines))
print("saved")
