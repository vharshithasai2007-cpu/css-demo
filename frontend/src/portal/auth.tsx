import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import portalApi, { PORTAL_TOKEN_KEY, type PortalUser } from './api'

type PortalAuthStatus = 'loading' | 'authenticated' | 'anonymous'

type PortalAuthValue = {
  user: PortalUser | null
  token: string | null
  status: PortalAuthStatus
  isAuthenticated: boolean
  login: (token: string) => void
  logout: () => void
}

const PortalAuthContext = createContext<PortalAuthValue | undefined>(undefined)

export function PortalAuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem(PORTAL_TOKEN_KEY),
  )
  const [user, setUser] = useState<PortalUser | null>(null)
  const [status, setStatus] = useState<PortalAuthStatus>(() =>
    token ? 'loading' : 'anonymous',
  )

  useEffect(() => {
    if (!token) {
      setUser(null)
      setStatus('anonymous')
      return
    }

    let cancelled = false
    setStatus('loading')

    portalApi
      .get<PortalUser>('/portal/auth/me')
      .then((response) => {
        if (cancelled) return
        setUser(response.data)
        setStatus('authenticated')
      })
      .catch(() => {
        if (cancelled) return
        // The portal axios interceptor already handles 401. Clearing here also
        // covers network failures so the protected route cannot stay stuck.
        localStorage.removeItem(PORTAL_TOKEN_KEY)
        setToken(null)
        setUser(null)
        setStatus('anonymous')
      })

    return () => {
      cancelled = true
    }
  }, [token])

  const login = useCallback((nextToken: string) => {
    localStorage.setItem(PORTAL_TOKEN_KEY, nextToken)
    setToken(nextToken)
    setStatus('loading')
  }, [])

  const logout = useCallback(() => {
    // Only the portal key is removed. The dashboard's `token` is untouched.
    localStorage.removeItem(PORTAL_TOKEN_KEY)
    setToken(null)
    setUser(null)
    setStatus('anonymous')
  }, [])

  const value = useMemo<PortalAuthValue>(
    () => ({
      user,
      token,
      status,
      isAuthenticated: Boolean(token),
      login,
      logout,
    }),
    [user, token, status, login, logout],
  )

  return (
    <PortalAuthContext.Provider value={value}>{children}</PortalAuthContext.Provider>
  )
}

export function usePortalAuth(): PortalAuthValue {
  const context = useContext(PortalAuthContext)
  if (!context) {
    throw new Error('usePortalAuth must be used inside PortalAuthProvider')
  }
  return context
}

export function PortalProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, status } = usePortalAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return (
      <Navigate
        to="/css-demo/login"
        replace
        state={{ from: location.pathname }}
      />
    )
  }

  if (status === 'loading') {
    return <p>Checking your session…</p>
  }

  return <>{children}</>
}
