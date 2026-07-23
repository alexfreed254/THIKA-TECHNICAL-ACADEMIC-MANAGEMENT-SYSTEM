import { api } from '@/lib/apiClient'

export interface StudentDashboardData {
  current_month: string
  student: {
    full_name?: string | null
    admission_no?: string | null
  }
  stats: {
    total: number
    pending: number
    approved: number
    rejected: number
    attendance_total?: number
    attendance_percent?: number
    clearance_status?: string
    clearance_stage?: number
    attachment_active?: number
    attachment_total?: number
    logbook_entries?: number
    pending_competencies?: number
  }
  overall_pct: number
  total_attended: number
  attendance_data: Array<{
    id: string
    unit_code?: string
    unit_name?: string
    attended: number
    total_records: number
    last_update?: string | null
  }>
  recent_assessments: Array<{
    id: string
    status?: string
    assessment_type?: string
    uploaded_at?: string
    units?: { name?: string } | null
    classes?: { name?: string } | null
  }>
  unread_notifications?: Array<Record<string, unknown>>
}

export async function fetchStudentDashboard() {
  const { data } = await api.get('/api/v1/student/dashboard')
  return data.data as StudentDashboardData
}
