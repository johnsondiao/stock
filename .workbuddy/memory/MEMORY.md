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

- 主库 `backend/data/stock.db`(约 530MB), 表: `daily_kline` / `hourly_kline` /
  `kline_5min` / `realtime_snapshot` / `fundamental` / `screen_task`
- 日线的 `date` 统一格式 `YYYY-MM-DD 00:00:00`, 主键 `(code, date)`, 可安全 upsert
- 数据源为新浪: 实时行情 `hq.sinajs.cn`(批量500只/次),
  K线 `vip.stock.finance.sina.com.cn` 的 `CN_MarketData.getKLineData`(scale=5/60/240)
- 全局限流器 30 请求/分钟; 日线全市场补齐若走限流器需 110 分钟,
  改用并发池约 9 分钟(实测 6~10 只/秒, 并发 8, 零失败)

## 日线维护机制 (2026-09-05 修复后)

后台更新服务 `data_updater` 现在三层保障日线:
1. 盘中 `patch_daily()` — 用行情快照真实 OHLC 单事务批量维护当日日线, **零 API 请求**
2. 每日首次进入交易时段 `_ensure_daily_ok()` — 自检并补齐
3. 服务启动 `_startup_daily_check()` — 覆盖跨周末/宕机留下的历史缺口

底层模块 `backend/app/data/daily_backfill.py`, CLI 入口 `backfill_daily.py`。
回归测试见 `backend/tests/test_daily_maintenance.py`。

**历史教训**: 曾因只维护小时线/5分钟线而漏掉日线, 导致日线冻结 5 个交易日、
选股命中名单整体失效且日志无异常。改动数据维护链路时务必确认三张 K 线表都覆盖。

## Git 约定

- 仓库 `git@github.com:johnsondiao/stock.git`, 分支 main
- `*.db` 走 Git LFS。主库已有 532MB 的旧版本, **再传一份会超 GitHub 免费 1GB 配额**,
  提交数据库前先确认配额; 日常提交代码应排除 `backend/data/stock.db`
- `backup/` 已在 .gitignore 中(本地数据库快照, 不入 LFS)
- 2026-09-07 起 **沙箱内 push 可正常执行**, 上述拦截问题已不复现

## 策略与持仓

- 主力策略 `ma_combo`: 日线趋势确认(MA12/MA60) + 60分钟金叉 + 5分钟金叉, 四段漏斗
- 持仓纪律: 收盘跌破日线 MA12 减仓/清仓, MA60 为最后防线
- 持仓明细维护在 `weekend_review.py` 的 `HOLD` 列表(成本/股数), 复盘前需与实际对账
  (2026-09-07 已按券商截图对账: 铜陵有色实为 100股@7.153, 非此前记的 200股@6.775;
   中国出版已清仓移出)
- 选股走 `POST /api/screen` + `{"strategy":"ma_combo"}`, **同步返回**, 约 8 秒

## 自动化

- 「A股尾盘决策核查」: 每交易日 14:45 自动跑 `pm_check.py` + ma_combo 选股,
  按纪律输出动作清单。修改持仓纪律时记得同步该 automation 的 prompt
