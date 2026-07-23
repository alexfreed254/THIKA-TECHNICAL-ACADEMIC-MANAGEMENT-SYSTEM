import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchAttendance, submitAttendance } from '@/api/trainer'
import { PortalShell } from '@/layouts/PortalShell'
import { EmptyState, ErrorState, PageSkeleton } from '@/components/ui/States'
import { getApiErrorMessage } from '@/lib/apiClient'

const YEARS = Array.from({ length: 12 }, (_, i) => 2024 + i)
const WEEKS = Array.from({ length: 15 }, (_, i) => i + 1)

export default function AttendancePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const qc = useQueryClient()
  const classId = searchParams.get('class_id') || ''
  const unitId = searchParams.get('unit_id') || ''
  const week = Number(searchParams.get('week') || 0)
  const lesson = searchParams.get('lesson') || ''
  const year = Number(searchParams.get('year') || new Date().getFullYear())
  const term = Number(searchParams.get('term') || 1)

  const q = useQuery({
    queryKey: ['trainer', 'attendance', classId, unitId, week, lesson, year, term],
    queryFn: () =>
      fetchAttendance({
        class_id: classId || undefined,
        unit_id: unitId || undefined,
        week: week || undefined,
        lesson: lesson || undefined,
        year,
        term,
      }),
  })

  const [statuses, setStatuses] = useState<Record<string, 'present' | 'absent'>>({})
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!q.data?.students_list) return
    const init: Record<string, 'present' | 'absent'> = {}
    for (const s of q.data.students_list) init[s.student_id] = 'absent'
    setStatuses(init)
  }, [q.data?.students_list, classId, unitId, week, lesson])

  const submitMut = useMutation({
    mutationFn: submitAttendance,
    onSuccess: () => {
      setMsg('Attendance submitted successfully.')
      setErr(null)
      void qc.invalidateQueries({ queryKey: ['trainer', 'attendance'] })
    },
    onError: (e) => {
      setErr(getApiErrorMessage(e))
      setMsg(null)
    },
  })

  function updateParams(patch: Record<string, string>) {
    const next = new URLSearchParams(searchParams)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    if (patch.class_id !== undefined && patch.class_id !== classId) {
      next.delete('unit_id')
      next.delete('lesson')
    }
    setSearchParams(next)
  }

  const unitCode = useMemo(() => {
    const u = q.data?.units_list.find((x) => x.id === unitId)
    return u?.code || ''
  }, [q.data, unitId])

  const canMark = Boolean(classId && unitId && week && lesson)
  const lessons = q.data?.lessons || [
    { id: 'L1', label: '08:00–10:00' },
    { id: 'L2', label: '10:15–12:15' },
    { id: 'L3', label: '12:45–02:45' },
    { id: 'L4', label: '03:00–05:00' },
  ]

  if (q.isLoading) {
    return (
      <PortalShell title="Mark Attendance">
        <PageSkeleton />
      </PortalShell>
    )
  }

  if (q.isError) {
    return (
      <PortalShell title="Mark Attendance">
        <div className="p-6">
          <ErrorState message={getApiErrorMessage(q.error)} onRetry={() => void q.refetch()} />
        </div>
      </PortalShell>
    )
  }

  const data = q.data!

  return (
    <PortalShell title="Mark Attendance">
      <div className="p-6">
        <div className="mb-5 rounded-[10px] border border-slate-200 bg-white p-5 shadow-[0_2px_8px_rgba(0,0,0,.07)]">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Select
              label="Class"
              value={classId}
              onChange={(v) => updateParams({ class_id: v })}
              options={[{ value: '', label: 'Select class' }, ...data.class_list.map((c) => ({ value: c.id, label: c.name }))]}
            />
            <Select
              label="Unit"
              value={unitId}
              onChange={(v) => updateParams({ unit_id: v })}
              options={[
                { value: '', label: 'Select unit' },
                ...data.units_list.map((u) => ({ value: u.id, label: `${u.code || ''} ${u.name || ''}`.trim() })),
              ]}
            />
            <Select
              label="Week"
              value={week ? String(week) : ''}
              onChange={(v) => updateParams({ week: v })}
              options={[{ value: '', label: 'Select week' }, ...WEEKS.map((w) => ({ value: String(w), label: `Week ${w}` }))]}
            />
            <Select
              label="Year"
              value={String(year)}
              onChange={(v) => updateParams({ year: v })}
              options={YEARS.map((y) => ({ value: String(y), label: String(y) }))}
            />
            <Select
              label="Term"
              value={String(term)}
              onChange={(v) => updateParams({ term: v })}
              options={[1, 2, 3].map((t) => ({ value: String(t), label: `Term ${t}` }))}
            />
          </div>

          <div className="mt-4">
            <div className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">Lesson time</div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {lessons.map((l) => {
                const selected = lesson === l.id
                return (
                  <button
                    key={l.id}
                    type="button"
                    onClick={() => updateParams({ lesson: l.id })}
                    className="rounded-xl border-2 px-3 py-4 text-left transition"
                    style={
                      selected
                        ? { borderColor: '#1e5a9f', background: '#eff6ff' }
                        : { borderColor: '#e2e8f0', background: '#fff' }
                    }
                  >
                    <div className="text-sm font-extrabold text-slate-900">{l.id}</div>
                    <div className="text-xs text-slate-500">{l.label}</div>
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {data.active_event ? (
          <div
            className="mb-4 rounded-xl px-4 py-3 text-sm font-medium"
            style={
              data.active_event.event_type === 'holiday'
                ? { background: '#fff8e1', color: '#f57f17' }
                : { background: '#e8f5e9', color: '#2e7d32' }
            }
          >
            Session marked as <strong>{data.active_event.event_type === 'holiday' ? 'Holiday' : 'Academic Trip'}</strong>
            {data.active_event.note ? ` — ${data.active_event.note}` : ''}
          </div>
        ) : null}

        {data.attendance_submitted ? (
          <div className="mb-4 rounded-xl px-4 py-3 text-sm font-medium" style={{ background: '#dbeafe', color: '#2563eb' }}>
            Attendance already submitted for this session.{' '}
            <a className="font-bold underline" href={`/trainer/view-session?class_id=${classId}&unit_id=${unitId}&week=${week}&lesson=${lesson}&year=${year}&term=${term}`}>
              View session
            </a>
          </div>
        ) : null}

        {msg ? <div className="mb-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">{msg}</div> : null}
        {err ? <div className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm font-medium text-red-800">{err}</div> : null}

        {!canMark ? (
          <EmptyState title="Select class, unit, week and lesson" hint="Then mark each trainee present or absent." />
        ) : data.students_list.length === 0 ? (
          <EmptyState title="No trainees enrolled in this class" />
        ) : (
          <div className="overflow-hidden rounded-[10px] border border-slate-200 bg-white shadow-[0_2px_8px_rgba(0,0,0,.07)]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
              <h2 className="text-base font-bold text-slate-900">
                Trainees <span className="text-slate-400">({data.students_list.length})</span>
              </h2>
              {!data.attendance_submitted ? (
                <button
                  type="button"
                  disabled={submitMut.isPending}
                  onClick={() =>
                    submitMut.mutate({
                      class_id: classId,
                      unit_id: unitId,
                      unit_code: unitCode,
                      week,
                      lesson,
                      year,
                      term,
                      statuses,
                    })
                  }
                  className="rounded-lg bg-[#1e5a9f] px-4 py-2 text-sm font-bold text-white hover:bg-[#154070] disabled:opacity-60"
                >
                  {submitMut.isPending ? 'Submitting…' : 'Submit Attendance'}
                </button>
              ) : null}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr style={{ background: '#2c5f8a' }}>
                    {['#', 'Admission', 'Name', 'Status'].map((h) => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-white">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.students_list.map((s, idx) => {
                    const p = s.user_profiles || {}
                    const st = statuses[s.student_id] || 'absent'
                    return (
                      <tr key={s.student_id} className="hover:bg-slate-50">
                        <td className="px-4 py-3 text-sm text-slate-500">{idx + 1}</td>
                        <td className="px-4 py-3 text-sm font-medium text-slate-800">{p.admission_no || '—'}</td>
                        <td className="px-4 py-3 text-sm font-semibold text-slate-900">{p.full_name || '—'}</td>
                        <td className="px-4 py-3">
                          <div className="flex gap-2">
                            <Toggle
                              label="Present"
                              active={st === 'present'}
                              color="#16a34a"
                              bg="#dcfce7"
                              disabled={data.attendance_submitted}
                              onClick={() => setStatuses((m) => ({ ...m, [s.student_id]: 'present' }))}
                            />
                            <Toggle
                              label="Absent"
                              active={st === 'absent'}
                              color="#dc2626"
                              bg="#fee2e2"
                              disabled={data.attendance_submitted}
                              onClick={() => setStatuses((m) => ({ ...m, [s.student_id]: 'absent' }))}
                            />
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </PortalShell>
  )
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: Array<{ value: string; label: string }>
}) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-bold text-slate-700">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none focus:border-[#1e5a9f]"
      >
        {options.map((o) => (
          <option key={o.value || o.label} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function Toggle({
  label,
  active,
  color,
  bg,
  disabled,
  onClick,
}: {
  label: string
  active: boolean
  color: string
  bg: string
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="rounded-lg border px-3 py-1.5 text-xs font-bold disabled:opacity-50"
      style={
        active
          ? { borderColor: color, background: bg, color }
          : { borderColor: '#e2e8f0', background: '#fff', color: '#64748b' }
      }
    >
      {label}
    </button>
  )
}
