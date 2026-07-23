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

export async function fetchStudentAttendance() {
  const { data } = await api.get('/api/v1/student/attendance')
  return data.data as {
    attendance: Array<Record<string, unknown>>
    total: number
    present: number
    absent: number
    percentage: number
  }
}

export async function fetchStudentUnits() {
  const { data } = await api.get('/api/v1/student/units')
  return data.data as {
    units: Array<{
      id: string
      code?: string
      name?: string
      class_name?: string
      attended: number
      total: number
      pct: number
    }>
  }
}

export async function fetchStudentMarks(params: { year?: string | number; term?: string | number }) {
  const { data } = await api.get('/api/v1/student/marks', { params })
  return data.data as {
    profile: { full_name?: string; admission_no?: string; mobile_number?: string }
    class_name: string
    dept_name: string
    year: string
    term: string
    units_data: Array<{
      unit: { name?: string; code?: string }
      term?: number
      assessments: Array<{
        assessment_name: string
        assessment_type: string
        marks_obtained: number | null
        max_marks: number
        grade: string | null
        pct: number | null
      }>
      total_obt: number
      total_max: number
      pct: number
      final_grade: string
      has_marks: boolean
    }>
    overall: number
    passed: number
    scored_units: number
  }
}
