import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, getToken, loadPersisted, onUnauthorized, setToken } from './api'
import type { User } from './types'

interface AuthCtx {
  user: User | null
  ready: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const Ctx = createContext<AuthCtx>({ user: null, ready: false, login: async () => {}, logout: async () => {}, refresh: async () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null)
      return
    }
    try {
      setUser(await api<User>('/api/auth/me'))
    } catch {
      setUser(null)
    }
  }, [])

  useEffect(() => {
    ;(async () => {
      await loadPersisted()
      await refresh()
      setReady(true)
    })()
    const off = onUnauthorized(() => {
      setToken(null)
      setUser(null)
    })
    return () => {
      off()
    }
  }, [refresh])

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ access_token: string; user: User }>('/api/auth/login-json', { body: { email, password } })
    await setToken(r.access_token)
    setUser(r.user)
  }, [])

  const logout = useCallback(async () => {
    await setToken(null)
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, ready, login, logout, refresh }), [user, ready, login, logout, refresh])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
