"""组合策略匹配股票指标图: 日线(趋势确认) + 60分钟(定方向) + 5分钟(定入场)"""
import json
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

DB = r"d:\vibecoding\stock\backend\data\stock.db"
OUT_DIR = Path(r"d:\vibecoding\stock\charts")
OUT_DIR.mkdir(exist_ok=True)

UP_COLOR = "#E53935"
DOWN_COLOR = "#43A047"
FAST_COLOR = "#FF9800"
SLOW_COLOR = "#2196F3"


def get_latest_results() -> list[dict]:
    conn = sqlite3.connect(DB)
    row = conn.execute(
        "SELECT result_json FROM screen_task ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return json.loads(row[0])["results"]


def load_kline(code: str, table: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query(
        f"SELECT date, open, high, low, close, volume FROM {table} "
        f"WHERE code=? ORDER BY date", conn, params=(code,)
    )
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def find_cross(df: pd.DataFrame, fast_col: str, slow_col: str) -> int | None:
    for i in range(len(df) - 1, 0, -1):
        cur, prev = df.iloc[i], df.iloc[i - 1]
        if pd.isna(cur[fast_col]) or pd.isna(prev[slow_col]):
            continue
        if cur[fast_col] > cur[slow_col] and prev[fast_col] <= prev[slow_col]:
            return i
    return None


def draw_candles(ax, data: pd.DataFrame):
    for i, row in data.iterrows():
        o, c, h, l = row["open"], row["close"], row["high"], row["low"]
        color = UP_COLOR if c >= o else DOWN_COLOR
        ax.plot([i, i], [l, h], color=color, linewidth=0.7)
        body_low, body_high = min(o, c), max(o, c)
        if body_high == body_low:
            ax.plot([i - 0.3, i + 0.3], [c, c], color=color, linewidth=0.9)
        else:
            ax.add_patch(plt.Rectangle(
                (i - 0.3, body_low), 0.6, body_high - body_low,
                facecolor=color, edgecolor=color,
            ))


def mark_cross(ax, data: pd.DataFrame, fast_col: str, slow_col: str):
    idx = find_cross(data, fast_col, slow_col)
    if idx is not None:
        cy = data[slow_col].iloc[idx]
        ax.plot(idx, cy, marker="^", markersize=11, color="#FFEB3B",
                markeredgecolor="#000000", markeredgewidth=0.7, zorder=5)
        ax.annotate("金叉", xy=(idx, cy), xytext=(idx, cy * 0.985),
                    color="#FFEB3B", fontsize=9, ha="center", fontweight="bold")


def style_ax(ax):
    ax.set_facecolor("#1E1E2E")
    ax.tick_params(colors="#CCCCCC", labelsize=7)
    for spine in ax.spines.values():
        spine.set_color("#444444")
    ax.grid(color="#333333", linewidth=0.4)


def set_xticks(ax, data: pd.DataFrame, fmt: str, n_ticks: int = 5):
    step = max(len(data) // n_ticks, 1)
    xs = list(range(0, len(data), step))
    ax.set_xticks(xs)
    ax.set_xticklabels([data["date"][i].strftime(fmt) for i in xs],
                       rotation=20, fontsize=7, color="#CCCCCC")


def plot_stock(i: int, r: dict, out_path: Path):
    code, name, score = r["code"], r["name"], r["score"]

    daily = load_kline(code, "daily_kline")
    hourly = load_kline(code, "hourly_kline")
    m5 = load_kline(code, "kline_5min")
    if daily.empty or hourly.empty or m5.empty:
        print(f"  {code} data missing (daily={len(daily)}, hourly={len(hourly)}, 5min={len(m5)})")
        return

    for p in (12, 60):
        daily[f"ma{p}"] = daily["close"].rolling(p).mean()
    for p in (24, 60):
        hourly[f"ma{p}"] = hourly["close"].rolling(p).mean()
    for p in (12, 288):
        m5[f"ma{p}"] = m5["close"].rolling(p).mean()

    dd = daily.tail(120).reset_index(drop=True)
    hd = hourly.tail(100).reset_index(drop=True)
    md = m5.tail(400).reset_index(drop=True)

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(8, 12), dpi=110)
    fig.patch.set_facecolor("#1E1E2E")
    for ax in (ax1, ax2, ax3):
        style_ax(ax)

    fig.suptitle(
        f"#{i} {code} {name} | 评分 {score} | "
        f"60分金叉{r.get('hourly_cross_bars_ago')}根前 · 5分金叉{r.get('min_cross_bars_ago')}根前",
        color="#FFFFFF", fontsize=11, y=0.995,
    )

    # 日线: 趋势确认
    draw_candles(ax1, dd)
    ax1.plot(dd.index, dd["ma12"], color=FAST_COLOR, linewidth=1.1, label="MA12")
    ax1.plot(dd.index, dd["ma60"], color=SLOW_COLOR, linewidth=1.1, label="MA60")
    trend_ok = dd["ma12"].iloc[-1] > dd["ma60"].iloc[-1]
    ax1.set_title(f"日线 · 趋势确认 (MA12>MA60: {'成立' if trend_ok else '不成立'})",
                  color="#CCCCCC", fontsize=10, loc="left")
    ax1.legend(loc="upper left", facecolor="#1E1E2E", labelcolor="#CCCCCC",
               edgecolor="#444444", fontsize=8)
    set_xticks(ax1, dd, "%m-%d")

    # 60分钟: 定方向
    draw_candles(ax2, hd)
    ax2.plot(hd.index, hd["ma24"], color=FAST_COLOR, linewidth=1.1, label="MA24")
    ax2.plot(hd.index, hd["ma60"], color=SLOW_COLOR, linewidth=1.1, label="MA60")
    mark_cross(ax2, hd, "ma24", "ma60")
    ax2.set_title("60分钟 · 定方向 (MA24 金叉 MA60)", color="#CCCCCC", fontsize=10, loc="left")
    ax2.legend(loc="upper left", facecolor="#1E1E2E", labelcolor="#CCCCCC",
               edgecolor="#444444", fontsize=8)
    set_xticks(ax2, hd, "%m-%d %H:%M")

    # 5分钟: 定入场
    draw_candles(ax3, md)
    ax3.plot(md.index, md["ma12"], color=FAST_COLOR, linewidth=1.1, label="MA12")
    ax3.plot(md.index, md["ma288"], color=SLOW_COLOR, linewidth=1.1, label="MA288")
    mark_cross(ax3, md, "ma12", "ma288")
    ax3.set_title("5分钟 · 定入场 (MA12 金叉 MA288)", color="#CCCCCC", fontsize=10, loc="left")
    ax3.legend(loc="upper left", facecolor="#1E1E2E", labelcolor="#CCCCCC",
               edgecolor="#444444", fontsize=8)
    set_xticks(ax3, md, "%m-%d %H:%M")

    plt.tight_layout(rect=[0, 0, 1, 0.965])
    plt.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  saved: {out_path.name}")


if __name__ == "__main__":
    results = get_latest_results()
    print(f"matched: {len(results)} stocks")
    for i, r in enumerate(results, 1):
        print(f"plotting #{i} {r['code']} {r['name']} ...")
        plot_stock(i, r, OUT_DIR / f"combo{i:02d}_{r['code']}.png")
    print("all done")
