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
  hourly_cross_bars_ago?: number | null
  min_cross_bars_ago?: number | null
  hourly_fresh?: boolean
  min_fresh?: boolean
  [key: string]: unknown
}

export interface ScreenResultData {
  task_id: string
  strategy: string
  params: Record<string, unknown>
  total_scanned: number
  matched_count: number
  errors: number
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

/** 同步执行选股（数据已在缓存，通常几十秒内返回完整结果） */
export async function startScreen(req: ScreenRequest): Promise<ScreenResultData> {
  const res = await api.post<ScreenResultData>('/screen', req, { timeout: 900000 })
  return res.data
}

/** 获取历史选股结果 */
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
