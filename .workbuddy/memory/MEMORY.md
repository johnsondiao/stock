# 项目长期约定 · A股选股系统

## 运行环境 (踩过的坑)

- **Python 必须用**: `/c/Users/diaoc/miniconda3/python.exe`
  系统 python 与 workbuddy 托管 python 都**没有** requests/pandas, 直接跑会 ModuleNotFoundError
- **环境有 HTTP 代理** `HTTP_PROXY=http://127.0.0.1:12660`。
  访问本地后端服务(127.0.0.1:8000)时 requests 会被劫持到 12660 端口导致超时,
  解决办法二选一:
  - 命令行前置 `no_proxy="127.0.0.1,localhost" NO_PROXY="127.0.0.1,localhost"`
  - 代码内 `requests.Session()` 后设 `session.trust_env = False`
  访问新浪等外部地址则正常走代理, 无需处理
- 后端服务常驻在 `http://127.0.0.1:8000`, `/api/health` 可探活

## 数据架构

- 主库 `backend/data/stock.db`, 表: `daily_kline` / `hourly_kline` /
  `kline_5min` / `kline_15min` / `realtime_snapshot` / `fundamental` /
  `fund_flow` / `screen_task`
- `daily_kline` 的 `amount` 字段**全是 0, 不可用**(别拿它算成交额)
- `fund_flow` 主力资金流(新浪, 2024-08起, 每只500交易日): 下载器
  `fundflow_download.py`, 增量用法 `python fundflow_download.py 60`
- 日线的 `date` 统一格式 `YYYY-MM-DD 00:00:00`, 主键 `(code, date)`, 可安全 upsert
- 数据源为新浪: 实时行情 `hq.sinajs.cn`(批量500只/次),
  K线 `vip.stock.finance.sina.com.cn` 的 `CN_MarketData.getKLineData`(scale=5/60/240)
- 全局限流器 30 请求/分钟; 日线全市场补齐若走限流器需 110 分钟,
  改用并发池约 9 分钟(实测 6~10 只/秒, 并发 8, 零失败)
- **东方财富接口慎用**: `push2his.eastmoney.com` 连发数次后整个域名
  RemoteDisconnected(要等很久才恢复), 且个股资金流历史上限仅 120 根。
  新浪 vip.stock.finance.sina.com.cn 更稳、历史更长(500根), 优先用新浪
- **分钟线全市场覆盖极短 (回测硬约束)**: 新浪 `getKLineData` 分钟线只回传约
  2 周近期数据, 无法补历史。实测各表"每天≥2000只"覆盖起点:
  `kline_5min` 仅 **2026-08-26** 起(约13交易日)、`hourly_kline` 仅 **2026-05-28**
  起(约76天)、`daily_kline` 从 **2025-06-20** 起(约302天)。
  → **依赖5分钟金叉的策略(如 ma_combo)严格回测窗口被卡在约13天**,
    要更长回测必须换数据源(付费分钟/tick 历史)。

## 日线维护机制 (2026-09-10 根治后)

后台更新服务 `data_updater` 三层保障日线:
1. 盘中 `patch_daily()` — 用行情快照真实 OHLC 单事务批量维护当日日线, **零 API 请求**
2. 每日首次进入交易时段 `_ensure_daily_ok()` — 自检并补齐
3. 服务启动 `_startup_daily_check()` — 覆盖跨周末/宕机留下的历史缺口

底层模块 `backend/app/data/daily_backfill.py`, CLI 入口 `backfill_daily.py`。
回归测试见 `backend/tests/test_daily_maintenance.py`。

**两条血泪教训 (9/5 与 9/10 各断一次)**:
1. 改了后台服务代码**必须重启服务**, 否则跑的还是旧代码 —
   9/5 写好的三层保障因服务 9/4 启动后没重启, 白纸一张, 9/7~9/9 连断三天
2. "最新日期 >= 目标日期"不能证明数据完整 — 9/7 盘中 patch 只写过 2 只,
   日期是对的覆盖是空的。现已加 `recent_incomplete_days()`:
   以 hourly_kline 日期为交易日参考, 昨天及之前 daily 覆盖 <2000 只必触发补齐
   (排除今天, 盘中渐进写入属正常)

**服务重启命令** (注意解释器是 ProgramData 的):
`cd backend && C:/ProgramData/miniconda3/python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000`

## Git 约定

- 仓库 `git@github.com:johnsondiao/stock.git`, 分支 main
- `*.db` 走 Git LFS。主库已有 532MB 的旧版本, **再传一份会超 GitHub 免费 1GB 配额**,
  提交数据库前先确认配额; 日常提交代码应排除 `backend/data/stock.db`
- `backup/` 已在 .gitignore 中(本地数据库快照, 不入 LFS)
- 2026-09-07 起 **沙箱内 push 可正常执行**, 上述拦截问题已不复现

## 策略与持仓

- 主力策略 `ma_combo`: 日线趋势确认(MA12/MA60) + 60分钟金叉 + 5分钟金叉, 四段漏斗
- 持仓纪律: 收盘跌破日线 MA12 减仓/清仓, MA60 为最后防线
- 持仓明细维护在 `pm_check.py` 的 `STOCKS` 列表(成本/股数), 复盘前需与实际对账
  (2026-09-10 对账 5 只: 全柴动力500@7.780 / 深圳机场300@6.650 /
   三峡水利100@6.430(9/9新买) / 阳光照明100@3.310 / 哈空调100@5.230;
   中国出版、铜陵有色已清仓, 在 WATCH 仅跟踪)
- 选股走 `POST /api/screen` + `{"strategy":"ma_combo"}`, **同步返回**, 约 8 秒

## 自动化

- 「A股尾盘决策核查」: 每交易日 14:45 自动跑 `pm_check.py` + ma_combo 选股,
  按纪律输出动作清单。修改持仓纪律时记得同步该 automation 的 prompt
