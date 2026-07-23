import { api } from '@/lib/apiClient'
import type { AuthUser } from '@/types'

export async function loginStaff(email: string, password: string) {
  const { data } = await api.post('/api/v1/auth/login', {
    login_type: 'staff',
    email,
    password,
  })
  return data.data.user as AuthUser
}

export async function loginStudent(admission_no: string, password: string) {
  const { data } = await api.post('/api/v1/auth/login', {
    login_type: 'student',
    admission_no,
    password,
  })
  return data.data.user as AuthUser
}

export async function fetchMe() {
  const { data } = await api.get('/api/v1/auth/me')
  return data.data.user as AuthUser
}

export async function logout() {
  await api.post('/api/v1/auth/logout')
}
