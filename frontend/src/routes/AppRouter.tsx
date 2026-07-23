import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { PageSkeleton } from '@/components/ui/States'
import { RequireAuth, RequireRole } from '@/routes/guards'

const LoginPage = lazy(() => import('@/pages/auth/LoginPage'))
const TrainerDashboardPage = lazy(() => import('@/pages/trainer/DashboardPage'))
const FeaturePlaceholder = lazy(() => import('@/pages/shared/FeaturePlaceholder'))

function Lazy({ children }: { children: ReactNode }) {
  return <Suspense fallback={<PageSkeleton />}>{children}</Suspense>
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
                    <FeaturePlaceholder title="Mark Attendance" legacyPath="/trainer/attendance" />
                  </Lazy>
                }
              />
              <Route
                path="/trainer/attendance-history"
                element={
                  <Lazy>
                    <FeaturePlaceholder title="Attendance History" legacyPath="/trainer/attendance-history" />
                  </Lazy>
                }
              />
              <Route
                path="/trainer/assessments"
                element={
                  <Lazy>
                    <FeaturePlaceholder title="Trainee POE Review" legacyPath="/trainer/assessments" />
                  </Lazy>
                }
              />
              <Route
                path="/trainer/marks-entry"
                element={
                  <Lazy>
                    <FeaturePlaceholder title="Marks Entry" legacyPath="/trainer/marks-entry" />
                  </Lazy>
                }
              />
              <Route
                path="/trainer/marks-import"
                element={
                  <Lazy>
                    <FeaturePlaceholder title="Import Marks" legacyPath="/trainer/marks-import" />
                  </Lazy>
                }
              />
              <Route
                path="/trainer/portfolio"
                element={
                  <Lazy>
                    <FeaturePlaceholder title="My Portfolio" legacyPath="/trainer/portfolio" />
                  </Lazy>
                }
              />
              <Route path="/trainer" element={<Navigate to="/trainer/dashboard" replace />} />
            </Route>

            <Route
              path="/student/dashboard"
              element={
                <Lazy>
                  <FeaturePlaceholder title="Trainee Dashboard" legacyPath="/student/dashboard" />
                </Lazy>
              }
            />
          </Route>

          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
