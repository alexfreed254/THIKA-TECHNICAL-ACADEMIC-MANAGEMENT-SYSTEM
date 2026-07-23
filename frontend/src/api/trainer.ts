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

export interface FormativeAssessment {
  id: string
  assessment_type: 'Oral' | 'Practical' | 'Theory' | string
  assessment_name: string
  max_marks: number
  year?: number
  term?: number
}

export interface MarksEntryStudent {
  student_id: string
  user_profiles?: { full_name?: string; admission_no?: string } | null
}

export interface MarksEntryData {
  class_list: Array<{ id: string; name: string }>
  units_list: Array<{ id: string; code?: string; name?: string }>
  students_list: MarksEntryStudent[]
  assessments: FormativeAssessment[]
  oral_list: FormativeAssessment[]
  practical_list: FormativeAssessment[]
  theory_list: FormativeAssessment[]
  marks_map: Record<string, Record<string, number | null>>
  class_id: string
  unit_id: string
  year: number
  term: number
}

export interface PoeAssessment {
  id: string
  status?: string
  assessment_type?: string
  assessment_no?: string | number
  uploaded_at?: string
  reviewed_at?: string
  review_note?: string | null
  marks_obtained?: number | null
  max_marks?: number | null
  user_profiles?: { full_name?: string; admission_no?: string } | null
  reviewer?: { full_name?: string } | null
  units?: { name?: string; code?: string } | null
  classes?: { id?: string; name?: string } | null
  unit_id?: string
  [key: string]: unknown
}

export interface PoeUnitBucket {
  id: string
  name: string
  code?: string
  total: number
  pending: number
  approved: number
  rejected: number
  assessments: PoeAssessment[]
}

export interface PoeClassBucket {
  id: string
  name: string
  units: PoeUnitBucket[]
  unit_count: number
  pending: number
}

export interface AssessmentsData {
  classes: PoeClassBucket[]
  status_counts: {
    total: number
    pending: number
    approved: number
    rejected: number
  }
}

export interface AttendanceStudent {
  student_id: string
  user_profiles?: { full_name?: string; admission_no?: string } | null
}

export interface AttendanceData {
  class_list: Array<{ id: string; name: string }>
  units_list: Array<{ id: string; code?: string; name?: string }>
  students_list: AttendanceStudent[]
  attendance_submitted: boolean
  active_event: {
    id: string
    event_type: string
    week?: number
    lesson?: string
    note?: string | null
  } | null
  class_id: string
  unit_id: string
  week: number
  lesson: string
  year: number
  term: number
  lessons: Array<{ id: string; label: string }>
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

export async function fetchMarksEntry(params: {
  class_id?: string
  unit_id?: string
  year?: number | string
  term?: number | string
}) {
  const { data } = await api.get('/api/v1/trainer/marks-entry', { params })
  return data.data as MarksEntryData
}

export async function saveMark(payload: {
  assessment_id: string
  student_id: string
  marks: string | number
}) {
  const { data } = await api.post('/api/v1/trainer/marks-entry/save-mark', payload)
  return data as { ok?: boolean; success?: boolean; cleared?: boolean; error?: string }
}

export async function addAssessment(payload: {
  unit_id: string
  class_id: string
  assessment_type: string
  assessment_name: string
  max_marks?: number
  year?: number
  term?: number
}) {
  const { data } = await api.post('/api/v1/trainer/marks-entry/add-assessment', payload)
  return data.data as { assessment: FormativeAssessment }
}

export async function fetchAssessments() {
  const { data } = await api.get('/api/v1/trainer/assessments')
  return data.data as AssessmentsData
}

export async function reviewAssessment(
  id: string,
  payload: { action: 'approve' | 'reject'; review_note?: string },
) {
  const { data } = await api.post(`/api/v1/trainer/assessments/${id}/review`, payload)
  return data.data as { status: string }
}

export async function fetchAttendance(params: {
  class_id?: string
  unit_id?: string
  week?: number | string
  lesson?: string
  year?: number | string
  term?: number | string
}) {
  const { data } = await api.get('/api/v1/trainer/attendance', { params })
  return data.data as AttendanceData
}

export async function submitAttendance(payload: {
  class_id: string
  unit_id: string
  unit_code?: string
  week: number | string
  lesson: string
  year: number | string
  term: number | string
  statuses: Record<string, 'present' | 'absent'>
}) {
  const { data } = await api.post('/api/v1/trainer/attendance/submit', payload)
  return data.data as { submitted: boolean }
}
