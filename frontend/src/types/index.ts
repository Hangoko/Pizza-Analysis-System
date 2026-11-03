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

export interface AuthResponse {
  access_token: string
  token_type: string
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

export interface GraphInfo {
  status: string
  version: string
  source: string
  nodes_count: number
  edges_count: number
  loaded_at: string
  file_path: string
}
