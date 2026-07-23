import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import {
  fetchAssessments,
  reviewAssessment,
  type PoeAssessment,
  type PoeClassBucket,
  type PoeUnitBucket,
} from '@/api/trainer'
import { PortalShell } from '@/layouts/PortalShell'
import { EmptyState, ErrorState, PageSkeleton } from '@/components/ui/States'
import { getApiErrorMessage } from '@/lib/apiClient'

type Tab = 'dashboard' | 'browse' | 'search'
type StatusFilter = 'all' | 'pending' | 'approved' | 'rejected'

export default function AssessmentsPage() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['trainer', 'assessments'], queryFn: fetchAssessments })
  const [tab, setTab] = useState<Tab>('dashboard')
  const [browseClass, setBrowseClass] = useState<PoeClassBucket | null>(null)
  const [browseUnit, setBrowseUnit] = useState<PoeUnitBucket | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [fileSearch, setFileSearch] = useState('')
  const [rejectNotes, setRejectNotes] = useState<Record<string, string>>({})
  const [openReject, setOpenReject] = useState<string | null>(null)

  const reviewMut = useMutation({
    mutationFn: ({ id, action, review_note }: { id: string; action: 'approve' | 'reject'; review_note?: string }) =>
      reviewAssessment(id, { action, review_note }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['trainer', 'assessments'] })
      setOpenReject(null)
    },
  })

  const counts = q.data?.status_counts || { total: 0, pending: 0, approved: 0, rejected: 0 }
  const classes = q.data?.classes || []

  const browseFiles = useMemo(() => {
    let files = browseUnit?.assessments || []
    if (statusFilter !== 'all') files = files.filter((f) => (f.status || 'pending') === statusFilter)
    if (fileSearch.trim()) {
      const s = fileSearch.toLowerCase()
      files = files.filter((f) => {
        const p = f.user_profiles || {}
        return (
          (p.full_name || '').toLowerCase().includes(s) ||
          (p.admission_no || '').toLowerCase().includes(s) ||
          String(f.assessment_type || '').toLowerCase().includes(s)
        )
      })
    }
    return files
  }, [browseUnit, statusFilter, fileSearch])

  const searchAll = useMemo(() => {
    const all: PoeAssessment[] = []
    for (const c of classes) for (const u of c.units) all.push(...(u.assessments || []))
    return all
  }, [classes])

  if (q.isLoading) {
    return (
      <PortalShell title="Trainee POE Review">
        <PageSkeleton />
      </PortalShell>
    )
  }
  if (q.isError) {
    return (
      <PortalShell title="Trainee POE Review">
        <div className="p-6">
          <ErrorState message={getApiErrorMessage(q.error)} onRetry={() => void q.refetch()} />
        </div>
      </PortalShell>
    )
  }

  return (
    <PortalShell title="Trainee POE Review">
      <div className="min-h-screen p-6" style={{ background: '#f0f4f8' }}>
        <div className="mb-5 flex flex-wrap gap-2">
          {([
            ['dashboard', 'Dashboard'],
            ['browse', 'Browse'],
            ['search', 'Search'],
          ] as const).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={
                tab === id
                  ? 'rounded-xl bg-[#4f46e5] px-4 py-2.5 text-sm font-bold text-white'
                  : 'rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-600'
              }
            >
              {label}
            </button>
          ))}
        </div>

        {tab === 'dashboard' ? (
          <>
            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Total" value={counts.total} border="#4f46e5" bg="rgba(79,70,229,.06)" />
              <StatCard label="Pending" value={counts.pending} border="#f59e0b" bg="rgba(245,158,11,.08)" />
              <StatCard label="Approved" value={counts.approved} border="#10b981" bg="rgba(16,185,129,.08)" />
              <StatCard label="Returned" value={counts.rejected} border="#f43f5e" bg="rgba(244,63,94,.08)" />
            </div>

            {classes.length === 0 ? (
              <EmptyState title="No POE submissions yet" hint="Trainee uploads will appear here by class and unit." />
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                {classes.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => {
                      setBrowseClass(c)
                      setBrowseUnit(null)
                      setTab('browse')
                    }}
                    className="rounded-2xl border border-slate-200 bg-white/90 p-5 text-left shadow-sm backdrop-blur hover:border-indigo-300"
                  >
                    <div className="mb-2 flex items-center gap-3">
                      <span className="grid h-10 w-10 place-items-center rounded-xl bg-indigo-50 text-indigo-600">
                        <i className="fas fa-folder" />
                      </span>
                      <div>
                        <div className="font-bold text-slate-900">{c.name}</div>
                        <div className="text-xs text-slate-500">
                          {c.unit_count} unit{c.unit_count === 1 ? '' : 's'}
                        </div>
                      </div>
                    </div>
                    {c.pending > 0 ? (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-800">
                        {c.pending} pending
                      </span>
                    ) : (
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-800">
                        Queue clear
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </>
        ) : null}

        {tab === 'browse' ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex flex-wrap items-center gap-2 text-sm text-slate-600">
              <button type="button" className="font-semibold text-indigo-600" onClick={() => { setBrowseClass(null); setBrowseUnit(null) }}>
                Classes
              </button>
              {browseClass ? (
                <>
                  <span>/</span>
                  <button type="button" className="font-semibold text-indigo-600" onClick={() => setBrowseUnit(null)}>
                    {browseClass.name}
                  </button>
                </>
              ) : null}
              {browseUnit ? (
                <>
                  <span>/</span>
                  <span className="font-bold text-slate-800">{browseUnit.name}</span>
                </>
              ) : null}
            </div>

            {!browseClass ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {classes.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setBrowseClass(c)}
                    className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-left hover:border-indigo-300"
                  >
                    <div className="font-bold text-slate-900">{c.name}</div>
                    <div className="text-xs text-slate-500">{c.unit_count} units · {c.pending} pending</div>
                  </button>
                ))}
              </div>
            ) : !browseUnit ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {browseClass.units.map((u) => (
                  <button
                    key={u.id}
                    type="button"
                    onClick={() => setBrowseUnit(u)}
                    className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-left hover:border-indigo-300"
                  >
                    <div className="font-bold text-slate-900">
                      {u.code ? `${u.code} — ` : ''}
                      {u.name}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5 text-[11px] font-bold">
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">{u.pending} pending</span>
                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-800">{u.approved} approved</span>
                      <span className="rounded bg-rose-100 px-1.5 py-0.5 text-rose-800">{u.rejected} returned</span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <>
                <div className="mb-4 flex flex-wrap items-center gap-2">
                  <input
                    value={fileSearch}
                    onChange={(e) => setFileSearch(e.target.value)}
                    placeholder="Search trainee / type…"
                    className="min-w-[200px] flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
                  />
                  {(['all', 'pending', 'approved', 'rejected'] as const).map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setStatusFilter(s)}
                      className={pillClass(s, statusFilter === s)}
                    >
                      {s === 'all' ? 'All' : s === 'rejected' ? 'Returned' : s[0].toUpperCase() + s.slice(1)}
                    </button>
                  ))}
                </div>
                {browseFiles.length === 0 ? (
                  <EmptyState title="No files match this filter." />
                ) : (
                  <div className="space-y-3">
                    {browseFiles.map((f) => (
                      <FileCard
                        key={f.id}
                        file={f}
                        rejectOpen={openReject === f.id}
                        rejectNote={rejectNotes[f.id] || ''}
                        busy={reviewMut.isPending}
                        onRejectNote={(v) => setRejectNotes((m) => ({ ...m, [f.id]: v }))}
                        onToggleReject={() => setOpenReject((cur) => (cur === f.id ? null : f.id))}
                        onApprove={() => reviewMut.mutate({ id: f.id, action: 'approve' })}
                        onReject={() =>
                          reviewMut.mutate({
                            id: f.id,
                            action: 'reject',
                            review_note: rejectNotes[f.id] || '',
                          })
                        }
                      />
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        ) : null}

        {tab === 'search' ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <input
              value={fileSearch}
              onChange={(e) => setFileSearch(e.target.value)}
              placeholder="Search all POE files by trainee name or admission…"
              className="mb-4 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
            />
            <div className="space-y-3">
              {searchAll
                .filter((f) => {
                  if (!fileSearch.trim()) return true
                  const s = fileSearch.toLowerCase()
                  const p = f.user_profiles || {}
                  return (
                    (p.full_name || '').toLowerCase().includes(s) ||
                    (p.admission_no || '').toLowerCase().includes(s)
                  )
                })
                .slice(0, 40)
                .map((f) => (
                  <FileCard
                    key={f.id}
                    file={f}
                    rejectOpen={openReject === f.id}
                    rejectNote={rejectNotes[f.id] || ''}
                    busy={reviewMut.isPending}
                    onRejectNote={(v) => setRejectNotes((m) => ({ ...m, [f.id]: v }))}
                    onToggleReject={() => setOpenReject((cur) => (cur === f.id ? null : f.id))}
                    onApprove={() => reviewMut.mutate({ id: f.id, action: 'approve' })}
                    onReject={() =>
                      reviewMut.mutate({
                        id: f.id,
                        action: 'reject',
                        review_note: rejectNotes[f.id] || '',
                      })
                    }
                  />
                ))}
            </div>
          </div>
        ) : null}
      </div>
    </PortalShell>
  )
}

function StatCard({ label, value, border, bg }: { label: string; value: number; border: string; bg: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white/90 p-5 shadow-sm backdrop-blur" style={{ borderLeft: `4px solid ${border}`, background: bg }}>
      <div className="text-xs font-bold uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-1 text-3xl font-black text-slate-900">{value}</div>
    </div>
  )
}

function pillClass(status: StatusFilter, active: boolean) {
  const base = 'rounded-full border px-3 py-1.5 text-xs font-bold'
  const map: Record<StatusFilter, string> = {
    all: 'bg-[#ede9fe] text-[#4f46e5] border-transparent',
    approved: 'bg-[#d1fae5] text-[#065f46] border-[#6ee7b7]',
    pending: 'bg-[#fef9c3] text-[#854d0e] border-[#fde047]',
    rejected: 'bg-[#fee2e2] text-[#991b1b] border-[#fca5a5]',
  }
  return `${base} ${map[status]} ${active ? 'outline outline-[2.5px] outline-[#4f46e5] outline-offset-2' : ''}`
}

function FileCard({
  file,
  rejectOpen,
  rejectNote,
  busy,
  onRejectNote,
  onToggleReject,
  onApprove,
  onReject,
}: {
  file: PoeAssessment
  rejectOpen: boolean
  rejectNote: string
  busy: boolean
  onRejectNote: (v: string) => void
  onToggleReject: () => void
  onApprove: () => void
  onReject: () => void
}) {
  const status = file.status || 'pending'
  const profile = file.user_profiles || {}
  const marks = file.marks_obtained
  const max = file.max_marks || 100

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-bold text-slate-900">{profile.full_name || 'Trainee'}</div>
          <div className="text-xs text-slate-500">
            {profile.admission_no || '—'} · {String(file.assessment_type || 'POE')}
            {file.uploaded_at ? ` · ${String(file.uploaded_at).slice(0, 10)}` : ''}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {marks != null ? (
            <span className="rounded-lg bg-purple-600 px-2 py-1 text-xs font-bold text-white">
              {marks}/{max}
            </span>
          ) : null}
          <span className={pillClass(status as StatusFilter, false)}>
            {status === 'rejected' ? 'Returned' : status[0].toUpperCase() + status.slice(1)}
          </span>
        </div>
      </div>

      {status === 'pending' ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onApprove}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50"
          >
            Approve
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onToggleReject}
            className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50"
          >
            Return
          </button>
          <a
            href={`/trainer/assessment/${file.id}/review`}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-700"
          >
            Full review
          </a>
        </div>
      ) : null}

      {rejectOpen ? (
        <div className="mt-3 space-y-2">
          <textarea
            value={rejectNote}
            onChange={(e) => onRejectNote(e.target.value)}
            rows={2}
            placeholder="Reason for return…"
            className="w-full rounded-xl border border-rose-200 bg-white px-3 py-2 text-sm"
          />
          <button
            type="button"
            disabled={busy}
            onClick={onReject}
            className="rounded-lg bg-rose-700 px-3 py-1.5 text-xs font-bold text-white"
          >
            Confirm return
          </button>
        </div>
      ) : null}
    </div>
  )
}
