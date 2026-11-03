export type Role = 'admin' | 'manager' | 'executive' | 'driver'

export interface User {
  id: number
  username: string
  email: string | null
  full_name: string | null
  role: Role
  is_active: boolean
  driver_id: number | null
  created_at: string
  updated_at: string
}

export interface UserCreatePayload {
  username: string
  password: string
  role: Role
  email?: string | null
  full_name?: string | null
  is_active?: boolean
  driver_id?: number | null
}

export interface UserUpdatePayload {
  role?: Role | null
  full_name?: string | null
  email?: string | null
  is_active?: boolean | null
  password?: string | null
  driver_id?: number | null
}

export interface UsersListResponse {
  items: User[]
  total: number
  limit: number
  offset: number
}

export interface AuthResponse {
  access_token: string
  token_type: string
  expires_in?: number
}

export interface Branch {
  id: number
  name: string
  lat: number
  lon: number
  current_queue: number
  is_active: boolean
}

export type Granularity = 'hour' | 'day' | 'week'

export interface StatsPeriod {
  date_from: string | null
  date_to: string | null
  branch_ids: number[] | null
}

export interface KpiResponse {
  total_orders: number
  delivered: number
  canceled: number
  cancel_rate: number
  avg_delivery_minutes: number | null
  median_delivery_minutes: number | null
  p90_delivery_minutes: number | null
  period: StatsPeriod
}

export interface BranchLoadItem {
  branch_id: number
  branch_name: string | null
  orders: number
  share_pct: number
  delivered: number
  canceled: number
  cancel_rate: number
  avg_delivery_minutes: number | null
  deviation_from_mean: number
  deviation_pct: number | null
}

export interface BranchLoadResponse {
  period: StatsPeriod
  total_orders: number
  mean_orders: number
  items: BranchLoadItem[]
}

export interface TimeseriesPoint {
  period_start: string
  orders: number
  delivered: number
  canceled: number
  cancel_rate: number
  avg_delivery_minutes: number | null
}

export interface TimeseriesResponse {
  period: StatsPeriod
  granularity: Granularity
  points: TimeseriesPoint[]
}

export interface DriverRecommendation {
  driver_location: {
    lat: number
    lon: number
  }
  recommended_branch: {
    id: number
    name: string
    lat: number
    lon: number
    current_queue: number
  }
  estimated_travel_time_minutes: number
  effective_score: number
  route_coordinates: [number, number][]
  elapsed_ms: number
}

export interface ClusterCentroid {
  lat: number
  lon: number
}

export interface NearestBranchInfo {
  id: number
  name: string
  distance_km: number
}

export interface ClusterItem {
  cluster_id: number
  centroid: ClusterCentroid
  orders_count: number
  share_pct: number
  nearest_branch: NearestBranchInfo | null
  verdict: string
}

export interface BranchRecommendationResponse {
  n_clusters: number
  orders_count: number
  clusters: ClusterItem[]
  recommendation: string
}

// Reports schemas
export type ReportMetric =
  | 'orders'
  | 'delivered'
  | 'canceled'
  | 'cancel_rate'
  | 'avg_delivery_minutes'
  | 'median_delivery_minutes'
  | 'p90_delivery_minutes'

export type ReportGroupBy =
  | 'branch'
  | 'driver'
  | 'status'
  | 'hour'
  | 'day'
  | 'week'
  | 'hour_of_day'
  | 'weekday'

export type OrderStatusName = 'Pending' | 'InDelivery' | 'Delivered' | 'Canceled'

export type CsvDelimiter = ';' | ','

export interface ReportFilters {
  branch_ids?: number[] | null
  driver_ids?: number[] | null
  statuses?: OrderStatusName[] | null
}

export interface ReportConfig {
  metrics: ReportMetric[]
  group_by?: ReportGroupBy | null
  filters?: ReportFilters
  default_period_days?: number | null
}

export interface ReportTemplate {
  id: number
  name: string
  system_name?: string | null
  description?: string | null
  is_system: boolean
  config: ReportConfig
  created_at?: string
  updated_at?: string
  user_id?: number | null
}

export interface ReportTemplateCreate {
  name: string
  description?: string | null
  config: ReportConfig
  is_system?: boolean
}

export interface ReportTemplateUpdate {
  name?: string
  description?: string | null
  config?: ReportConfig
}

export interface ReportPreview {
  period: {
    date_from: string | null
    date_to: string | null
  }
  columns: string[]
  rows: Record<string, any>[]
}

export interface GraphBBox {
  min_lat: number
  min_lon: number
  max_lat: number
  max_lon: number
}

export interface GraphInfo {
  status: 'not_loaded' | 'loading' | 'ready' | 'failed'
  error: string | null
  version: number | null
  source: string | null
  nodes: number | null
  edges: number | null
  loaded_at: string | null
  bbox: GraphBBox | null
  branch_nodes_cached: number | null
  graph_path: string
  file_exists: boolean
  file_size_bytes: number | null
  file_modified_at: string | null
  upload_max_mb: number
}

export interface GraphWeightsResponse {
  filename: string
  format: string
  rows_total: number
  rows_applied: number
  rows_skipped: number
  edges_updated: number
  graph_version: number
  errors?: string[]
}
