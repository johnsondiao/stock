# 重建快照 + 端到端验证估值合并
import sys
sys.path.insert(0, r"d:\vibecoding\stock\backend")

from app.data.provider import get_provider
from app.data import cache

p = get_provider()
snap = p.get_all_stocks(force_refresh=True)
print(f"快照重建: {len(snap)} 只")

merged = cache.merge_fundamental(cache.load_snapshot())
has_pe = (merged["pe"] > 0).sum()
print(f"合并估值后带PE: {has_pe}/{len(merged)}")

# 东财同款过滤: 价格<20 + PE 10~1000 (净利>0 由 PE>0 隐含)
df = merged[(merged["price"] < 20) & (merged["pe"] >= 10) & (merged["pe"] <= 1000)]
print(f"东财同款基本面池: {len(df)} 只")
print(df.sort_values("pe")[["code", "name", "price", "pe", "pb"]].head(8).to_string())
