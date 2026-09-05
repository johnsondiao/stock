"""新浪财经 API 数据源 - 小时K线 + 全市场实时行情"""

import json
import re
import time
import requests
import pandas as pd
from app.data.base import DataSource
from app.data.rate_limiter import get_rate_limiter
from app.log_config import get_logger

logger = get_logger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn",
}

# A 股代码段（仅普通账户可交易的主板股票）
_SH_RANGES = [
    (600000, 605999),   # 沪市主板
]
_SZ_RANGES = [
    (1, 4999),          # 深市主板 + 中小板
]
# 排除: 创业板(300-301)、科创板(688-689)、北交所(8/4开头) — 普通账户无法交易或需单独开通


def _generate_all_codes() -> list[str]:
    """生成全部 A 股代码（含无效，后续通过行情接口过滤）"""
    codes = set()  # 用 set 去重
    # 上海
    for start, end in _SH_RANGES:
        for i in range(start, end + 1):
            codes.add(f"sh{i:06d}")
    # 深圳
    for start, end in _SZ_RANGES:
        for i in range(start, end + 1):
            codes.add(f"sz{i:06d}")
    return sorted(codes)


# 预生成代码列表（只生成一次）
_ALL_SINA_CODES: list[str] = _generate_all_codes()


class SinaSource(DataSource):
    """新浪财经 API 数据源（小时K线 + 全市场行情）"""

    @property
    def name(self) -> str:
        return "sina"

    def get_realtime_quotes(self, max_retries: int = 3) -> pd.DataFrame:
        """
        通过新浪批量行情接口获取全 A 股实时行情
        每次请求 500 个代码，无效代码返回空数据会被过滤
        非交易时间使用昨收价(pre_close)作为当前价
        """
        limiter = get_rate_limiter()
        batch_size = 500  # 增大批次，减少请求次数
        all_records = []

        logger.info("新浪: 开始获取全市场行情 (%d 个候选代码)...", len(_ALL_SINA_CODES))

        for attempt in range(max_retries):
            try:
                all_records = self._fetch_all_quotes(batch_size, limiter)
                break
            except Exception as e:
                logger.warning("新浪全市场行情获取失败 (第 %d 次): %s", attempt + 1, e)
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                else:
                    raise

        if not all_records:
            logger.error("新浪: 未获取到任何行情数据")
            return pd.DataFrame()

        df = pd.DataFrame(all_records)
        logger.info("新浪: 获取到 %d 只股票行情", len(df))
        return df

    def _fetch_all_quotes(self, batch_size: int, limiter) -> list[dict]:
        """分批获取全部行情"""
        records = []
        total_batches = (len(_ALL_SINA_CODES) + batch_size - 1) // batch_size

        for batch_idx in range(0, len(_ALL_SINA_CODES), batch_size):
            batch = _ALL_SINA_CODES[batch_idx:batch_idx + batch_size]
            limiter.acquire()

            codes_str = ",".join(batch)
            url = f"https://hq.sinajs.cn/list={codes_str}"

            r = requests.get(url, headers=_HEADERS, timeout=15)
            r.raise_for_status()
            r.encoding = 'gbk'  # 新浪行情数据使用 GBK 编码

            for line in r.text.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                parsed = self._parse_quote_line(line)
                if parsed:
                    records.append(parsed)

            # 进度日志
            done = min(batch_idx + batch_size, len(_ALL_SINA_CODES))
            if done % 800 == 0 or done == len(_ALL_SINA_CODES):
                logger.info("新浪: 行情获取进度 %d/%d (有效 %d 只)",
                            done, len(_ALL_SINA_CODES), len(records))

        return records

    @staticmethod
    def _parse_quote_line(line: str) -> dict | None:
        """
        解析新浪行情数据行
        格式: var hq_str_sh600000="浦发银行,0.000,9.070,...";
        字段: 名称[0],今开[1],昨收[2],最新价[3],最高[4],最低[5],买一[6],卖一[7],
              成交量(股)[8],成交额(元)[9],...,日期[30],时间[31],...
        非交易时间 price[3]=0，此时使用 pre_close[2] 作为参考价
        """
        match = re.match(r'var hq_str_(\w+)="(.+)";', line)
        if not match:
            return None

        symbol = match.group(1)
        fields = match.group(2).split(",")

        if len(fields) < 32 or not fields[0]:
            return None

        pre_close = float(fields[2]) if fields[2] else 0
        price = float(fields[3]) if fields[3] else 0

        # 非交易时间 price=0，使用昨收价作为参考价
        if price <= 0:
            if pre_close <= 0:
                return None  # 停牌或完全无效
            price = pre_close  # fallback: 用昨收价

        change = price - pre_close if pre_close > 0 else 0
        pct_change = (change / pre_close * 100) if pre_close > 0 else 0

        # 提取纯数字代码
        code = symbol[2:]  # 去掉 sh/sz 前缀

        return {
            "code": code,
            "name": fields[0],
            "price": price,
            "pct_change": round(pct_change, 2),
            "change": round(change, 4),
            "volume": float(fields[8]) / 100 if fields[8] else 0,  # 股→手
            "amount": float(fields[9]) if fields[9] else 0,
            "high": float(fields[4]) if fields[4] else 0,
            "low": float(fields[5]) if fields[5] else 0,
            "open": float(fields[1]) if fields[1] else 0,
            "pre_close": pre_close,
            "total_mv": 0,      # 新浪接口不提供市值
            "circ_mv": 0,
            "pe": 0,            # 新浪接口不提供 PE
            "pb": 0,
        }

    def get_fundamentals(self, max_retries: int = 3) -> pd.DataFrame:
        """
        拉取全市场估值数据 (PE/PB/总市值)
        数据源: 新浪节点行情接口 (hs_a 节点, 含创业板/科创板, 由调用方过滤)
        每页100条约56页, 仅每日开盘后刷新一次, 用于基本面预筛
        """
        limiter = get_rate_limiter()
        url = ("http://vip.stock.finance.sina.com.cn/quotes_service/api/"
               "json_v2.php/Market_Center.getHQNodeData")

        records: list[dict] = []
        for attempt in range(max_retries):
            try:
                records = []
                page = 1
                while page <= 80:  # 安全上限, 正常约56页结束
                    limiter.acquire()
                    r = requests.get(url, params={
                        "page": page, "num": 100, "sort": "symbol", "asc": 1,
                        "node": "hs_a", "symbol": "", "_s_r_a": "page",
                    }, headers=_HEADERS, timeout=15)
                    r.raise_for_status()
                    text = r.text.strip()
                    if text in ("null", "", "[]"):
                        break
                    # 新浪返回非标准JSON(键无引号), 修正后解析
                    fixed = re.sub(r'([{,])(\w+):', r'\1"\2":', text)
                    items = json.loads(fixed)
                    for it in items:
                        records.append({
                            "code": str(it["code"]).zfill(6),
                            "pe": float(it.get("per") or 0),
                            "pb": float(it.get("pb") or 0),
                            "total_mv": float(it.get("mktcap") or 0),  # 万元
                        })
                    if len(items) < 100:
                        break
                    page += 1
                break
            except Exception as e:
                logger.warning("新浪估值数据拉取失败 (第 %d 次): %s",
                               attempt + 1, e)
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                else:
                    raise

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.drop_duplicates("code").reset_index(drop=True)
        logger.info("新浪: 获取估值数据 %d 只股票", len(df))
        return df

    def get_kline(self, code: str, period: str = "60", count: int = 300, max_retries: int = 3) -> pd.DataFrame:
        """
        获取小时级别K线数据
        :param code: 股票代码
        :param period: "60"(1小时)/"30"/"15"/"5"
        :param count: 获取根数
        :param max_retries: 最大重试次数
        """
        sina_symbol = self._to_sina_symbol(code)
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
        params = {"symbol": sina_symbol, "scale": period, "ma": "no", "datalen": count}

        for attempt in range(max_retries):
            try:
                limiter = get_rate_limiter()
                limiter.acquire()

                r = requests.get(url, params=params, headers=_HEADERS, timeout=15)
                r.raise_for_status()

                items = json.loads(r.text)
                if not items:
                    return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

                records = [
                    {
                        "date": item["day"],
                        "open": float(item["open"]),
                        "high": float(item["high"]),
                        "low": float(item["low"]),
                        "close": float(item["close"]),
                        "volume": float(item["volume"]),
                    }
                    for item in items
                ]
                df = pd.DataFrame(records)
                df["date"] = pd.to_datetime(df["date"])
                return df

            except Exception as e:
                logger.warning("新浪K线 %s 获取失败 (第 %d 次): %s", code, attempt + 1, e)
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                else:
                    raise

        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    @staticmethod
    def _to_sina_symbol(code: str) -> str:
        """股票代码转新浪格式: 深圳=sz+code, 上海=sh+code"""
        if code.startswith(("6", "9")):
            return f"sh{code}"
        return f"sz{code}"
