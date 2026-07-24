import axios, { AxiosError, type AxiosInstance } from 'axios'

const baseURL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') || ''

export const api: AxiosInstance = axios.create({
  baseURL,
  timeout: 30000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
})

let csrfToken: string | null = null
let csrfPromise: Promise<string> | null = null

async function ensureCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken
  if (!csrfPromise) {
    csrfPromise = api
      .get('/api/v1/csrf-token')
      .then((res) => {
        const body = res.data as { data?: { csrf_token?: string }; csrf_token?: string }
        csrfToken = body?.data?.csrf_token || body?.csrf_token || ''
        return csrfToken
      })
      .finally(() => {
        csrfPromise = null
      })
  }
  return csrfPromise
}

api.interceptors.request.use(async (config) => {
  const token = sessionStorage.getItem('ttti_access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const method = (config.method || 'get').toLowerCase()
  if (['post', 'put', 'patch', 'delete'].includes(method)) {
    const url = String(config.url || '')
    if (!url.includes('/csrf-token')) {
      try {
        const csrf = await ensureCsrfToken()
        if (csrf) config.headers['X-CSRFToken'] = csrf
      } catch {
        // Server will reject if token is required and missing
      }
    }
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ error?: string; code?: string }>) => {
    const status = error.response?.status
    const code = error.response?.data?.code
    if (status === 401 || code === 'unauthorized') {
      const path = window.location.pathname
      if (!path.startsWith('/login')) {
        window.dispatchEvent(new CustomEvent('ttti:session-expired'))
      }
    }
    return Promise.reject(error)
  },
)

export function getApiErrorMessage(error: unknown, fallback = 'Something went wrong. Please try again.') {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { error?: string } | undefined
    if (data?.error) return data.error
    if (error.code === 'ECONNABORTED') return 'Request timed out. Check your connection.'
    if (!error.response) return 'Network error. Check your connection.'
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}
