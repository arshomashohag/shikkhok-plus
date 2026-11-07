/**
 * The admin app's routes, at the root of the admin host.
 *
 * Signed out, every address leads to `/signin`, remembering where the
 * administrator was going; signed in, `/signin` sends them on there. The
 * session ends on a 401 from any call or when the hour is up, and this
 * component then takes them back to sign-in from wherever they were.
 */
import { Navigate, Route, Routes, useLocation } from 'react-router'
import { lazyScreen } from '../core/lazy'
import './strings'
import { AdminShell } from './AdminChrome'
import { AdminSignIn } from './auth/AdminSignIn'
import { useAdminSession } from './useAdminSession'

/** Every screen is one chunk, fetched after sign-in. Paths match `adminPaths`. */
const load = () => import('./screens/AdminArea')

const SCREENS = [
  { path: '/', element: lazyScreen(load, 'AdminOverview') },
  { path: '/teachers', element: lazyScreen(load, 'AdminTeachers') },
  { path: '/help', element: lazyScreen(load, 'AdminRequesters') },
  { path: '/help/tickets', element: lazyScreen(load, 'AdminTickets') },
  { path: '/help/tickets/:ticketId', element: lazyScreen(load, 'AdminTicketView') },
]

/** Only a path inside this app, never `//other.host` or the sign-in itself. */
export function safeReturnPath(from: unknown): string {
  if (typeof from !== 'string' || !from.startsWith('/') || from.startsWith('//')) return '/'
  if (from === '/signin' || from.startsWith('/signin?')) return '/'
  return from
}

function ToSignIn() {
  const location = useLocation()
  return (
    <Navigate to="/signin" replace state={{ from: `${location.pathname}${location.search}` }} />
  )
}

function OnwardFromSignIn() {
  const location = useLocation()
  const from = (location.state as { from?: unknown } | null)?.from
  return <Navigate to={safeReturnPath(from)} replace />
}

export function AdminApp() {
  const session = useAdminSession()

  if (!session)
    return (
      <Routes>
        <Route path="/signin" element={<AdminSignIn />} />
        <Route path="*" element={<ToSignIn />} />
      </Routes>
    )

  return (
    <Routes>
      <Route path="/signin" element={<OnwardFromSignIn />} />
      <Route element={<AdminShell session={session} />}>
        {SCREENS.map((r) => (
          <Route key={r.path} path={r.path} element={r.element} />
        ))}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
