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
  const oral = data.oral_labels || []
  const practical = data.practical_labels || []
  const written = data.written_labels || []

  return (
    <PortalShell title="Marks & Transcript">
      <div className="mx-auto max-w-[1200px] p-6">
        <div
          className="mb-6 flex flex-wrap items-center gap-5 rounded-2xl px-[30px] py-[26px] text-white"
          style={{ background: 'linear-gradient(135deg,#0f2c54,#1a3d6e)' }}
        >
          <img src="/ttti-logo.jpg" alt="" className="h-[60px] w-[60px] rounded-full bg-white object-contain p-1" />
          <div className="min-w-0 flex-1">
            <div className="text-[17px] font-extrabold uppercase tracking-wide" style={{ fontFamily: 'var(--font-display)' }}>
              Marks & Transcript
            </div>
            <div className="mt-0.5 text-xs text-white/75">Same layout as the downloadable Academic Result Transcript</div>
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
            <i className="fas fa-file-pdf" /> Download Transcript
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
          <div className="mb-6 overflow-hidden rounded-[14px] border border-slate-200 bg-white shadow-sm">
            <div
              className="flex flex-wrap items-center gap-2.5 px-[22px] py-3"
              style={{ background: 'linear-gradient(135deg,#0f2c54,#1a3d6e)' }}
            >
              <span className="text-sm font-bold text-white">
                <i className="fas fa-table mr-2" />
                Assessment Marks — {data.units_data.length} Unit(s)
              </span>
              <span className="ml-auto text-[11px] text-white/70">
                Marks shown as obtained/max · same as transcript PDF
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-[12.5px]">
                <thead>
                  <tr className="text-white">
                    <th rowSpan={2} className="bg-[#0f2c54] px-3 py-2.5 text-left text-[11px] font-bold uppercase">#</th>
                    <th rowSpan={2} className="bg-[#0f2c54] px-3 py-2.5 text-left text-[11px] font-bold uppercase">Unit</th>
                    <th rowSpan={2} className="bg-[#0f2c54] px-3 py-2.5 text-center text-[11px] font-bold uppercase">Term</th>
                    {oral.length > 0 && (
                      <th colSpan={oral.length} className="bg-[#1e5a9f] px-2 py-2 text-center text-[11px] font-bold uppercase">
                        Oral Assessments
                      </th>
                    )}
                    {practical.length > 0 && (
                      <th colSpan={practical.length} className="bg-[#c2410c] px-2 py-2 text-center text-[11px] font-bold uppercase">
                        Practical Assessments
                      </th>
                    )}
                    {written.length > 0 && (
                      <th colSpan={written.length} className="bg-[#5b21b6] px-2 py-2 text-center text-[11px] font-bold uppercase">
                        Written Assessments
                      </th>
                    )}
                    <th rowSpan={2} className="bg-[#0f2c54] px-3 py-2.5 text-center text-[11px] font-bold uppercase">Total</th>
                    <th rowSpan={2} className="bg-[#0f2c54] px-3 py-2.5 text-center text-[11px] font-bold uppercase">Score %</th>
                    <th rowSpan={2} className="bg-[#0f2c54] px-3 py-2.5 text-center text-[11px] font-bold uppercase">Grade</th>
                  </tr>
                  <tr className="text-white">
                    {oral.map((n) => (
                      <th key={`o-${n}`} className="bg-[#1e5a9f] px-2 py-2 text-center text-[10px] font-semibold normal-case tracking-normal">
                        {n}
                      </th>
                    ))}
                    {practical.map((n) => (
                      <th key={`p-${n}`} className="bg-[#c2410c] px-2 py-2 text-center text-[10px] font-semibold normal-case tracking-normal">
                        {n}
                      </th>
                    ))}
                    {written.map((n) => (
                      <th key={`w-${n}`} className="bg-[#5b21b6] px-2 py-2 text-center text-[10px] font-semibold normal-case tracking-normal">
                        {n}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.units_data.map((u, idx) => {
                    const bar =
                      u.pct >= 85 ? '#16a34a' : u.pct >= 70 ? '#2563eb' : u.pct >= 50 ? '#d97706' : '#dc2626'
                    return (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="px-3 py-2.5 text-center text-[11px] font-bold text-slate-400">{idx + 1}</td>
                        <td className="px-3 py-2.5">
                          <span className="mr-1.5 inline-flex rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-700">
                            {u.unit?.code || '—'}
                          </span>
                          <span className="font-bold text-slate-800">{u.unit?.name || '—'}</span>
                        </td>
                        <td className="px-3 py-2.5 text-center text-[11.5px] font-semibold text-slate-500">
                          {term ? `T${term}` : u.term ? `T${u.term}` : '—'}
                        </td>
                        {(u.oral_cells || []).map((cell, i) => (
                          <td key={`o${i}`} className="px-2 py-2.5 text-center">
                            <MarkChip cell={cell} tone="oral" />
                          </td>
                        ))}
                        {(u.practical_cells || []).map((cell, i) => (
                          <td key={`p${i}`} className="px-2 py-2.5 text-center">
                            <MarkChip cell={cell} tone="practical" />
                          </td>
                        ))}
                        {(u.written_cells || []).map((cell, i) => (
                          <td key={`w${i}`} className="px-2 py-2.5 text-center">
                            <MarkChip cell={cell} tone="written" />
                          </td>
                        ))}
                        <td className="px-3 py-2.5 text-center text-[12.5px] font-bold text-slate-900">
                          {u.has_marks ? (
                            <>
                              {u.total_obt}
                              <span className="text-[11px] font-normal text-slate-400">/{u.total_max}</span>
                            </>
                          ) : (
                            <span className="text-[11px] text-slate-400">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-center">
                          {u.has_marks ? (
                            <div className="inline-flex flex-col items-center gap-1">
                              <span className="text-[12.5px] font-bold" style={{ color: bar }}>{u.pct}%</span>
                              <div className="h-1 w-[52px] overflow-hidden rounded-full bg-slate-200">
                                <div className="h-full rounded-full" style={{ width: `${u.pct}%`, background: bar }} />
                              </div>
                            </div>
                          ) : (
                            <span className="text-[11px] italic text-slate-400">Pending</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-center">
                          {u.has_marks ? <GradeBadge grade={u.final_grade} /> : <span className="text-[11px] text-slate-400">—</span>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center gap-3.5 border-t border-slate-100 bg-slate-50 px-[22px] py-2.5 text-[11.5px] text-slate-500">
              <span className="font-bold text-slate-700">Legend:</span>
              <span><MarkChip cell="18/20" tone="oral" /> Oral</span>
              <span><MarkChip cell="42/50" tone="practical" /> Practical</span>
              <span><MarkChip cell="35/40" tone="written" /> Written / Theory</span>
              <span className="ml-auto">M 80–100% · P 65–79% · C 50–64% · NYC 0–49%</span>
            </div>
          </div>
        )}
      </div>
    </PortalShell>
  )
}

function MarkChip({ cell, tone }: { cell: string; tone: 'oral' | 'practical' | 'written' }) {
  if (!cell || cell === '—') {
    return <span className="inline-flex min-w-8 items-center justify-center rounded px-1.5 py-0.5 text-[10.5px] italic text-slate-400 bg-slate-100">—</span>
  }
  const styles = {
    oral: 'bg-blue-50 text-blue-800',
    practical: 'bg-orange-50 text-orange-700',
    written: 'bg-violet-50 text-violet-800',
  }[tone]
  return (
    <span className={`inline-flex min-w-8 items-center justify-center rounded px-1.5 py-0.5 text-[11.5px] font-bold ${styles}`}>
      {cell}
    </span>
  )
}

function GradeBadge({ grade }: { grade: string }) {
  const cls =
    grade === 'M' ? 'bg-green-100 text-green-700'
      : grade === 'P' ? 'bg-blue-100 text-blue-700'
        : grade === 'C' ? 'bg-amber-100 text-amber-800'
          : 'bg-red-100 text-red-700'
  return (
    <span className={`inline-flex min-w-10 items-center justify-center rounded-md px-2.5 py-0.5 text-[11.5px] font-extrabold ${cls}`}>
      {grade}
    </span>
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
