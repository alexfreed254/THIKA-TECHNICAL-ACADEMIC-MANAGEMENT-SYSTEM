import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  title?: string
}

interface State {
  hasError: boolean
  message?: string
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-[40vh] grid place-items-center p-8">
          <div className="max-w-md w-full rounded-2xl border border-red-100 bg-white p-6 shadow-sm text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-600">
              <i className="fas fa-exclamation-triangle" aria-hidden />
            </div>
            <h2 className="text-lg font-bold text-slate-900">{this.props.title || 'Something went wrong'}</h2>
            <p className="mt-2 text-sm text-slate-500">
              Please refresh the page. If the problem continues, contact your administrator.
            </p>
            <button
              type="button"
              className="mt-5 rounded-xl bg-[#1e5a9f] px-4 py-2.5 text-sm font-semibold text-white"
              onClick={() => window.location.reload()}
            >
              Reload page
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
