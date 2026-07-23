import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { type ReactNode } from 'react'
import {
  Chart as ChartJS,
  ArcElement,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { Doughnut, Line, Bar } from 'react-chartjs-2'
import { motion } from 'framer-motion'
import { fetchTrainerDashboard } from '@/api/trainer'
import { useAuth } from '@/providers/AuthProvider'
import { PortalShell } from '@/layouts/PortalShell'
import { EmptyState, ErrorState, PageSkeleton } from '@/components/ui/States'
import { getApiErrorMessage } from '@/lib/apiClient'

ChartJS.register(
  ArcElement,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend,
  Filler,
)

export default function TrainerDashboardPage() {
  const { user } = useAuth()
  const q = useQuery({
    queryKey: ['trainer', 'dashboard'],
    queryFn: fetchTrainerDashboard,
  })

  if (q.isLoading) {
    return (
      <PortalShell title="Trainer Dashboard">
        <PageSkeleton />
      </PortalShell>
    )
  }

  if (q.isError) {
    return (
      <PortalShell title="Trainer Dashboard">
        <div className="p-6">
          <ErrorState message={getApiErrorMessage(q.error)} onRetry={() => void q.refetch()} />
        </div>
      </PortalShell>
    )
  }

  const data = q.data!
  const stats = data.stats
  const total = stats.total || 0
  const pending = stats.pending || 0
  const approved = stats.approved || 0
  const rejected = stats.rejected || 0
  const pPct = total > 0 ? Math.round((pending / total) * 100) : 0
  const aPct = total > 0 ? Math.round((approved / total) * 100) : 0
  const rPct = total > 0 ? Math.round((rejected / total) * 100) : 0
  const approvalRate = total > 0 ? Math.round((approved / total) * 100) : 0
  const firstName = (user?.full_name || 'Trainer').split(' ')[0]

  return (
    <PortalShell title="Trainer Dashboard">
      <div className="min-h-screen bg-slate-50 p-6">
        <div className="mb-8">
          <h1 className="mb-2 text-3xl font-bold text-slate-900">Welcome back, {firstName}!</h1>
          <p className="text-slate-600">
            {data.current_month} ·{' '}
            {pending ? (
              <span className="font-semibold text-orange-600">
                {pending} assessment{pending === 1 ? '' : 's'} awaiting review
              </span>
            ) : (
              <span className="font-semibold text-green-600">Review queue is clear — great work!</span>
            )}
          </p>
        </div>

        <div className="mb-3.5 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.1em] text-slate-500">
          <i className="fas fa-briefcase" /> Workload Snapshot
          <span className="h-px flex-1 bg-slate-200" />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-5 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCell
              icon="layer-group"
              iconBg="#f3e8ff"
              iconColor="#7c3aed"
              value={total}
              label="Total Assessments"
              hint="All trainee POE submissions"
              barWidth={100}
              bar="linear-gradient(90deg,#8b5cf6,#a78bfa)"
            />
            <KpiCell
              to="/trainer/assessments"
              icon="hourglass-half"
              iconBg="#fff7ed"
              iconColor="#ea580c"
              value={pending}
              valueColor="#c2410c"
              label="Pending Review"
              hint="Awaiting your decision"
              badge={pending ? 'Action' : undefined}
              barWidth={pPct}
              bar="linear-gradient(90deg,#f59e0b,#fb923c)"
            />
            <KpiCell
              icon="check-circle"
              iconBg="#ecfdf5"
              iconColor="#059669"
              value={approved}
              valueColor="#047857"
              label="Approved"
              hint={`${aPct}% of all submissions`}
              barWidth={aPct}
              bar="linear-gradient(90deg,#10b981,#34d399)"
            />
            <KpiCell
              to="/trainer/assessments"
              icon="undo-alt"
              iconBg="#fef2f2"
              iconColor="#dc2626"
              value={rejected}
              valueColor="#b91c1c"
              label="Returned"
              hint="Needs trainee revision"
              barWidth={rPct}
              bar="linear-gradient(90deg,#ef4444,#f87171)"
            />
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-slate-100 bg-slate-50 px-5 py-3 text-xs">
            <span className="text-slate-500">
              {pending
                ? `Focus on the review queue first — ${pending} file${pending === 1 ? '' : 's'} still open.`
                : 'POE review queue is clear. Keep Marks Entry and attendance up to date.'}
            </span>
            <Link to="/trainer/assessments" className="inline-flex items-center gap-1.5 font-bold text-violet-700">
              Open Trainee POE Review <i className="fas fa-arrow-right" />
            </Link>
          </div>
        </motion.div>

        <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-2">
          <ActionTile
            href="/academic-trips"
            icon="bus"
            iconBg="#f0fdfa"
            iconColor="#0f766e"
            value={stats.trips_uploaded || 0}
            label="My Trip Reports"
            hint="Academic trips uploaded by you"
            external
          />
          <ActionTile
            href="/clearance/approver"
            icon="clipboard-check"
            iconBg="#eff6ff"
            iconColor="#2563eb"
            value={stats.clearance_pending || 0}
            label="Clearance Pending"
            hint="Approvals waiting on you"
            external
          />
        </div>

        <div className="mb-3.5 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.1em] text-slate-500">
          <i className="fas fa-chart-bar text-violet-600" /> Performance Analytics
          <span className="h-px flex-1 bg-slate-200" />
        </div>

        <div className="mb-6 grid grid-cols-1 gap-6 md:grid-cols-3">
          <ChartCard title="Assessment Status" sub={`${total} total`} icon="file-alt" iconColor="#9333ea">
            <div className="relative mx-auto h-[170px] max-w-[220px]">
              <Doughnut
                data={{
                  labels: ['Pending', 'Approved', 'Returned'],
                  datasets: [
                    {
                      data: [pending, approved, rejected],
                      backgroundColor: ['#f59e0b', '#10b981', '#ef4444'],
                      borderWidth: 3,
                      borderColor: '#fff',
                    },
                  ],
                }}
                options={{ cutout: '72%', plugins: { legend: { display: false } } }}
              />
              <div className="pointer-events-none absolute inset-0 grid place-items-center">
                <div className="text-center">
                  <strong className="block text-2xl font-extrabold text-slate-900">{total}</strong>
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Total</span>
                </div>
              </div>
            </div>
          </ChartCard>

          <ChartCard title="7-Day Attendance" sub="My units · last 7 days" icon="calendar-check" iconColor="#10b981">
            <Line
              data={{
                labels: data.analytics.trend_labels,
                datasets: [
                  {
                    label: 'Present',
                    data: data.analytics.trend_present,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16,185,129,.10)',
                    fill: true,
                    tension: 0.4,
                  },
                  {
                    label: 'Absent',
                    data: data.analytics.trend_absent,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239,68,68,.07)',
                    fill: true,
                    tension: 0.4,
                  },
                ],
              }}
              options={{
                responsive: true,
                plugins: { legend: { position: 'top', labels: { font: { size: 11 }, usePointStyle: true } } },
                scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
              }}
            />
          </ChartCard>

          <ChartCard title="Attendance by Unit" sub="Presence rate" icon="users" iconColor="#3b82f6">
            {data.analytics.att_unit_labels.length === 0 ? (
              <div className="py-9 text-center text-sm text-slate-400">No attendance data yet</div>
            ) : (
              data.analytics.att_unit_labels.map((label, i) => {
                const tot = (data.analytics.att_unit_present[i] || 0) + (data.analytics.att_unit_absent[i] || 0)
                const pct = tot > 0 ? Math.round(((data.analytics.att_unit_present[i] || 0) / tot) * 100) : 0
                return (
                  <div key={label} className="mb-2.5">
                    <div className="mb-1 flex justify-between text-xs">
                      <span className="max-w-[150px] truncate font-semibold text-slate-700">{label}</span>
                      <span className="font-bold text-slate-500">{pct}%</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })
            )}
          </ChartCard>
        </div>

        <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-2">
          <ChartCard title="Assessments per Unit" sub="Pending · Approved · Returned" icon="layer-group" iconColor="#8b5cf6">
            <Bar
              data={{
                labels: data.analytics.assess_unit_labels,
                datasets: [
                  { label: 'Pending', data: data.analytics.assess_unit_pending, backgroundColor: 'rgba(245,158,11,.80)' },
                  { label: 'Approved', data: data.analytics.assess_unit_approved, backgroundColor: 'rgba(16,185,129,.80)' },
                  { label: 'Returned', data: data.analytics.assess_unit_rejected, backgroundColor: 'rgba(239,68,68,.75)' },
                ],
              }}
              options={{
                responsive: true,
                plugins: { legend: { position: 'top', labels: { font: { size: 11 }, usePointStyle: true } } },
                scales: { y: { beginAtZero: true } },
              }}
            />
          </ChartCard>

          <ChartCard title="Approval Rate" sub="This trainer" icon="chart-pie" iconColor="#f59e0b">
            <div className="py-3 text-center">
              <div className="text-5xl font-black text-slate-900" style={{ fontFamily: 'var(--font-display)' }}>
                {approvalRate}
                <span className="text-2xl text-slate-400">%</span>
              </div>
              <div className="mt-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Approval Rate</div>
              <div className="my-3.5 h-2.5 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400" style={{ width: `${approvalRate}%` }} />
              </div>
              <div className="mt-3 flex border-t border-slate-100">
                {[
                  [pending, 'Pending', '#f59e0b'],
                  [approved, 'Approved', '#10b981'],
                  [rejected, 'Returned', '#ef4444'],
                  [total, 'Total', '#111827'],
                ].map(([v, l, c]) => (
                  <div key={String(l)} className="flex-1 border-r border-slate-100 py-2.5 text-center last:border-0">
                    <strong className="block text-lg font-extrabold" style={{ color: String(c) }}>
                      {v as number}
                    </strong>
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{l as string}</span>
                  </div>
                ))}
              </div>
            </div>
          </ChartCard>
        </div>

        <div className="mb-8 overflow-hidden rounded-xl border border-slate-100 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
            <h2 className="text-lg font-bold text-slate-900">
              <i className="fas fa-clock mr-2 text-orange-600" />
              Pending Assessments
              {data.pending_assessments.length ? (
                <span className="ml-2 rounded-full bg-orange-100 px-2 py-0.5 text-xs font-bold text-orange-700">
                  {data.pending_assessments.length}
                </span>
              ) : null}
            </h2>
            <Link to="/trainer/assessments" className="text-sm font-semibold text-violet-600">
              View All <i className="fas fa-arrow-right ml-1" />
            </Link>
          </div>
          {data.pending_assessments.length === 0 ? (
            <EmptyState title="No pending assessments. Great job!" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50">
                  <tr>
                    {['Student', 'Unit', 'Class', 'Type', 'Uploaded', 'Action'].map((h) => (
                      <th key={h} className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.pending_assessments.map((a) => {
                    const profile = (a.user_profiles || {}) as Record<string, string>
                    const unit = (a.units || {}) as Record<string, string>
                    const cls = (a.classes || {}) as Record<string, string>
                    return (
                      <tr key={String(a.id)} className="hover:bg-slate-50">
                        <td className="px-6 py-4">
                          <p className="text-sm font-medium text-slate-900">{profile.full_name || '—'}</p>
                          <p className="text-xs text-slate-500">{profile.admission_no || ''}</p>
                        </td>
                        <td className="px-6 py-4 text-sm">{unit.name || '—'}</td>
                        <td className="px-6 py-4 text-sm">{cls.name || '—'}</td>
                        <td className="px-6 py-4">
                          <span className="rounded bg-blue-100 px-2 py-1 text-xs font-bold text-blue-700">
                            {String(a.assessment_type || '—')}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-slate-600">
                          {a.uploaded_at ? String(a.uploaded_at).slice(0, 10) : '—'}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <a
                            href={`/trainer/assessment/${a.id}/review`}
                            className="inline-flex items-center gap-1 rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white"
                          >
                            <i className="fas fa-eye" /> Review
                          </a>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {data.units_list.length > 0 ? (
          <div className="overflow-hidden rounded-xl border border-slate-100 bg-white shadow-sm">
            <div className="border-b border-slate-100 px-6 py-4">
              <h2 className="text-lg font-bold text-slate-900">
                <i className="fas fa-book mr-2 text-violet-600" />
                My Assigned Units
                <span className="ml-2 rounded-full bg-violet-100 px-2 py-0.5 text-xs font-bold text-violet-700">
                  {data.units_list.length}
                </span>
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">Code</th>
                    <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">Name</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.units_list.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-50">
                      <td className="px-6 py-4">
                        <span className="rounded bg-violet-100 px-2 py-1 text-xs font-bold text-violet-700">{u.code}</span>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-900">{u.name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </PortalShell>
  )
}

function KpiCell(props: {
  to?: string
  icon: string
  iconBg: string
  iconColor: string
  value: number
  valueColor?: string
  label: string
  hint: string
  badge?: string
  barWidth: number
  bar: string
}) {
  const inner = (
    <>
      <div className="mb-3.5 flex items-center justify-between">
        <div
          className="grid h-10 w-10 place-items-center rounded-xl text-[15px]"
          style={{ background: props.iconBg, color: props.iconColor }}
        >
          <i className={`fas fa-${props.icon}`} />
        </div>
        {props.badge ? (
          <span className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-orange-600">
            {props.badge}
          </span>
        ) : null}
      </div>
      <div className="text-[30px] font-extrabold leading-none tracking-tight" style={{ color: props.valueColor || '#0f172a' }}>
        {props.value}
      </div>
      <div className="mt-2 text-xs font-bold text-slate-700">{props.label}</div>
      <div className="mt-0.5 text-[11px] text-slate-400">{props.hint}</div>
      <div className="mt-3.5 h-1 overflow-hidden rounded-full bg-slate-100">
        <span className="block h-full rounded-full" style={{ width: `${props.barWidth}%`, background: props.bar }} />
      </div>
    </>
  )
  const cls = 'relative block border-b border-slate-100 p-5 sm:border-b-0 sm:[&:not(:last-child)]:border-r sm:[&:not(:last-child)]:border-slate-100'
  if (props.to) return <Link to={props.to} className={`${cls} hover:bg-slate-50`}>{inner}</Link>
  return <div className={cls}>{inner}</div>
}

function ActionTile(props: {
  href: string
  icon: string
  iconBg: string
  iconColor: string
  value: number
  label: string
  hint: string
  external?: boolean
}) {
  const body = (
    <>
      <div className="grid h-12 w-12 place-items-center rounded-[14px] text-lg" style={{ background: props.iconBg, color: props.iconColor }}>
        <i className={`fas fa-${props.icon}`} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[26px] font-extrabold leading-none text-slate-900">{props.value}</div>
        <div className="mt-1 text-[13px] font-bold text-slate-700">{props.label}</div>
        <div className="mt-0.5 text-[11px] text-slate-400">{props.hint}</div>
      </div>
      <div className="grid h-[34px] w-[34px] place-items-center rounded-full border border-slate-200 bg-slate-50 text-slate-500 group-hover:border-violet-600 group-hover:bg-violet-600 group-hover:text-white">
        <i className="fas fa-chevron-right text-xs" />
      </div>
    </>
  )
  const cls =
    'group flex items-center gap-4 rounded-2xl border border-slate-200 bg-white px-5 py-4.5 shadow-sm transition hover:-translate-y-0.5 hover:border-violet-200 hover:shadow-md'
  if (props.external) return <a href={props.href} className={cls}>{body}</a>
  return <Link to={props.href} className={cls}>{body}</Link>
}

function ChartCard({
  title,
  sub,
  icon,
  iconColor,
  children,
}: {
  title: string
  sub: string
  icon: string
  iconColor: string
  children: ReactNode
}) {
  return (
    <div className="overflow-hidden rounded-[14px] border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
        <h3 className="m-0 flex items-center gap-2 text-sm font-bold text-slate-900">
          <i className={`fas fa-${icon}`} style={{ color: iconColor }} /> {title}
        </h3>
        <span className="text-[11.5px] text-slate-400">{sub}</span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}
