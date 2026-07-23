export function PageSkeleton() {
  return (
    <div className="animate-pulse space-y-4 p-6" aria-busy="true" aria-label="Loading">
      <div className="h-8 w-64 rounded-lg bg-slate-200" />
      <div className="h-4 w-96 max-w-full rounded bg-slate-200" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-28 rounded-2xl bg-slate-200" />
        ))}
      </div>
      <div className="h-64 rounded-2xl bg-slate-200" />
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-white px-6 py-12 text-center">
      <i className="fas fa-inbox mb-3 block text-4xl text-slate-300" aria-hidden />
      <p className="font-semibold text-slate-700">{title}</p>
      {hint ? <p className="mt-1 text-sm text-slate-500">{hint}</p> : null}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-red-100 bg-red-50 px-6 py-8 text-center">
      <i className="fas fa-exclamation-circle mb-2 text-2xl text-red-500" aria-hidden />
      <p className="text-sm font-medium text-red-800">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-lg bg-red-600 px-3 py-2 text-xs font-bold text-white"
        >
          Retry
        </button>
      ) : null}
    </div>
  )
}
