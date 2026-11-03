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

export interface ReportTemplate {
  id: number
  name: string
  system_name?: string | null
  description?: string | null
  is_system: boolean
  config?: Record<string, unknown>
  created_at?: string
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
