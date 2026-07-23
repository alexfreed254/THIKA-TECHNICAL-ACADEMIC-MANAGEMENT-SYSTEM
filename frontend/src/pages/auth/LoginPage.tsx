import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuth } from '@/providers/AuthProvider'
import { getRoleHome } from '@/config/navigation'

export default function LoginPage() {
  const { user, loading, loginStaff, loginStudent } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState<'staff' | 'student'>('staff')
  const [email, setEmail] = useState('')
  const [admission, setAdmission] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!loading && user) {
    return <Navigate to={getRoleHome(user.role)} replace />
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const u =
        tab === 'staff'
          ? await loginStaff(email.trim(), password)
          : await loginStudent(admission.trim(), password)
      navigate(getRoleHome(u.role), { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-[linear-gradient(135deg,#0f172a_0%,#1e3a8a_45%,#2563eb_100%)] p-6 text-slate-900">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="grid w-full max-w-[1160px] overflow-hidden rounded-[28px] border border-white/12 bg-white/5 shadow-[0_40px_90px_rgba(15,23,42,0.35)] md:grid-cols-2 md:min-h-[640px]"
      >
        <section className="flex flex-col justify-center gap-7 bg-[linear-gradient(180deg,#0f172a_0%,#1e3a8a_100%)] px-8 py-14 text-slate-50 md:px-12">
          <div className="mx-auto grid h-[92px] w-[92px] place-items-center rounded-full bg-white shadow-xl">
            <img src="/ttti-logo.jpg" alt="TTTI logo" className="h-[70px] w-[70px] object-contain" />
          </div>
          <h1 className="text-center text-[clamp(1.8rem,2.8vw,2.6rem)] font-bold uppercase leading-tight tracking-[0.04em]">
            Thika Technical Training Institute
          </h1>
          <p className="mx-auto max-w-[520px] text-center text-base leading-8 text-slate-50/82">
            Academic Management System — secure access for trainers, trainees, HODs, and examination offices.
          </p>
          <div className="grid grid-cols-3 gap-4">
            {[
              ['12+', 'Portals'],
              ['TVET', 'Focused'],
              ['Live', 'Records'],
            ].map(([k, v]) => (
              <div
                key={v}
                className="rounded-[18px] border border-white/14 bg-white/10 px-4 py-5 text-center backdrop-blur"
              >
                <strong className="mb-2 block text-[1.9rem] font-extrabold">{k}</strong>
                <small className="text-[0.8rem] uppercase tracking-[0.12em] text-slate-50/72">{v}</small>
              </div>
            ))}
          </div>
        </section>

        <section className="flex flex-col justify-center gap-7 bg-white px-8 py-12 md:px-12">
          <div className="grid grid-cols-2 gap-2">
            {(['staff', 'student'] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={
                  tab === t
                    ? 'rounded-full border border-blue-300 bg-blue-50 px-3 py-3 text-[0.82rem] font-bold text-blue-700'
                    : 'rounded-full border border-blue-100 bg-slate-50 px-3 py-3 text-[0.82rem] font-bold text-slate-600'
                }
              >
                {t === 'staff' ? 'Staff Login' : 'Trainee Login'}
              </button>
            ))}
          </div>

          <div>
            <h2 className="text-[clamp(1.8rem,2.4vw,2.5rem)] font-bold leading-none">Welcome back</h2>
            <p className="mt-3 text-slate-500 leading-8">
              {tab === 'staff'
                ? 'Sign in with your institutional email and password.'
                : 'Sign in with your admission number and password.'}
            </p>
          </div>

          <form className="grid gap-[18px]" onSubmit={onSubmit}>
            {tab === 'staff' ? (
              <label className="grid gap-2.5 text-[0.95rem]">
                <span className="font-bold text-slate-900">Email</span>
                <span className="relative block">
                  <i className="fas fa-envelope absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden />
                  <input
                    type="email"
                    required
                    autoComplete="username"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full rounded-2xl border border-slate-200 py-4 pl-[46px] pr-[18px] outline-none focus:border-blue-400"
                    placeholder="name@thikatti.ac.ke"
                  />
                </span>
              </label>
            ) : (
              <label className="grid gap-2.5 text-[0.95rem]">
                <span className="font-bold text-slate-900">Admission number</span>
                <span className="relative block">
                  <i className="fas fa-id-card absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden />
                  <input
                    type="text"
                    required
                    autoComplete="username"
                    value={admission}
                    onChange={(e) => setAdmission(e.target.value)}
                    className="w-full rounded-2xl border border-slate-200 py-4 pl-[46px] pr-[18px] outline-none focus:border-blue-400"
                    placeholder="e.g. TT/2024/001"
                  />
                </span>
              </label>
            )}

            <label className="grid gap-2.5 text-[0.95rem]">
              <span className="font-bold text-slate-900">Password</span>
              <span className="relative block">
                <i className="fas fa-lock absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" aria-hidden />
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-2xl border border-slate-200 py-4 pl-[46px] pr-[18px] outline-none focus:border-blue-400"
                  placeholder="Enter password"
                />
              </span>
            </label>

            {error ? (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700" role="alert">
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={busy}
              className="rounded-2xl bg-[#1e5a9f] px-5 py-4 text-base font-bold text-white disabled:opacity-60"
            >
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </section>
      </motion.div>
    </div>
  )
}
