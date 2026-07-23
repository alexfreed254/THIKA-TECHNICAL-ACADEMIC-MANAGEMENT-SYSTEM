import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { fetchStudentMarks } from '@/api/student'
import { PortalShell } from '@/layouts/PortalShell'
import { EmptyState, ErrorState, PageSkeleton } from '@/components/ui/States'
import { getApiErrorMessage } from '@/lib/apiClient'

const YEARS = Array.from({ length: 8 }, (_, i) => new Date().getFullYear() - 2 + i)

export default function StudentMarksPage() {
  const [params, setParams] = useSearchParams()
  const year = params.get('year') || String(new Date().getFullYear())
  const term = params.get('term') || ''

  const q = useQuery({
    queryKey: ['student', 'marks', year, term],
    queryFn: () => fetchStudentMarks({ year, term: term || undefined }),
  })

  if (q.isLoading) {
    return (
      <PortalShell title="Marks & Transcript">
        <PageSkeleton />
      </PortalShell>
    )
  }
  if (q.isError) {
    return (
      <PortalShell title="Marks & Transcript">
        <div className="p-6">
          <ErrorState message={getApiErrorMessage(q.error)} onRetry={() => void q.refetch()} />
        </div>
      </PortalShell>
    )
  }

  const data = q.data!

  return (
    <PortalShell title="Marks & Transcript">
      <div className="mx-auto max-w-[1060px] p-6">
        <div
          className="mb-6 flex flex-wrap items-center gap-5 rounded-2xl px-[30px] py-[26px] text-white"
          style={{ background: 'linear-gradient(135deg,#0f2c54,#1a3d6e)' }}
        >
          <img src="/ttti-logo.jpg" alt="" className="h-[60px] w-[60px] rounded-full bg-white object-contain p-1" />
          <div className="min-w-0 flex-1">
            <div className="text-[17px] font-extrabold uppercase tracking-wide" style={{ fontFamily: 'var(--font-display)' }}>
              Marks & Transcript
            </div>
            <div className="mt-0.5 text-xs text-white/75">Formative assessment results</div>
            <div className="mt-2.5 flex flex-wrap gap-4 text-[12.5px]">
              <span><i className="fas fa-user mr-1 opacity-70" />{data.profile.full_name || '—'}</span>
              <span><i className="fas fa-id-card mr-1 opacity-70" />{data.profile.admission_no || '—'}</span>
              <span><i className="fas fa-chalkboard mr-1 opacity-70" />{data.class_name || '—'}</span>
              <span><i className="fas fa-building mr-1 opacity-70" />{data.dept_name || '—'}</span>
            </div>
          </div>
        </div>

        <div className="mb-5 flex flex-wrap items-end gap-3.5 rounded-[13px] border border-slate-200 bg-white px-[22px] py-4 shadow-sm">
          <label className="text-sm">
            <span className="mb-1 block text-[11px] font-bold uppercase text-slate-500">Year</span>
            <select
              value={year}
              onChange={(e) => {
                const n = new URLSearchParams(params)
                n.set('year', e.target.value)
                setParams(n)
              }}
              className="rounded-lg border-[1.5px] border-slate-200 px-3 py-2 text-[13px]"
            >
              {YEARS.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-[11px] font-bold uppercase text-slate-500">Term</span>
            <select
              value={term}
              onChange={(e) => {
                const n = new URLSearchParams(params)
                if (e.target.value) n.set('term', e.target.value)
                else n.delete('term')
                setParams(n)
              }}
              className="rounded-lg border-[1.5px] border-slate-200 px-3 py-2 text-[13px]"
            >
              <option value="">All terms</option>
              <option value="1">Term 1</option>
              <option value="2">Term 2</option>
              <option value="3">Term 3</option>
            </select>
          </label>
          <a
            href={`/student/marks/download-result-slip?year=${year}${term ? `&term=${term}` : ''}`}
            className="ml-auto inline-flex items-center gap-1.5 rounded-[9px] px-5 py-2.5 text-[13px] font-bold text-white"
            style={{ background: 'linear-gradient(135deg,#16a34a,#15803d)' }}
          >
            <i className="fas fa-file-pdf" /> Result slip
          </a>
        </div>

        <div className="mb-6 grid grid-cols-2 gap-3.5 md:grid-cols-4">
          <MiniStat val={`${data.overall}%`} lbl="Overall" color="#1e5a9f" />
          <MiniStat val={String(data.scored_units)} lbl="Units scored" color="#0f172a" />
          <MiniStat val={String(data.passed)} lbl="Passed (M/P/C)" color="#15803d" />
          <MiniStat val={year} lbl="Academic year" color="#64748b" />
        </div>

        {data.units_data.length === 0 ? (
          <EmptyState title="No formative marks for this filter" hint="Marks appear after your trainer enters them." />
        ) : (
          data.units_data.map((u, idx) => (
            <div key={idx} className="mb-5 overflow-hidden rounded-[14px] border border-slate-200 bg-white shadow-sm">
              <div
                className="flex flex-wrap items-center gap-3 px-[22px] py-3.5"
                style={{ background: 'linear-gradient(135deg,#0f2c54,#1a3d6e)' }}
              >
                <span className="rounded-md bg-white/18 px-2.5 py-0.5 text-xs font-bold text-white">
                  {u.unit?.code || '—'}
                </span>
                <span className="flex-1 text-[15px] font-bold text-white">{u.unit?.name || 'Unit'}</span>
                <span className="rounded-md bg-white/12 px-2 py-0.5 text-[11.5px] text-white/75">
                  {u.has_marks ? `${u.pct}% · ${u.final_grade}` : 'Pending'}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-slate-50">
                    <tr>
                      {['Assessment', 'Type', 'Score', 'Max', '%', 'Grade'].map((h) => (
                        <th key={h} className="px-4 py-2.5 text-left text-[11px] font-bold uppercase text-slate-500">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {u.assessments.map((a, i) => (
                      <tr key={i}>
                        <td className="px-4 py-2.5 text-sm font-medium text-slate-900">{a.assessment_name}</td>
                        <td className="px-4 py-2.5 text-xs font-bold text-slate-500">{a.assessment_type}</td>
                        <td className="px-4 py-2.5 text-sm">{a.marks_obtained ?? '—'}</td>
                        <td className="px-4 py-2.5 text-sm">{a.max_marks}</td>
                        <td className="px-4 py-2.5 text-sm">{a.pct != null ? `${a.pct}%` : '—'}</td>
                        <td className="px-4 py-2.5 text-sm font-bold">{a.grade || 'Pending'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))
        )}
      </div>
    </PortalShell>
  )
}

function MiniStat({ val, lbl, color }: { val: string; lbl: string; color: string }) {
  return (
    <div className="rounded-[13px] border border-slate-200 bg-white px-5 py-[18px] text-center shadow-sm">
      <div className="text-[28px] font-extrabold leading-tight" style={{ color }}>{val}</div>
      <div className="mt-1 text-[11.5px] font-semibold uppercase tracking-wider text-slate-500">{lbl}</div>
    </div>
  )
}
