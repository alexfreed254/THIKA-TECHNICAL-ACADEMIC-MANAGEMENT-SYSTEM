import { useQuery } from '@tanstack/react-query'
import { fetchStudentAttendance } from '@/api/student'
import { PortalShell } from '@/layouts/PortalShell'
import { EmptyState, ErrorState, PageSkeleton } from '@/components/ui/States'
import { getApiErrorMessage } from '@/lib/apiClient'

export default function StudentAttendancePage() {
  const q = useQuery({ queryKey: ['student', 'attendance'], queryFn: fetchStudentAttendance })

  if (q.isLoading) {
    return (
      <PortalShell title="Lesson Attendance">
        <PageSkeleton />
      </PortalShell>
    )
  }
  if (q.isError) {
    return (
      <PortalShell title="Lesson Attendance">
        <div className="p-6">
          <ErrorState message={getApiErrorMessage(q.error)} onRetry={() => void q.refetch()} />
        </div>
      </PortalShell>
    )
  }

  const data = q.data!
  const pct = data.percentage || 0
  const pctClass = pct >= 75 ? '#15803d' : pct >= 50 ? '#b45309' : '#b91c1c'

  return (
    <PortalShell title="Lesson Attendance">
      <div className="mx-auto max-w-[1000px] p-6">
        <div className="mb-7 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat icon="calendar-check" color="#1e5a9f" label="Total Lessons" value={data.total} />
          <Stat icon="user-check" color="#16a34a" label="Present" value={data.present} />
          <Stat icon="user-times" color="#dc2626" label="Absent" value={data.absent} />
          <div className="flex items-center gap-3.5 rounded-[14px] border border-slate-200 bg-white p-5 shadow-sm">
            <div className="grid h-12 w-12 place-items-center rounded-xl text-white" style={{ background: '#0891b2' }}>
              <i className="fas fa-percentage text-xl" />
            </div>
            <div>
              <h3 className="m-0 text-[11px] font-bold uppercase tracking-wider text-slate-400">Attendance %</h3>
              <p className="m-0 text-[26px] font-extrabold leading-none" style={{ color: pctClass }}>
                {pct}%
              </p>
              <div className="mt-1.5 h-1.5 w-[90px] overflow-hidden rounded-full bg-slate-200">
                <div className="h-full rounded-full" style={{ width: `${Math.min(pct, 100)}%`, background: pctClass }} />
              </div>
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-[14px] border border-slate-200 bg-white shadow-sm">
          <div
            className="px-5 py-3.5 text-sm font-bold text-white"
            style={{ background: 'linear-gradient(135deg,#1e5a9f,#2e75b6)' }}
          >
            Attendance Records
          </div>
          {data.attendance.length === 0 ? (
            <EmptyState title="No attendance records yet" hint="Records appear after your trainer marks lessons." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50">
                  <tr>
                    {['Date', 'Unit', 'Week', 'Lesson', 'Status'].map((h) => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase text-slate-500">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.attendance.map((a) => {
                    const unit = (a.units || {}) as { name?: string; code?: string }
                    const present = a.status === 'present'
                    return (
                      <tr key={String(a.id)} className="hover:bg-slate-50">
                        <td className="px-4 py-3 text-sm text-slate-700">
                          {a.attendance_date ? String(a.attendance_date).slice(0, 10) : '—'}
                        </td>
                        <td className="px-4 py-3 text-sm font-medium text-slate-900">
                          {unit.code || ''} {unit.name || ''}
                        </td>
                        <td className="px-4 py-3 text-sm">{a.week != null ? `W${a.week}` : '—'}</td>
                        <td className="px-4 py-3 text-sm">{String(a.lesson || '—')}</td>
                        <td className="px-4 py-3">
                          <span
                            className="rounded-full px-2.5 py-1 text-[11px] font-bold"
                            style={
                              present
                                ? { background: '#dcfce7', color: '#15803d' }
                                : { background: '#fee2e2', color: '#b91c1c' }
                            }
                          >
                            {present ? 'Present' : 'Absent'}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </PortalShell>
  )
}

function Stat({
  icon,
  color,
  label,
  value,
}: {
  icon: string
  color: string
  label: string
  value: number
}) {
  return (
    <div className="flex items-center gap-3.5 rounded-[14px] border border-slate-200 bg-white p-5 shadow-sm">
      <div className="grid h-12 w-12 place-items-center rounded-xl text-white" style={{ background: color }}>
        <i className={`fas fa-${icon} text-xl`} />
      </div>
      <div>
        <h3 className="m-0 text-[11px] font-bold uppercase tracking-wider text-slate-400">{label}</h3>
        <p className="m-0 text-[26px] font-extrabold leading-none text-slate-900">{value}</p>
      </div>
    </div>
  )
}
