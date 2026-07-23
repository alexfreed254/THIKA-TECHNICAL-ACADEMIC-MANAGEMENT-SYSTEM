import { NavLink, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState, type ReactNode } from 'react'
import { useAuth } from '@/providers/AuthProvider'
import { getPortalNav, getPortalTitle } from '@/config/navigation'
import { fetchRecentNotifications } from '@/api/trainer'
import clsx from 'clsx'

const legacyBase = (import.meta.env.VITE_LEGACY_ORIGIN as string | undefined) || ''
const ZOOM_MIN = 0
const ZOOM_MAX = 200
const ZOOM_KEY = 'ttti_zoom'

function readZoomPct() {
  const raw = parseFloat(localStorage.getItem(ZOOM_KEY) || '100')
  if (Number.isNaN(raw)) return 100
  if (raw > 0 && raw <= 3) return Math.round(raw * 100)
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(raw)))
}

function applyPageZoom(pct: number) {
  const level = pct / 100
  const target =
    (document.querySelector('.main-content') as HTMLElement | null) ||
    (document.querySelector('main') as HTMLElement | null) ||
    document.body
  document.body.style.zoom = ''
  target.style.zoom = String(level)
  localStorage.setItem(ZOOM_KEY, String(pct))
}

function resolveHref(to: string, external?: boolean) {
  if (external && legacyBase) return `${legacyBase.replace(/\/$/, '')}${to}`
  if (external) return to
  return to
}

export function PortalShell({
  title,
  children,
}: {
  title?: string
  children: ReactNode
}) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)
  const [zoomPct, setZoomPct] = useState(() =>
    typeof window === 'undefined' ? 100 : readZoomPct(),
  )
  const role = user?.role || 'trainer'
  const nav = getPortalNav(role)

  useEffect(() => {
    applyPageZoom(zoomPct)
  }, [zoomPct])

  const notifs = useQuery({
    queryKey: ['notifications', 'recent'],
    queryFn: () => fetchRecentNotifications(8),
    enabled: Boolean(user),
    refetchInterval: 60_000,
  })

  const unread = notifs.data?.unread_count || 0

  async function onLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-[var(--gray-50)]">
      {/* Official header strip — matches existing institutional chrome */}
      <header
        className="fixed inset-x-0 top-0 z-[60] flex h-[var(--official-header-h)] items-center gap-3 border-b border-slate-200 bg-white px-4 shadow-sm"
        style={{ height: 'var(--official-header-h)' }}
      >
        <img src="/ttti-logo.jpg" alt="Thika Technical" className="h-10 w-10 rounded-full object-contain" />
        <div className="min-w-0">
          <div className="truncate text-sm font-bold text-slate-900" style={{ fontFamily: 'var(--font-display)' }}>
            Thika Technical Training Institute
          </div>
          <div className="truncate text-xs text-slate-500">Academic Management System</div>
        </div>
      </header>

      <aside
        className={clsx(
          'fixed bottom-0 left-0 top-[var(--official-header-h)] z-50 flex w-[var(--sidebar-w)] flex-col text-white transition-transform duration-200',
          'bg-[linear-gradient(180deg,#0a0f1e_0%,#0f1f40_45%,#0d1b35_100%)]',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
      >
        <div className="border-b border-white/10 px-4 py-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-amber-300/90">
            {getPortalTitle(role)}
          </div>
          <div className="mt-1 truncate text-sm font-semibold">{user?.full_name}</div>
        </div>

        <nav className="flex-1 overflow-y-auto px-2.5 py-3" aria-label="Portal menu">
          {nav.map((section, si) => (
            <div key={si} className="mb-2">
              {section.title ? (
                <div className="mb-1 mt-3 flex items-center gap-2 px-2.5 text-[9.5px] font-extrabold uppercase tracking-[1.8px] text-amber-400/85">
                  {section.title}
                  <span className="h-px flex-1 bg-gradient-to-r from-amber-400/35 to-white/5" />
                </div>
              ) : null}
              <div className="flex flex-col gap-0.5">
                {section.items.map((item) => {
                  const href = resolveHref(item.to, item.external)
                  if (item.external) {
                    return (
                      <a
                        key={item.to}
                        href={href}
                        className="flex items-center gap-3 rounded-[10px] px-3.5 py-2.5 text-[13.5px] font-medium text-white/85 hover:bg-amber-400/13 hover:text-white"
                      >
                        <span className="grid h-8 w-8 place-items-center rounded-lg border border-white/10 bg-white/10 text-[13px]">
                          <i className={`fas fa-${item.icon}`} aria-hidden />
                        </span>
                        {item.label}
                      </a>
                    )
                  }
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      onClick={() => setSidebarOpen(false)}
                      className={({ isActive }) =>
                        clsx(
                          'flex items-center gap-3 rounded-[10px] px-3.5 py-2.5 text-[13.5px] font-medium text-white/85',
                          isActive && 'border-l-2 border-amber-400 bg-amber-400/13 text-white',
                        )
                      }
                    >
                      <span className="grid h-8 w-8 place-items-center rounded-lg border border-white/10 bg-white/10 text-[13px]">
                        <i className={`fas fa-${item.icon}`} aria-hidden />
                      </span>
                      {item.label}
                    </NavLink>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="shrink-0 border-t border-white/10 p-3">
          <div
            className="rounded-xl border border-amber-400/45 bg-slate-950/55 px-3 py-2.5 shadow-lg"
            role="group"
            aria-label="Page zoom"
          >
            <div className="mb-2 flex items-center justify-between text-[13px] font-extrabold text-white">
              <span className="inline-flex items-center gap-2">
                <i className="fas fa-search-plus text-amber-400" aria-hidden /> Zoom
              </span>
              <span className="min-w-[52px] rounded-full border border-amber-400/35 bg-amber-400/15 px-2 py-0.5 text-center text-[13px] font-extrabold text-amber-400">
                {zoomPct}%
              </span>
            </div>
            <input
              type="range"
              min={ZOOM_MIN}
              max={ZOOM_MAX}
              step={5}
              value={zoomPct}
              aria-label="Zoom from 0 to 200 percent"
              className="h-2.5 w-full cursor-pointer appearance-none rounded-full border border-white/20 bg-gradient-to-r from-slate-600 to-amber-400"
              onChange={(e) => setZoomPct(Number(e.target.value))}
            />
            <div className="mt-2 flex justify-between text-[10px] font-extrabold uppercase tracking-wide text-white/70">
              <span>0%</span>
              <span>100%</span>
              <span>Max</span>
            </div>
          </div>
        </div>
      </aside>

      {sidebarOpen ? (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          aria-label="Close menu"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}

      <div className="main-content pt-[var(--official-header-h)] lg:pl-[var(--sidebar-w)]">
        <div
          className="sticky top-[var(--official-header-h)] z-30 flex h-[var(--topbar-h)] items-center justify-between border-b-2 border-amber-100 bg-white px-4"
        >
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 text-slate-600 lg:hidden"
              aria-label="Open menu"
              onClick={() => setSidebarOpen(true)}
            >
              <i className="fas fa-bars" />
            </button>
            <h1 className="text-base font-bold text-slate-900">{title || 'Dashboard'}</h1>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <button
                type="button"
                className="relative grid h-9 w-9 place-items-center rounded-lg text-slate-600 hover:bg-slate-50"
                aria-label="Notifications"
                onClick={() => setNotifOpen((v) => !v)}
              >
                <i className="fas fa-bell" />
                {unread > 0 ? (
                  <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
                    {unread > 99 ? '99+' : unread}
                  </span>
                ) : null}
              </button>
              <AnimatePresence>
                {notifOpen ? (
                  <motion.div
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 6 }}
                    className="absolute right-0 top-[calc(100%+10px)] z-50 w-[340px] overflow-hidden rounded-[14px] border border-slate-200 bg-white shadow-xl"
                  >
                    <div className="border-b border-slate-100 px-4 py-3 text-sm font-bold">Notifications</div>
                    <div className="max-h-80 overflow-y-auto">
                      {(notifs.data?.notifications || []).length === 0 ? (
                        <div className="px-4 py-8 text-center text-sm text-slate-400">No notifications</div>
                      ) : (
                        (notifs.data?.notifications || []).map((n) => (
                          <div key={String(n.id)} className="border-b border-slate-50 px-4 py-3">
                            <div className="text-sm font-semibold text-slate-900">{String(n.title || '')}</div>
                            <div className="text-xs text-slate-500">{String(n.message || '')}</div>
                          </div>
                        ))
                      )}
                    </div>
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>

            <button
              type="button"
              onClick={() => void onLogout()}
              className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-3 py-2 text-xs font-bold text-white hover:bg-red-700"
              aria-label="Sign out"
            >
              <i className="fas fa-sign-out-alt" />
              Sign Out
            </button>
          </div>
        </div>

        <main className="min-h-[calc(100vh-var(--official-header-h)-var(--topbar-h))]">{children}</main>
      </div>
    </div>
  )
}
