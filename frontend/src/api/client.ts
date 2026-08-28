import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// ── 类型定义 ──────────────────────────────────────────

export interface StrategyInfo {
  name: string
  description: string
  params_schema: Record<string, ParamSchema>
}

export interface ParamSchema {
  type: string
  label: string
  default: number | string | boolean
  min?: number
  max?: number
  description?: string
}

export interface ScreenRequest {
  strategy: string
  params: Record<string, unknown>
  prefilter?: PrefilterParams
}

export interface PrefilterParams {
  min_price?: number
  max_price?: number
  min_market_cap?: number
  exclude_st?: boolean
}

export interface TaskStatus {
  id: string
  status: string
  strategy: string
  progress: number
  total: number
  matched: number
  skipped: number
  errors: number
}

export interface ScreenResult {
  code: string
  name: string
  price: number
  pct_change: number
  signal: string
  score: number
  above_count?: number
  total_ma?: number
  ma_aligned?: boolean
  fresh_candles?: number
  ma_details?: MADetail[]
  [key: string]: unknown
}

export interface MADetail {
  period: number
  value: number | null
  price_above: boolean
  deviation: number | null
}

export interface ScreenResultData {
  strategy: string
  params: Record<string, unknown>
  total_scanned: number
  matched_count: number
  errors: number
  cache_skipped: number
  results: ScreenResult[]
  completed_at: string
}

export interface SnapshotInfo {
  stocks_count: number
  updated_at: string | null
  is_fresh: boolean
}

// ── API 调用 ──────────────────────────────────────────

/** 获取策略列表 */
export async function fetchStrategies(): Promise<StrategyInfo[]> {
  const res = await api.get<{ strategies: StrategyInfo[] }>('/strategy/list')
  return res.data.strategies
}

/** 获取策略参数 schema */
export async function fetchStrategySchema(name: string): Promise<StrategyInfo> {
  const res = await api.get<StrategyInfo>(`/strategy/${name}`)
  return res.data
}

/** 启动选股任务 */
export async function startScreen(req: ScreenRequest): Promise<{ task_id: string }> {
  const res = await api.post<{ task_id: string }>('/screen', req)
  return res.data
}

/** 查询任务状态 */
export async function fetchTaskStatus(taskId: string): Promise<TaskStatus> {
  const res = await api.get<TaskStatus>(`/screen/${taskId}`)
  return res.data
}

/** 获取选股结果 */
export async function fetchTaskResult(taskId: string): Promise<ScreenResultData> {
  const res = await api.get<ScreenResultData>(`/screen/${taskId}/result`)
  return res.data
}

/** 获取历史任务 */
export async function fetchTaskHistory(limit = 20): Promise<TaskStatus[]> {
  const res = await api.get<{ tasks: TaskStatus[] }>('/screen/history', { params: { limit } })
  return res.data.tasks
}

/** 获取行情快照状态 */
export async function fetchSnapshotInfo(): Promise<SnapshotInfo> {
  const res = await api.get<SnapshotInfo>('/market/snapshot/info')
  return res.data
}

/** 刷新行情 */
export async function refreshMarket(force = false): Promise<{ stocks_count: number }> {
  const res = await api.post<{ stocks_count: number }>('/market/refresh', { force })
  return res.data
}
