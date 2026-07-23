import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'
import * as authApi from '@/api/auth'
import type { AuthUser } from '@/types'
import { getApiErrorMessage } from '@/lib/apiClient'

interface AuthContextValue {
  user: AuthUser | null
  loading: boolean
  error: string | null
  loginStaff: (email: string, password: string) => Promise<AuthUser>
  loginStudent: (admissionNo: string, password: string) => Promise<AuthUser>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const refresh = useCallback(async () => {
    try {
      const me = await authApi.fetchMe()
      setUser(me)
      setError(null)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    const onExpired = () => {
      setUser(null)
      queryClient.clear()
    }
    window.addEventListener('ttti:session-expired', onExpired)
    return () => window.removeEventListener('ttti:session-expired', onExpired)
  }, [queryClient])

  const loginStaff = useCallback(async (email: string, password: string) => {
    try {
      const u = await authApi.loginStaff(email, password)
      setUser(u)
      setError(null)
      return u
    } catch (err) {
      const msg = getApiErrorMessage(err, 'Invalid email or password')
      setError(msg)
      throw new Error(msg)
    }
  }, [])

  const loginStudent = useCallback(async (admissionNo: string, password: string) => {
    try {
      const u = await authApi.loginStudent(admissionNo, password)
      setUser(u)
      setError(null)
      return u
    } catch (err) {
      const msg = getApiErrorMessage(err, 'Invalid admission number or password')
      setError(msg)
      throw new Error(msg)
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      setUser(null)
      queryClient.clear()
    }
  }, [queryClient])

  const value = useMemo(
    () => ({ user, loading, error, loginStaff, loginStudent, logout, refresh }),
    [user, loading, error, loginStaff, loginStudent, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
