const BASE_URL = '/api/v1'

export interface ApiError {
  status: number
  message: string
  detail?: unknown
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = localStorage.getItem('access_token')
  const headers = new Headers(options.headers || {})

  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const url = `${BASE_URL}${endpoint}`
  const response = await fetch(url, {
    ...options,
    headers,
  })

  if (!response.ok) {
    let errorDetail: unknown = null
    try {
      errorDetail = await response.json()
    } catch {
      errorDetail = await response.text()
    }

    if (response.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }

    const error: ApiError = {
      status: response.status,
      message: (errorDetail && typeof errorDetail === 'object' && 'detail' in errorDetail)
        ? String((errorDetail as { detail: unknown }).detail)
        : response.statusText || 'Request failed',
      detail: errorDetail,
    }
    throw error
  }

  // Handle empty or non-JSON responses (e.g. 204 or text)
  if (response.status === 204) {
    return {} as T
  }

  const contentType = response.headers.get('content-type')
  if (contentType && contentType.includes('application/json')) {
    return (await response.json()) as T
  }

  return (await response.text()) as unknown as T
}
