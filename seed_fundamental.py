# 首次灌入估值数据: 建表 + 拉取 + 保存 + 校验
import sys
sys.path.insert(0, r"d:\vibecoding\stock\backend")

from app.database import init_db
from app.data.sina import SinaSource
from app.data import cache

init_db()
src = SinaSource()
df = src.get_fundamentals()
print(f"拉取 {len(df)} 只")
cache.save_fundamental(df)

fund = cache.load_fundamental()
print(f"库中 {len(fund)} 只, 刷新时间 {cache.fundamental_date()}")
print(f"PE>0: {(fund['pe'] > 0).sum()} 只, 10<=PE<=1000: "
      f"{((fund['pe'] >= 10) & (fund['pe'] <= 1000)).sum()} 只")

# 与快照合并测试
snap = cache.load_snapshot()
merged = cache.merge_fundamental(snap)
has_pe = (merged["pe"] > 0).sum()
print(f"快照 {len(snap)} 只, 合并后带PE值 {has_pe} 只")
print(merged[merged["pe"] > 0][["code", "name", "price", "pe", "pb"]]
      .head(5).to_string())
