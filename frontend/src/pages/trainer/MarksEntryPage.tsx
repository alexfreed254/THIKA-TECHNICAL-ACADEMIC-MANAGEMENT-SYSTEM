import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  addAssessment,
  fetchMarksEntry,
  saveMark,
} from '@/api/trainer'
import { PortalShell } from '@/layouts/PortalShell'
import { ErrorState, PageSkeleton } from '@/components/ui/States'
import { getApiErrorMessage } from '@/lib/apiClient'

const YEARS = Array.from({ length: 12 }, (_, i) => 2024 + i)

type ToastItem = { id: number; msg: string; err?: boolean }

export default function MarksEntryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const classId = searchParams.get('class_id') || ''
  const unitId = searchParams.get('unit_id') || ''
  const year = Number(searchParams.get('year') || new Date().getFullYear())
  const term = Number(searchParams.get('term') || 1)

  const [modalOpen, setModalOpen] = useState(false)
  const [selType, setSelType] = useState('')
  const [asmName, setAsmName] = useState('')
  const [asmMax, setAsmMax] = useState(100)
  const [modalErr, setModalErr] = useState('')
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const [inputState, setInputState] = useState<Record<string, 'saved' | 'error' | 'saving' | ''>>({})
  const [localMarks, setLocalMarks] = useState<Record<string, string>>({})

  const q = useQuery({
    queryKey: ['trainer', 'marks-entry', classId, unitId, year, term],
    queryFn: () =>
      fetchMarksEntry({
        class_id: classId || undefined,
        unit_id: unitId || undefined,
        year,
        term,
      }),
  })

  useEffect(() => {
    if (!q.data) return
    const next: Record<string, string> = {}
    for (const [sid, amap] of Object.entries(q.data.marks_map || {})) {
      for (const [aid, val] of Object.entries(amap || {})) {
        if (val != null) next[`${sid}:${aid}`] = String(val)
      }
    }
    setLocalMarks(next)
  }, [q.data])

  function toast(msg: string, err = false) {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, msg, err }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 2800)
  }

  function updateParams(patch: Record<string, string>) {
    const next = new URLSearchParams(searchParams)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    if (patch.class_id !== undefined && patch.class_id !== classId) {
      next.delete('unit_id')
    }
    setSearchParams(next)
  }

  const saveMut = useMutation({
    mutationFn: saveMark,
  })

  const addMut = useMutation({
    mutationFn: addAssessment,
    onSuccess: async () => {
      setModalOpen(false)
      setSelType('')
      setAsmName('')
      setAsmMax(100)
      setModalErr('')
      toast('Assessment added')
      await queryClient.invalidateQueries({ queryKey: ['trainer', 'marks-entry'] })
    },
    onError: (err) => {
      setModalErr(getApiErrorMessage(err, 'Could not add assessment.'))
    },
  })

  const oral = q.data?.oral_list || []
  const practical = q.data?.practical_list || []
  const theory = q.data?.theory_list || []
  const ordered = useMemo(() => [...oral, ...practical, ...theory], [oral, practical, theory])
  const students = q.data?.students_list || []
  const units = q.data?.units_list || []
  const classes = q.data?.class_list || []
  const ready = Boolean(classId && unitId)

  const onBlurSave = useCallback(
    async (aid: string, sid: string, max: number, raw: string) => {
      const key = `${sid}:${aid}`
      const val = raw.trim()
      if (val !== '' && (Number.isNaN(Number(val)) || Number(val) < 0 || Number(val) > max)) {
        setInputState((s) => ({ ...s, [key]: 'error' }))
        toast(`Marks must be 0–${max}`, true)
        return
      }
      setInputState((s) => ({ ...s, [key]: 'saving' }))
      try {
        const resp = await saveMut.mutateAsync({ assessment_id: aid, student_id: sid, marks: val })
        if (resp.success || resp.ok) {
          setInputState((s) => ({ ...s, [key]: 'saved' }))
          setTimeout(() => setInputState((s) => ({ ...s, [key]: '' })), 2000)
        } else {
          setInputState((s) => ({ ...s, [key]: 'error' }))
          toast(resp.error || 'Save failed', true)
        }
      } catch (err) {
        setInputState((s) => ({ ...s, [key]: 'error' }))
        toast(getApiErrorMessage(err, 'Network error'), true)
      }
    },
    [saveMut],
  )

  function rowStats(sid: string) {
    let total = 0
    let maxTotal = 0
    let count = 0
    for (const a of ordered) {
      const v = parseFloat(localMarks[`${sid}:${a.id}`] ?? '')
      const mx = Number(a.max_marks) || 100
      if (!Number.isNaN(v)) {
        total += v
        maxTotal += mx
        count += 1
      }
    }
    /* Convert raw scores against their max to a single % out of 100 */
    const avg = count && maxTotal > 0 ? (total / maxTotal) * 100 : 0
    return { total, count, avg }
  }

  function chipClass(t: string) {
    if (t === 'Oral') return 'oral'
    if (t === 'Practical') return 'practical'
    return 'theory'
  }

  function chipIcon(t: string) {
    if (t === 'Oral') return 'microphone'
    if (t === 'Practical') return 'flask'
    return 'book'
  }

  const pdfHref = `/trainer/marks-entry/marks-pdf?class_id=${encodeURIComponent(classId)}&unit_id=${encodeURIComponent(unitId)}&year=${year}&term=${term}`
  const xlsHref = `/trainer/marks-entry/export-excel?class_id=${encodeURIComponent(classId)}&unit_id=${encodeURIComponent(unitId)}&year=${year}&term=${term}`

  if (q.isLoading) {
    return (
      <PortalShell title="Formative Assessment Marks">
        <PageSkeleton />
      </PortalShell>
    )
  }

  if (q.isError) {
    return (
      <PortalShell title="Formative Assessment Marks">
        <div className="p-6">
          <ErrorState message={getApiErrorMessage(q.error)} onRetry={() => void q.refetch()} />
        </div>
      </PortalShell>
    )
  }

  return (
    <PortalShell title="Formative Assessment Marks">
      <style>{marksCss}</style>
      <div className="me-wrap">
        <div className="me-filters">
          <h3>
            <i className="fas fa-filter" /> Select Class, Unit &amp; Period
          </h3>
          <div className="filter-grid">
            <div className="form-group">
              <label>Class</label>
              <select
                className="form-control"
                value={classId}
                onChange={(e) => updateParams({ class_id: e.target.value })}
              >
                <option value="">-- Choose Class --</option>
                {classes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Unit</label>
              <select
                className="form-control"
                value={unitId}
                onChange={(e) => updateParams({ unit_id: e.target.value })}
                disabled={!classId}
              >
                <option value="">-- Choose Unit --</option>
                {units.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.code} – {u.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Year</label>
              <select
                className="form-control"
                value={year}
                onChange={(e) => updateParams({ year: e.target.value })}
              >
                {YEARS.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>Term</label>
              <select
                className="form-control"
                value={term}
                onChange={(e) => updateParams({ term: e.target.value })}
              >
                <option value="1">Term 1 (Jan–Apr)</option>
                <option value="2">Term 2 (May–Aug)</option>
                <option value="3">Term 3 (Sep–Dec)</option>
              </select>
            </div>
          </div>
          <p className="me-hint">
            Select class, unit and term, then add Oral / Practical / Theory assessments. Marks save
            automatically on blur. Download official PDF or Excel from the marks grid — not a webpage
            printout.
          </p>
        </div>

        {ready ? (
          <>
            <div className="assessment-bar">
              <h4>
                <i className="fas fa-list-check" /> Assessments for this unit / term
              </h4>
              <div className="chip-group">
                {ordered.map((a) => (
                  <span key={a.id} className={`chip ${chipClass(a.assessment_type)}`} title={`Max: ${a.max_marks}`}>
                    <i className={`fas fa-${chipIcon(a.assessment_type)}`} style={{ fontSize: 10 }} />{' '}
                    {a.assessment_name}
                  </span>
                ))}
                {ordered.length === 0 ? (
                  <span style={{ color: '#aaa', fontSize: 13 }}>
                    No assessments yet — add one to start entering marks.
                  </span>
                ) : null}
                <button type="button" className="btn-add-assess" onClick={() => setModalOpen(true)}>
                  <i className="fas fa-plus" /> Add Assessment
                </button>
              </div>
            </div>

            <div className="marks-card">
              <div className="marks-card-header">
                <h3>
                  <i className="fas fa-table" style={{ marginRight: 7 }} />
                  Marks Grid
                  {students.length ? (
                    <span
                      style={{
                        background: '#e3f2fd',
                        color: '#1e5a9f',
                        padding: '3px 12px',
                        borderRadius: 20,
                        fontSize: 12,
                        marginLeft: 8,
                      }}
                    >
                      {students.length} student(s)
                    </span>
                  ) : null}
                </h3>
                {ordered.length > 0 && students.length > 0 ? (
                  <div className="action-btns">
                    <a href={pdfHref} className="btn-dl-pdf">
                      <i className="fas fa-file-pdf" /> Download PDF
                    </a>
                    <a href={xlsHref} className="btn-dl-xls">
                      <i className="fas fa-file-excel" /> Download Excel
                    </a>
                  </div>
                ) : null}
              </div>

              {students.length === 0 ? (
                <div className="empty-prompt">
                  <i className="fas fa-users" />
                  No students enrolled in this class.
                </div>
              ) : ordered.length === 0 ? (
                <div className="empty-prompt">
                  <i className="fas fa-plus-circle" />
                  No assessments created yet.
                  <br />
                  <small style={{ fontSize: 13 }}>
                    Click <strong>+ Add Assessment</strong> above to create Oral, Practical or Theory
                    assessments.
                  </small>
                </div>
              ) : (
                <>
                  <div className="grid-wrap">
                    <table className="grid-table">
                      <thead>
                        <tr>
                          <th colSpan={2} className="th-fixed col-name" style={{ textAlign: 'left', paddingLeft: 14 }}>
                            Student
                          </th>
                          {oral.length ? (
                            <th colSpan={oral.length} className="th-oral">
                              <i className="fas fa-microphone" style={{ fontSize: 10 }} /> Oral
                            </th>
                          ) : null}
                          {practical.length ? (
                            <th colSpan={practical.length} className="th-practical">
                              <i className="fas fa-flask" style={{ fontSize: 10 }} /> Practical
                            </th>
                          ) : null}
                          {theory.length ? (
                            <th colSpan={theory.length} className="th-theory">
                              <i className="fas fa-book" style={{ fontSize: 10 }} /> Theory / Written
                            </th>
                          ) : null}
                          <th colSpan={2} className="th-summary">
                            Summary
                          </th>
                        </tr>
                        <tr>
                          <th className="th-fixed" style={{ width: 40 }}>
                            #
                          </th>
                          <th className="th-fixed col-name">Adm No &nbsp;•&nbsp; Name</th>
                          {ordered.map((a) => (
                            <th
                              key={a.id}
                              className={
                                a.assessment_type === 'Oral'
                                  ? 'th-oral'
                                  : a.assessment_type === 'Practical'
                                    ? 'th-practical'
                                    : 'th-theory'
                              }
                              title={`Max: ${a.max_marks}`}
                            >
                              {a.assessment_name}
                              <br />
                              <span style={{ fontSize: 10, fontWeight: 400 }}>/{Math.trunc(a.max_marks)}</span>
                            </th>
                          ))}
                          <th className="th-summary">Total</th>
                          <th className="th-summary">Avg %</th>
                        </tr>
                      </thead>
                      <tbody>
                        {students.map((s, idx) => {
                          const p = s.user_profiles || {}
                          const { total, count, avg } = rowStats(s.student_id)
                          return (
                            <tr key={s.student_id}>
                              <td style={{ color: '#aaa', fontSize: 12 }}>{idx + 1}</td>
                              <td className="col-name">
                                <strong style={{ fontSize: 12, color: '#555' }}>{p.admission_no || '—'}</strong>
                                <br />
                                <span style={{ fontSize: 13 }}>{p.full_name || '—'}</span>
                              </td>
                              {ordered.map((a) => {
                                const key = `${s.student_id}:${a.id}`
                                const st = inputState[key] || ''
                                return (
                                  <td key={a.id}>
                                    <input
                                      type="number"
                                      className={`mark-inp ${st}`}
                                      min={0}
                                      max={a.max_marks}
                                      step={0.5}
                                      placeholder="—"
                                      value={localMarks[key] ?? ''}
                                      onChange={(e) =>
                                        setLocalMarks((m) => ({ ...m, [key]: e.target.value }))
                                      }
                                      onBlur={(e) =>
                                        void onBlurSave(a.id, s.student_id, Number(a.max_marks) || 100, e.target.value)
                                      }
                                    />
                                  </td>
                                )
                              })}
                              <td className="td-total">{count ? total.toFixed(1) : '—'}</td>
                              <td>
                                {count ? (
                                  <span
                                    className={
                                      avg >= 75 ? 'avg-high' : avg >= 50 ? 'avg-med' : 'avg-low'
                                    }
                                  >
                                    {avg.toFixed(1)}%
                                  </span>
                                ) : (
                                  '—'
                                )}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                  <div
                    style={{
                      padding: '10px 18px',
                      background: '#fafafa',
                      borderTop: '1px solid #eee',
                      fontSize: 12,
                      color: '#888',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 8,
                    }}
                  >
                    <i className="fas fa-info-circle" style={{ marginTop: 2 }} />
                    <span>
                      Marks save automatically when you click away from a cell (auto-save). Green border
                      = saved. Red = error. <strong>Avg %</strong> converts scores to out of 100% using
                      the assessment maximum (total obtained ÷ total maximum × 100).
                    </span>
                  </div>
                </>
              )}
            </div>
          </>
        ) : (
          <div className="marks-card">
            <div className="empty-prompt">
              <i className="fas fa-edit" />
              Select a Class and Unit above to load the marks entry grid.
            </div>
          </div>
        )}
      </div>

      {modalOpen ? (
        <div className="modal-overlay open" onClick={(e) => e.target === e.currentTarget && setModalOpen(false)}>
          <div className="modal-box">
            <h3>
              <i className="fas fa-plus-circle" /> Add New Assessment
            </h3>
            <label>Assessment Type</label>
            <div className="btn-type">
              {(['Oral', 'Practical', 'Theory'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`${t === 'Theory' ? 'theory' : t.toLowerCase()} ${selType === t ? 'selected' : ''}`}
                  onClick={() => setSelType(t)}
                >
                  {t === 'Theory' ? 'Theory / Written' : t}
                </button>
              ))}
            </div>
            <label>Assessment Name</label>
            <input
              type="text"
              value={asmName}
              placeholder="e.g. Oral 1, Practical 3, Written Assessment 2"
              onChange={(e) => setAsmName(e.target.value)}
            />
            <label>Maximum Marks (1–100, default 100)</label>
            <input
              type="number"
              value={asmMax}
              min={1}
              max={100}
              step={1}
              onChange={(e) => {
                const n = Number(e.target.value)
                if (Number.isNaN(n)) {
                  setAsmMax(100)
                  return
                }
                setAsmMax(Math.min(100, Math.max(1, n)))
              }}
            />
            <p style={{ fontSize: 12, color: '#64748b', margin: '-6px 0 14px', lineHeight: 1.4 }}>
              Entered scores are converted to <strong>out of 100%</strong> (score ÷ maximum × 100).
              Example:{' '}
              <strong>
                {Math.min(asmMax, Math.round(asmMax * 0.8 * 2) / 2 || asmMax)} / {asmMax || 100}
              </strong>{' '}
              ={' '}
              <strong>
                {(
                  ((Math.min(asmMax, Math.round(asmMax * 0.8 * 2) / 2 || asmMax) / (asmMax || 100)) *
                    100) ||
                  0
                ).toFixed(1)}
                %
              </strong>
              .
            </p>
            {modalErr ? (
              <div style={{ color: '#c62828', fontSize: 12, marginBottom: 8 }}>{modalErr}</div>
            ) : null}
            <div className="modal-footer">
              <button
                type="button"
                className="btn"
                style={{ background: '#eee', color: '#333', border: 'none', padding: '8px 14px', borderRadius: 8 }}
                onClick={() => setModalOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-add-assess"
                style={{ borderRadius: 8, padding: '8px 14px' }}
                disabled={addMut.isPending}
                onClick={() => {
                  if (!selType) {
                    setModalErr('Select an assessment type.')
                    return
                  }
                  if (!asmName.trim()) {
                    setModalErr('Assessment name is required.')
                    return
                  }
                  if (!asmMax || asmMax < 1 || asmMax > 100) {
                    setModalErr('Maximum marks must be between 1 and 100.')
                    return
                  }
                  addMut.mutate({
                    unit_id: unitId,
                    class_id: classId,
                    assessment_type: selType,
                    assessment_name: asmName.trim(),
                    max_marks: asmMax,
                    year,
                    term,
                  })
                }}
              >
                <i className="fas fa-plus" /> Add
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="mark-toast">
        {toasts.map((t) => (
          <div key={t.id} className={`toast-item show${t.err ? ' err' : ''}`}>
            {t.msg}
          </div>
        ))}
      </div>
    </PortalShell>
  )
}

const marksCss = `
.me-wrap { padding:20px; max-width:1400px; margin:0 auto; }
.me-filters { background:#fff; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,.07); padding:20px; margin-bottom:18px; }
.me-filters h3 { color:#1e5a9f; font-size:14px; margin-bottom:14px; padding-bottom:10px; border-bottom:1px solid #eee; }
.filter-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; align-items:end; }
.me-filters .form-group label { display:block; font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; margin-bottom:5px; }
.me-filters .form-control { width:100%; padding:9px 12px; border:1px solid #d1d5db; border-radius:8px; font-size:13px; }
.me-filters .form-control:focus { outline:none; border-color:#1e5a9f; box-shadow:0 0 0 3px rgba(30,90,159,.12); }
.me-hint { margin:12px 0 0; font-size:12px; color:#64748b; line-height:1.45; }
.assessment-bar { background:#fff; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,.07); padding:16px 20px; margin-bottom:18px; }
.assessment-bar h4 { font-size:13px; color:#555; margin-bottom:10px; }
.chip-group { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.chip { display:inline-flex; align-items:center; gap:6px; padding:5px 12px; border-radius:20px; font-size:12px; font-weight:700; }
.chip.oral { background:#e8f5e9; color:#1b5e20; }
.chip.practical { background:#fff3e0; color:#e65100; }
.chip.theory { background:#ede7f6; color:#4527a0; }
.btn-add-assess { display:inline-flex; align-items:center; gap:5px; padding:5px 14px; border-radius:20px; background:#1e5a9f; color:#fff; font-size:12px; font-weight:700; border:none; cursor:pointer; }
.btn-add-assess:hover { background:#154070; }
.marks-card { background:#fff; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,.07); overflow:hidden; }
.marks-card-header { padding:14px 20px; background:#fff; border-bottom:1px solid #e8eef6; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; }
.marks-card-header h3 { font-size:15px; font-weight:700; color:#1e5a9f; }
.action-btns { display:flex; gap:8px; flex-wrap:wrap; }
.btn-dl-pdf { background:#b91c1c; color:#fff; border:none; padding:8px 14px; border-radius:8px; font-size:12px; font-weight:700; text-decoration:none; display:inline-flex; align-items:center; gap:6px; }
.btn-dl-xls { background:#15803d; color:#fff; border:none; padding:8px 14px; border-radius:8px; font-size:12px; font-weight:700; text-decoration:none; display:inline-flex; align-items:center; gap:6px; }
.grid-wrap { overflow-x:auto; }
.grid-table { width:100%; border-collapse:collapse; min-width:500px; font-size:13px; }
.grid-table th { padding:10px 8px; font-size:11px; font-weight:700; text-align:center; border-bottom:2px solid #e0e0e0; white-space:nowrap; }
.grid-table th.col-name { text-align:left; padding-left:14px; }
.grid-table td { padding:7px 8px; border-bottom:1px solid #f0f0f0; text-align:center; vertical-align:middle; }
.grid-table td.col-name { text-align:left; padding-left:14px; }
.grid-table tbody tr:hover { background:#f5f8ff; }
.th-oral { background:#e8f5e9; color:#1b5e20; }
.th-practical { background:#fff3e0; color:#e65100; }
.th-theory { background:#ede7f6; color:#4527a0; }
.th-summary { background:#e3f2fd; color:#1e5a9f; }
.th-fixed { background:#f5f5f5; color:#555; }
.mark-inp { width:68px; padding:5px 6px; border:1px solid #ddd; border-radius:6px; font-size:13px; text-align:center; }
.mark-inp:focus { outline:none; border-color:#1e5a9f; background:#f0f7ff; }
.mark-inp.saved { border-color:#27ae60; background:#f0fff4; }
.mark-inp.error { border-color:#e74c3c; background:#fff5f5; }
.mark-inp.saving { opacity:0.6; }
.td-total { font-weight:700; color:#1e5a9f; }
.avg-high { color:#2e7d32; font-weight:700; } .avg-med { color:#f57c00; font-weight:700; } .avg-low { color:#c62828; font-weight:700; }
.empty-prompt { text-align:center; padding:48px 20px; color:#bbb; }
.empty-prompt i { font-size:40px; display:block; margin-bottom:14px; opacity:0.3; }
.mark-toast { position:fixed; bottom:24px; right:24px; z-index:9999; display:flex; flex-direction:column; gap:8px; pointer-events:none; }
.toast-item { background:#1e5a9f; color:#fff; padding:10px 18px; border-radius:8px; font-size:13px; font-weight:600; box-shadow:0 4px 16px rgba(0,0,0,.2); }
.toast-item.err { background:#c62828; }
.modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.45); z-index:1000; align-items:center; justify-content:center; }
.modal-overlay.open { display:flex; }
.modal-box { background:#fff; border-radius:12px; padding:28px; width:100%; max-width:440px; box-shadow:0 8px 32px rgba(0,0,0,.2); }
.modal-box h3 { font-size:16px; margin-bottom:18px; color:#1e5a9f; }
.modal-box label { font-size:13px; font-weight:600; display:block; margin-bottom:5px; color:#444; }
.modal-box input { width:100%; padding:9px 12px; border:1px solid #ccc; border-radius:6px; font-size:14px; margin-bottom:14px; }
.modal-footer { display:flex; gap:10px; justify-content:flex-end; margin-top:4px; }
.btn-type { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }
.btn-type button { flex:1; padding:9px; border:2px solid #ddd; border-radius:8px; background:#fff; cursor:pointer; font-size:13px; font-weight:600; }
.btn-type button.selected.oral { border-color:#27ae60; background:#e8f5e9; color:#1b5e20; }
.btn-type button.selected.practical { border-color:#f57c00; background:#fff3e0; color:#e65100; }
.btn-type button.selected.theory { border-color:#7b1fa2; background:#ede7f6; color:#4527a0; }
`
