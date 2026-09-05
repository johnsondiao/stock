# 重试获取行业分类, 失败则尝试备用接口
import time
import akshare as ak

ok = False
for i in range(3):
    try:
        board = ak.stock_board_industry_name_em()
        print("行业板块数:", len(board))
        print(board.head(3).to_string())
        ok = True
        break
    except Exception as e:
        print(f"尝试 {i+1} 失败: {type(e).__name__}: {e}")
        time.sleep(3)

if ok:
    try:
        cons = ak.stock_board_industry_cons_em(symbol=board.iloc[0]["板块名称"])
        print("\n成分股列:", list(cons.columns))
        print(cons.head(3).to_string())
    except Exception as e:
        print("成分股失败:", type(e).__name__, e)
else:
    # 备用: 东财个股所属行业接口
    try:
        df = ak.stock_individual_basic_info_xq(symbol="SH600000")
        print("雪球备用:\n", df.to_string())
    except Exception as e:
        print("备用也失败:", type(e).__name__, e)
