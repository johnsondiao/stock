"""AKShare 数据获取客户端 - A股行情数据"""

import akshare as ak
import pandas as pd
import requests
import os
import json
from functools import lru_cache
from datetime import datetime, timedelta
from pathlib import Path

# 缓存目录
CACHE_DIR = Path(__file__).parent.parent / "cache" / "hourly"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 通用请求头
_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


def get_stock_list() -> pd.DataFrame:
    """获取A股全部股票列表（代码+名称）"""
    df = ak.stock_zh_a_spot_em()
    return df[["代码", "名称"]].rename(columns={"代码": "code", "名称": "name"})


def get_stock_history(symbol: str, period: str = "daily",
                      start_date: str = None, end_date: str = None,
                      adjust: str = "qfq") -> pd.DataFrame:
    """
    获取单只股票历史行情
    :param symbol: 股票代码，如 "000001"
    :param period: 周期 daily/weekly/monthly/60(1小时)/30/15/5
    :param start_date: 开始日期 YYYYMMDD
    :param end_date: 结束日期 YYYYMMDD
    :param adjust: 复权类型 qfq前复权 hfq后复权
    """
    if not start_date:
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y%m%d")

    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period=period,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust
    )
    df = df.rename(columns={
        "日期": "date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
        "成交额": "amount", "振幅": "amplitude",
        "涨跌幅": "pct_change", "涨跌额": "change", "换手率": "turnover"
    })
    df["date"] = pd.to_datetime(df["date"])
    return df


def _get_secid(symbol: str) -> str:
    """根据股票代码生成东方财富 secid: 深圳=0.xxx, 上海=1.xxx"""
    if symbol.startswith(('6', '9')):
        return f"1.{symbol}"
    return f"0.{symbol}"


def _get_sina_symbol(symbol: str) -> str:
    """根据股票代码生成新浪股票代码: 深圳=sz+code, 上海=sh+code"""
    if symbol.startswith(('6', '9')):
        return f"sh{symbol}"
    return f"sz{symbol}"


def get_hourly_history(symbol: str, period: str = "60",
                       start_date: str = None, end_date: str = None,
                       adjust: str = "qfq") -> pd.DataFrame:
    """
    获取小时级别K线数据（新浪财经 API）
    :param symbol: 股票代码
    :param period: 60(1小时)/30/15/5
    :param start_date: 未使用（新浪接口按 datalen 返回）
    :param end_date: 未使用
    :param adjust: 未使用（新浪返回不复权数据）
    """
    sina_symbol = _get_sina_symbol(symbol)
    url = 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
    # MA169 需要至少 169 根K线，多取一些保证计算准确
    params = {
        'symbol': sina_symbol,
        'scale': period,
        'ma': 'no',
        'datalen': 300,
    }

    r = requests.get(url, params=params, headers=_HEADERS, timeout=15)
    r.raise_for_status()

    import json
    items = json.loads(r.text)
    if not items:
        return pd.DataFrame(columns=['date', 'open', 'close', 'high', 'low', 'volume'])

    records = []
    for item in items:
        records.append({
            'date': item['day'],
            'open': float(item['open']),
            'close': float(item['close']),
            'high': float(item['high']),
            'low': float(item['low']),
            'volume': float(item['volume']),
        })

    df = pd.DataFrame(records)
    df['date'] = pd.to_datetime(df['date'])
    return df


def get_realtime_quotes() -> pd.DataFrame:
    """获取A股实时行情快照（新浪财经 API，稳定可靠）"""
    import json

    # 生成全部 A 股代码范围
    codes = []
    # 深圳: 000xxx, 001xxx, 002xxx, 003xxx, 004xxx, 300xxx, 301xxx
    for prefix in ['000', '001', '002', '003', '004', '300', '301']:
        for i in range(1000):
            codes.append(f"sz{prefix}{i:03d}")
    # 上海: 600xxx, 601xxx, 603xxx, 605xxx, 688xxx
    for prefix in ['600', '601', '603', '605', '688']:
        for i in range(1000):
            codes.append(f"sh{prefix}{i:03d}")

    all_records = []
    batch_size = 800  # 新浪每次最多约 800 个

    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        code_str = ','.join(batch)
        url = f'https://hq.sinajs.cn/list={code_str}'
        try:
            r = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://finance.sina.com.cn',
            }, timeout=15)
            if r.status_code != 200:
                continue

            for line in r.text.strip().split('\n'):
                if '=' not in line or '""' in line:
                    continue
                try:
                    var_part, data_part = line.split('=', 1)
                    code_full = var_part.split('_')[-1]  # sz000001 or sh600000
                    symbol = code_full[2:]  # 000001
                    market = code_full[:2]  # sz or sh

                    fields = data_part.strip(';"\n').split(',')
                    if len(fields) < 32:
                        continue

                    name = fields[0]
                    open_p = float(fields[1]) if fields[1] else 0
                    pre_close = float(fields[2]) if fields[2] else 0
                    price = float(fields[3]) if fields[3] else 0
                    high = float(fields[4]) if fields[4] else 0
                    low = float(fields[5]) if fields[5] else 0
                    volume = float(fields[8]) if fields[8] else 0
                    amount = float(fields[9]) if fields[9] else 0

                    if price <= 0:
                        continue

                    pct_change = round((price - pre_close) / pre_close * 100, 2) if pre_close > 0 else 0

                    all_records.append({
                        'code': symbol,
                        'name': name,
                        'price': price,
                        'pct_change': pct_change,
                        'change': price - pre_close,
                        'volume': volume / 100,  # 转换为手
                        'amount': amount,
                        'high': high,
                        'low': low,
                        'open': open_p,
                        'pre_close': pre_close,
                        'total_mv': 0,  # 新浪接口不提供市值
                        'circ_mv': 0,
                        'pe': 0,
                        'pb': 0,
                    })
                except (ValueError, IndexError):
                    continue
        except Exception:
            continue

    df = pd.DataFrame(all_records)
    return df


# ── 小时K线缓存系统 ──────────────────────────────────────

def _cache_path(symbol: str) -> Path:
    """获取股票缓存文件路径"""
    return CACHE_DIR / f"{symbol}.csv"


def load_cached_hourly(symbol: str) -> pd.DataFrame:
    """加载缓存的小时K线数据"""
    path = _cache_path(symbol)
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, parse_dates=['date'])
        return df
    except Exception:
        return pd.DataFrame()


def save_hourly_cache(symbol: str, df: pd.DataFrame):
    """保存小时K线数据到缓存"""
    if df.empty:
        return
    path = _cache_path(symbol)
    df.to_csv(path, index=False)


def get_hourly_history_cached(symbol: str, period: str = "60",
                               start_date: str = None,
                               full_fetch_len: int = 300,
                               incremental_len: int = 30) -> pd.DataFrame:
    """
    带缓存的小时K线获取
    - 首次调用: 全量获取 full_fetch_len 根K线并缓存
    - 后续调用: 增量获取最新 incremental_len 根K线，与缓存合并
    :return: 合并后的完整K线 DataFrame
    """
    cached = load_cached_hourly(symbol)

    if cached.empty:
        # 首次获取：全量拉取
        df = get_hourly_history(symbol, period=period, start_date=start_date)
        if not df.empty:
            save_hourly_cache(symbol, df)
        return df

    # 增量获取：只拉最新 incremental_len 根
    try:
        sina_symbol = _get_sina_symbol(symbol)
        url = 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
        params = {
            'symbol': sina_symbol,
            'scale': period,
            'ma': 'no',
            'datalen': incremental_len,
        }
        r = requests.get(url, params=params, headers=_HEADERS, timeout=15)
        r.raise_for_status()

        items = json.loads(r.text)
        if not items:
            return cached

        new_records = []
        for item in items:
            new_records.append({
                'date': item['day'],
                'open': float(item['open']),
                'close': float(item['close']),
                'high': float(item['high']),
                'low': float(item['low']),
                'volume': float(item['volume']),
            })
        new_df = pd.DataFrame(new_records)
        new_df['date'] = pd.to_datetime(new_df['date'])

        # 合并：缓存 + 新数据，按日期去重
        merged = pd.concat([cached, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=['date'], keep='last')
        merged = merged.sort_values('date').reset_index(drop=True)

        # 只保留最近 full_fetch_len 根
        if len(merged) > full_fetch_len:
            merged = merged.tail(full_fetch_len).reset_index(drop=True)

        # 更新缓存
        save_hourly_cache(symbol, merged)
        return merged

    except Exception:
        # 增量失败时返回缓存数据
        return cached


def get_cache_stats() -> dict:
    """获取缓存统计信息"""
    files = list(CACHE_DIR.glob("*.csv"))
    total_size = sum(f.stat().st_size for f in files) if files else 0
    return {
        "cached_stocks": len(files),
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "cache_dir": str(CACHE_DIR),
    }
