import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { fetchStudentUnits } from '@/api/student'
import { PortalShell } from '@/layouts/PortalShell'
import { EmptyState, ErrorState, PageSkeleton } from '@/components/ui/States'
import { getApiErrorMessage } from '@/lib/apiClient'

export default function StudentUnitsPage() {
  const q = useQuery({ queryKey: ['student', 'units'], queryFn: fetchStudentUnits })

  if (q.isLoading) {
    return (
      <PortalShell title="My Units">
        <PageSkeleton />
      </PortalShell>
    )
  }
  if (q.isError) {
    return (
      <PortalShell title="My Units">
        <div className="p-6">
          <ErrorState message={getApiErrorMessage(q.error)} onRetry={() => void q.refetch()} />
        </div>
      </PortalShell>
    )
  }

  const units = q.data?.units || []

  return (
    <PortalShell title="My Units">
      <div className="p-6">
        <div className="mb-5">
          <h1 className="text-2xl font-bold text-slate-900">My Units</h1>
          <p className="text-sm text-slate-500">Units linked to your enrolled class, with attendance rates.</p>
        </div>

        {units.length === 0 ? (
          <EmptyState title="No units found" hint="Ask your department admin to enrol you in a class." />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {units.map((u) => {
              const color = u.pct >= 75 ? '#15803d' : u.pct >= 50 ? '#b45309' : '#b91c1c'
              return (
                <div key={u.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="mb-3 flex items-start justify-between gap-2">
                    <span className="rounded-lg bg-[#dbeafe] px-2.5 py-1 text-xs font-bold text-[#1e5a9f]">
                      {u.code || '—'}
                    </span>
                    <span className="text-lg font-extrabold" style={{ color }}>
                      {u.pct}%
                    </span>
                  </div>
                  <div className="text-base font-bold text-slate-900">{u.name}</div>
                  <div className="mt-1 text-xs text-slate-500">{u.class_name || '—'}</div>
                  <div className="mt-3 text-xs text-slate-600">
                    Present {u.attended}/{u.total} lessons
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full" style={{ width: `${Math.min(u.pct, 100)}%`, background: color }} />
                  </div>
                  <Link
                    to="/student/attendance"
                    className="mt-4 inline-flex text-xs font-bold text-[#1e5a9f]"
                  >
                    View attendance →
                  </Link>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </PortalShell>
  )
}
