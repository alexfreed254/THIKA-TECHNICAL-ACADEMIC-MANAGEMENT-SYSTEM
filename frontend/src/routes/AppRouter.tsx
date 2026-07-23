import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { PageSkeleton } from '@/components/ui/States'
import { RequireAuth, RequireRole } from '@/routes/guards'

const LoginPage = lazy(() => import('@/pages/auth/LoginPage'))
const TrainerDashboardPage = lazy(() => import('@/pages/trainer/DashboardPage'))
const MarksEntryPage = lazy(() => import('@/pages/trainer/MarksEntryPage'))
const AssessmentsPage = lazy(() => import('@/pages/trainer/AssessmentsPage'))
const AttendancePage = lazy(() => import('@/pages/trainer/AttendancePage'))
const StudentDashboardPage = lazy(() => import('@/pages/student/DashboardPage'))
const FeaturePlaceholder = lazy(() => import('@/pages/shared/FeaturePlaceholder'))

function Lazy({ children }: { children: ReactNode }) {
  return <Suspense fallback={<PageSkeleton />}>{children}</Suspense>
}

function Placeholder({ title, path }: { title: string; path: string }) {
  return (
    <Lazy>
      <FeaturePlaceholder title={title} legacyPath={path} />
    </Lazy>
  )
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Routes>
          <Route
            path="/login"
            element={
              <Lazy>
                <LoginPage />
              </Lazy>
            }
          />

          <Route element={<RequireAuth />}>
            <Route element={<RequireRole roles={['trainer']} />}>
              <Route
                path="/trainer/dashboard"
                element={
                  <Lazy>
                    <TrainerDashboardPage />
                  </Lazy>
                }
              />
              <Route
                path="/trainer/attendance"
                element={
                  <Lazy>
                    <AttendancePage />
                  </Lazy>
                }
              />
              <Route
                path="/trainer/assessments"
                element={
                  <Lazy>
                    <AssessmentsPage />
                  </Lazy>
                }
              />
              <Route
                path="/trainer/marks-entry"
                element={
                  <Lazy>
                    <MarksEntryPage />
                  </Lazy>
                }
              />
              <Route path="/trainer/attendance-history" element={<Placeholder title="Attendance History" path="/trainer/attendance-history" />} />
              <Route path="/trainer/marks-import" element={<Placeholder title="Import Marks" path="/trainer/marks-import" />} />
              <Route path="/trainer/portfolio" element={<Placeholder title="My Portfolio" path="/trainer/portfolio" />} />
              <Route path="/trainer" element={<Navigate to="/trainer/dashboard" replace />} />
            </Route>

            <Route element={<RequireRole roles={['student']} />}>
              <Route
                path="/student/dashboard"
                element={
                  <Lazy>
                    <StudentDashboardPage />
                  </Lazy>
                }
              />
              <Route path="/student/units" element={<Placeholder title="My Units" path="/student/units" />} />
              <Route path="/student/attendance" element={<Placeholder title="Lesson Attendance" path="/student/attendance" />} />
              <Route path="/student/marks" element={<Placeholder title="Marks & Transcripts" path="/student/marks" />} />
              <Route path="/student/portfolio" element={<Placeholder title="Portfolio of Evidence" path="/student/portfolio" />} />
              <Route path="/student/assessments" element={<Placeholder title="My Assessments" path="/student/assessments" />} />
              <Route path="/student/documents" element={<Placeholder title="My Documents" path="/student/documents" />} />
              <Route path="/student/exam-booking-form" element={<Placeholder title="Exam Booking Form" path="/student/exam-booking-form" />} />
              <Route path="/student/exam-bookings" element={<Placeholder title="My Exam Bookings" path="/student/exam-bookings" />} />
              <Route path="/student/industrial-attachment" element={<Placeholder title="Industrial Attachment" path="/student/industrial-attachment" />} />
              <Route path="/student/logbook" element={<Placeholder title="Digital Logbook" path="/student/logbook" />} />
              <Route path="/student/attachment-marks" element={<Placeholder title="Attachment Marks" path="/student/attachment-marks" />} />
              <Route path="/student/mentoring-tool" element={<Placeholder title="Mentoring Tool" path="/student/mentoring-tool" />} />
              <Route path="/student/employment-status" element={<Placeholder title="Employment Status" path="/student/employment-status" />} />
              <Route path="/student" element={<Navigate to="/student/dashboard" replace />} />
            </Route>
          </Route>

          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
