import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { usePortalAuth } from '../auth'
import NoticeBar from './NoticeBar'
import '../theme.css'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `portal-nav-link${isActive ? ' is-active' : ''}`

type BreadcrumbItem = {
  label: string
  to?: string
}

function breadcrumbItems(pathname: string): BreadcrumbItem[] {
  const segments = pathname
    .replace(/^\/css-demo\/?/, '')
    .split('/')
    .filter(Boolean)

  if (segments.length === 0) {
    return [{ label: 'Home' }]
  }

  const items: BreadcrumbItem[] = [{ label: 'Home', to: '/css-demo' }]

  if (segments[0] === 'login') {
    items.push({ label: 'Login' })
  } else if (segments[0] === 'register') {
    items.push({ label: 'Register' })
  } else if (segments[0] === 'submit') {
    items.push({ label: 'Submit Request' })
  } else if (segments[0] === 'track') {
    items.push({ label: 'Track Request' })
  } else if (segments[0] === 'requests') {
    items.push({ label: 'My Requests', to: '/css-demo/requests' })
    if (segments[1]) {
      items.push({ label: segments[1] })
    }
  } else {
    items.push({ label: segments[0] })
  }

  return items
}

export default function PortalLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const { isAuthenticated, logout: clearSession } = usePortalAuth()
  const [signingOut, setSigningOut] = useState(false)
  const breadcrumb = breadcrumbItems(location.pathname)

  // Clear the session only after the public home route has committed. Clearing
  // first lets PortalProtectedRoute redirect the protected page to
  // /css-demo/login instead of returning the user to /css-demo.
  useEffect(() => {
    if (signingOut && location.pathname === '/css-demo') {
      clearSession()
      setSigningOut(false)
    }
  }, [signingOut, location.pathname, clearSession])

  const logout = () => {
    setSigningOut(true)
    navigate('/css-demo')
  }

  return (
    <div className="css-portal">
      <NoticeBar />

      <header className="portal-header">
        <div className="portal-header-inner">
          <div className="portal-wordmark">Centralized Support System</div>
          <div className="portal-wordmark-sub">Educational demonstration</div>
        </div>
      </header>

      <nav className="portal-nav" aria-label="Portal navigation">
        <div className="portal-nav-inner">
          <NavLink to="/css-demo" end className={navLinkClass}>
            Home
          </NavLink>
          {isAuthenticated ? (
            <>
              <NavLink to="/css-demo/submit" className={navLinkClass}>
                Submit Request
              </NavLink>
              <NavLink to="/css-demo/requests" className={navLinkClass}>
                My Requests
              </NavLink>
              <NavLink to="/css-demo/track" className={navLinkClass}>
                Track Request
              </NavLink>
              <button type="button" className="portal-nav-button" onClick={logout}>
                Logout
              </button>
            </>
          ) : (
            <>
              <NavLink to="/css-demo/register" className={navLinkClass}>
                Register
              </NavLink>
              <NavLink to="/css-demo/login" className={navLinkClass}>
                Login
              </NavLink>
            </>
          )}
        </div>
      </nav>

      <nav className="portal-breadcrumb" aria-label="Breadcrumb">
        <ol className="portal-breadcrumb-list">
          {breadcrumb.map((item, index) => {
            const isLast = index === breadcrumb.length - 1
            return (
              <li key={`${item.label}-${index}`}>
                {item.to && !isLast ? (
                  <NavLink to={item.to}>{item.label}</NavLink>
                ) : (
                  <span aria-current={isLast ? 'page' : undefined}>{item.label}</span>
                )}
              </li>
            )
          })}
        </ol>
      </nav>

      <main className="portal-main">
        <Outlet />
      </main>

      <footer className="portal-footer">
        Simulated demonstration. Do not enter real personal information.
      </footer>
    </div>
  )
}
