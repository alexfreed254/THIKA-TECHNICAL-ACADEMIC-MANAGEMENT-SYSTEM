export type UserRole =
  | 'super_admin'
  | 'dept_admin'
  | 'trainer'
  | 'student'
  | 'examination_officer'
  | 'industry_mentor'
  | 'internal_verifier'
  | 'liaison_officer'
  | 'cdacc_verifier'
  | 'workshop_technician'
  | 'registrar'
  | 'deputy_principal'
  | 'quality_assurance_officer'
  | 'library_hod'
  | 'sports_hod'
  | 'service_clearance_officer'
  | 'environment_hod'
  | 'dean_students'
  | 'finance_officer'
  | string

export interface AuthUser {
  id: string
  full_name: string
  email?: string | null
  role: UserRole
  admission_no?: string | null
  department_id?: string | null
  must_change_password?: boolean
  home_path: string
}

export interface ApiOk<T> {
  ok: true
  data: T
}

export interface ApiErr {
  ok: false
  error: string
  code?: string
}

export type ApiResponse<T> = ApiOk<T> | ApiErr

export interface NavItem {
  label: string
  to: string
  icon: string
  external?: boolean
}

export interface NavSection {
  title?: string
  items: NavItem[]
}
