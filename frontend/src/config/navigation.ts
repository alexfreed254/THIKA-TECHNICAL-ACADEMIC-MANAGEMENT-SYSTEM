import type { NavSection, UserRole } from '@/types'

const trainerNav: NavSection[] = [
  {
    items: [{ label: 'Dashboard', to: '/trainer/dashboard', icon: 'tachometer-alt' }],
  },
  {
    title: 'Attendance',
    items: [
      { label: 'Mark Attendance', to: '/trainer/attendance', icon: 'clipboard-list' },
      { label: 'Biometric Attendance', to: '/biometric/', icon: 'fingerprint', external: true },
      { label: 'View & Download Attendance', to: '/trainer/attendance-history', icon: 'download' },
    ],
  },
  {
    title: 'Assessments',
    items: [
      { label: 'Trainee POE Review', to: '/trainer/assessments', icon: 'tasks' },
      { label: 'Marks Entry', to: '/trainer/marks-entry', icon: 'edit' },
      { label: 'Import Marks', to: '/trainer/marks-import', icon: 'file-excel' },
      { label: 'Summative Assessments', to: '/summative/', icon: 'award', external: true },
      { label: 'My Portfolio (POE)', to: '/trainer/portfolio', icon: 'folder-open' },
    ],
  },
  {
    title: 'Trips',
    items: [
      { label: 'Trip Reports', to: '/academic-trips', icon: 'bus', external: true },
      { label: 'Upload Trip Report', to: '/academic-trips/upload', icon: 'plus-circle', external: true },
    ],
  },
  {
    title: 'Clearance',
    items: [{ label: 'Clearance Approvals', to: '/clearance/approver', icon: 'clipboard-check', external: true }],
  },
  {
    title: 'Account',
    items: [
      { label: 'My Profile', to: '/auth/profile', icon: 'user-circle', external: true },
      { label: 'Notifications', to: '/notifications', icon: 'bell', external: true },
    ],
  },
]

const studentNav: NavSection[] = [
  {
    title: 'Overview',
    items: [{ label: 'Dashboard', to: '/student/dashboard', icon: 'tachometer-alt' }],
  },
  {
    title: 'Learning',
    items: [
      { label: 'My Units', to: '/student/units', icon: 'book-open' },
      { label: 'Lesson Attendance', to: '/student/attendance', icon: 'clipboard-list' },
      { label: 'Marks & Transcripts', to: '/student/marks', icon: 'chart-line' },
      { label: 'Summative Assessment', to: '/student/summative', icon: 'award', external: true },
      { label: 'Portfolio of Evidence', to: '/student/portfolio', icon: 'folder-open' },
      { label: 'My Assessments', to: '/student/assessments', icon: 'file-alt' },
    ],
  },
  {
    title: 'Records',
    items: [{ label: 'My Documents', to: '/student/documents', icon: 'archive' }],
  },
  {
    title: 'Exams',
    items: [
      { label: 'Exam Booking Form', to: '/student/exam-booking-form', icon: 'file-signature' },
      { label: 'My Exam Bookings', to: '/student/exam-bookings', icon: 'calendar-check' },
    ],
  },
  {
    title: 'Industrial Attachment',
    items: [
      { label: 'Attachment Placement & Letter Review', to: '/student/industrial-attachment', icon: 'industry' },
      { label: 'Digital Logbook', to: '/student/logbook', icon: 'book' },
      { label: 'My Attachment Marks', to: '/student/attachment-marks', icon: 'star-half-alt' },
      { label: 'Mentoring Tool / Logbook', to: '/student/mentoring-tool', icon: 'file-pdf' },
    ],
  },
  {
    title: 'Services',
    items: [
      { label: 'Course Clearance', to: '/clearance/', icon: 'clipboard-check', external: true },
      { label: 'Employment Status', to: '/student/employment-status', icon: 'user-tie' },
    ],
  },
  {
    title: 'Account',
    items: [
      { label: 'My Profile', to: '/auth/profile', icon: 'user-circle', external: true },
      { label: 'Notifications', to: '/notifications', icon: 'bell', external: true },
    ],
  },
]

const portalNav: Partial<Record<UserRole, NavSection[]>> = {
  trainer: trainerNav,
  student: studentNav,
}

export function getPortalNav(role: UserRole): NavSection[] {
  return portalNav[role] || [
    {
      items: [{ label: 'Dashboard', to: getRoleHome(role), icon: 'tachometer-alt' }],
    },
  ]
}

export function getRoleHome(role: UserRole): string {
  const map: Record<string, string> = {
    trainer: '/trainer/dashboard',
    student: '/student/dashboard',
    dept_admin: '/dept-admin/dashboard',
    super_admin: '/super-admin/dashboard',
    examination_officer: '/examination-officer/dashboard',
    industry_mentor: '/industry-mentor/dashboard',
    internal_verifier: '/internal-verifier/dashboard',
    liaison_officer: '/liaison-officer/dashboard',
    cdacc_verifier: '/cdacc-verifier/dashboard',
    workshop_technician: '/workshop-technician/dashboard',
  }
  return map[role] || '/login'
}

export function getPortalTitle(role: UserRole): string {
  const map: Record<string, string> = {
    trainer: 'TTTI Trainer Portal',
    student: 'TTTI Trainee Portal',
    dept_admin: 'Department Admin Portal',
    super_admin: 'Super Admin Portal',
    examination_officer: 'Examination Officer Portal',
  }
  return map[role] || 'TTTI Portal'
}
