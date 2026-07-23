import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { fetchStudentDashboard } from '@/api/student'
import { PortalShell } from '@/layouts/PortalShell'
import { EmptyState, ErrorState, PageSkeleton } from '@/components/ui/States'
import { getApiErrorMessage } from '@/lib/apiClient'

export default function StudentDashboardPage() {
  const q = useQuery({ queryKey: ['student', 'dashboard'], queryFn: fetchStudentDashboard })

  if (q.isLoading) {
    return (
      <PortalShell title="Dashboard">
        <PageSkeleton />
      </PortalShell>
    )
  }
  if (q.isError) {
    return (
      <PortalShell title="Dashboard">
        <div className="p-6">
          <ErrorState message={getApiErrorMessage(q.error)} onRetry={() => void q.refetch()} />
        </div>
      </PortalShell>
    )
  }

  const data = q.data!
  const stats = data.stats
  const firstName = (data.student.full_name || 'Trainee').split(' ')[0]
  const pct = data.overall_pct || 0
  const barColor = pct >= 75 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444'

  return (
    <PortalShell title="Dashboard">
      <div className="min-h-screen p-6" style={{ background: 'linear-gradient(#f8fafc,#f0f4f8)' }}>
        <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-bold text-slate-900" style={{ fontFamily: 'var(--font-display)' }}>
            Welcome back, {firstName}!
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {data.student.admission_no || '—'} · {data.current_month}
          </p>
        </div>

        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Attendance Rate</div>
            <div className="mt-2 text-3xl font-black" style={{ color: '#2563eb' }}>
              {pct}%
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {data.total_attended}/{stats.attendance_total || 0} lessons
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full" style={{ width: `${Math.min(pct, 100)}%`, background: barColor }} />
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Assessments & POE</div>
            <div className="mt-2 text-3xl font-black text-slate-900">{stats.approved || 0}</div>
            <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] font-bold">
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-800">Ok {stats.approved || 0}</span>
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">Pending {stats.pending || 0}</span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">Total {stats.total || 0}</span>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Industrial Attachment</div>
            <div className="mt-2 text-xl font-black text-slate-900">
              {(stats.attachment_active || 0) > 0 ? 'Active' : 'Inactive'}
            </div>
            <div className="mt-2 text-xs text-slate-500">
              Logbook entries: {stats.logbook_entries || 0} · NYC competencies: {stats.pending_competencies || 0}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Clearance</div>
            <div className="mt-2 text-xl font-black text-slate-900">
              {stats.clearance_status || 'Not started'}
            </div>
            <a href="/clearance/" className="mt-3 inline-block text-sm font-bold" style={{ color: '#2563eb' }}>
              Open clearance →
            </a>
          </div>
        </div>

        <div className="mb-6">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wider text-slate-500">Quick Actions</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {[
              ['My Units', '/student/units', 'book-open'],
              ['Attendance', '/student/attendance', 'clipboard-list'],
              ['Marks', '/student/marks', 'chart-line'],
              ['Portfolio', '/student/portfolio', 'folder-open'],
              ['Assessments', '/student/assessments', 'file-alt'],
              ['Documents', '/student/documents', 'archive'],
              ['Exam Booking', '/student/exam-booking-form', 'file-signature'],
              ['My Bookings', '/student/exam-bookings', 'calendar-check'],
              ['Attachment', '/student/industrial-attachment', 'industry'],
              ['Logbook', '/student/logbook', 'book'],
              ['Clearance', '/clearance/', 'clipboard-check', true],
              ['Employment', '/student/employment-status', 'user-tie'],
            ].map(([label, to, icon, external]) =>
              external ? (
                <a
                  key={String(to)}
                  href={String(to)}
                  className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800 shadow-sm hover:border-blue-300"
                >
                  <i className={`fas fa-${icon} text-[#2563eb]`} />
                  {label}
                </a>
              ) : (
                <Link
                  key={String(to)}
                  to={String(to)}
                  className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800 shadow-sm hover:border-blue-300"
                >
                  <i className={`fas fa-${icon} text-[#2563eb]`} />
                  {label}
                </Link>
              ),
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 px-5 py-4 text-base font-bold text-slate-900">Attendance by Unit</div>
            {data.attendance_data.length === 0 ? (
              <EmptyState title="No attendance records yet" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-slate-50">
                    <tr>
                      {['Unit', 'Present', 'Total', '%'].map((h) => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {data.attendance_data.map((u) => {
                      const upct = u.total_records ? Math.round((u.attended / u.total_records) * 100) : 0
                      return (
                        <tr key={u.id}>
                          <td className="px-4 py-3 text-sm font-medium text-slate-900">
                            {u.unit_code || ''} {u.unit_name || ''}
                          </td>
                          <td className="px-4 py-3 text-sm">{u.attended}</td>
                          <td className="px-4 py-3 text-sm">{u.total_records}</td>
                          <td className="px-4 py-3 text-sm font-bold" style={{ color: upct >= 75 ? '#10b981' : '#f59e0b' }}>
                            {upct}%
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 px-5 py-4 text-base font-bold text-slate-900">Recent Assessments</div>
            {data.recent_assessments.length === 0 ? (
              <EmptyState title="No assessments uploaded yet" />
            ) : (
              <ul className="divide-y divide-slate-100">
                {data.recent_assessments.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-3 px-5 py-3">
                    <div>
                      <div className="text-sm font-semibold text-slate-900">
                        {(a.units || {}).name || 'Unit'} · {a.assessment_type || 'POE'}
                      </div>
                      <div className="text-xs text-slate-500">{a.uploaded_at ? String(a.uploaded_at).slice(0, 10) : '—'}</div>
                    </div>
                    <StatusBadge status={a.status || 'pending'} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </PortalShell>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; color: string; label: string }> = {
    approved: { bg: '#d1fae5', color: '#065f46', label: 'Approved' },
    pending: { bg: '#fef9c3', color: '#854d0e', label: 'Pending' },
    rejected: { bg: '#fee2e2', color: '#991b1b', label: 'Returned' },
  }
  const s = map[status] || map.pending
  return (
    <span className="rounded-full px-2.5 py-1 text-[11px] font-bold" style={{ background: s.bg, color: s.color }}>
      {s.label}
    </span>
  )
}
