import { api } from '@/lib/apiClient'

export interface TrainerDashboardData {
  current_month: string
  stats: {
    total: number
    pending: number
    approved: number
    rejected: number
    trips_uploaded: number
    clearance_pending: number
    summative_nyc?: number
  }
  pending_assessments: Array<Record<string, unknown>>
  units_list: Array<{ id: string; code?: string; name?: string }>
  analytics: {
    att_unit_labels: string[]
    att_unit_present: number[]
    att_unit_absent: number[]
    assess_unit_labels: string[]
    assess_unit_pending: number[]
    assess_unit_approved: number[]
    assess_unit_rejected: number[]
    trend_labels: string[]
    trend_present: number[]
    trend_absent: number[]
  }
}

export async function fetchTrainerDashboard() {
  const { data } = await api.get('/api/v1/trainer/dashboard')
  return data.data as TrainerDashboardData
}

export async function fetchRecentNotifications(limit = 10) {
  const { data } = await api.get('/api/v1/notifications/recent', { params: { limit } })
  return data.data as {
    notifications: Array<Record<string, unknown>>
    unread_count: number
  }
}
