/**
 * Routes. Which tabs exist depends on the lens (see shell/nav.ts); a
 * route outside the current lens's set redirects home rather than
 * rendering — the server would refuse its data anyway, and a screen that
 * loads only to show an authorization error teaches nothing.
 */
import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { useT } from './i18n/i18n'
import { useSession, type Lens } from './session/session'
import { AppShell } from './shell/AppShell'
import { homeFor } from './shell/nav'
import { ErrorCard, Loading } from './ui/components'
import { SignIn } from './features/auth/SignIn'
import { SignUp } from './features/auth/SignUp'
import { Today } from './features/teacher/Today'
import { Batches, CreateBatch } from './features/teacher/Batches'
import { BatchDetail } from './features/teacher/BatchDetail'
import { Dues } from './features/teacher/Dues'
import { Verify } from './features/teacher/Verify'
import { MyBatches } from './features/student/MyBatches'
import { GuardianHome } from './features/guardian/GuardianHome'
import { Invitations } from './features/account/Invitations'
import { LensPicker } from './features/account/LensPicker'
import { More } from './features/account/More'
import { Settings } from './features/account/Settings'
import { classesRoutes } from './features/teacher/classes'
import { examsRoutes } from './features/teacher/exams'
import { peopleRoutes } from './features/teacher/people'
import { studentsRoutes } from './features/teacher/students'
import { moneyRoutes } from './features/teacher/money'

import { batchRoutes } from './features/family/batch'
import { payRoutes } from './features/family/pay'
import { accountRoutes } from './features/account/area'
import { seatPattern, type Reader } from './features/family/reader'

/** Seat routes the family areas own, mounted once per reader. */
const FAMILY_ROUTES = [...batchRoutes, ...payRoutes]
const READER_LENS: Record<Reader, Lens> = { me: 'student', child: 'guardian' }

/** Routes the teacher areas own (features/teacher/<area>/index.tsx). */
const AREA_ROUTES = [
  ...classesRoutes,
  ...examsRoutes,
  ...studentsRoutes,
  ...peopleRoutes,
  ...moneyRoutes,
]

function Only({
  lens,
  current,
  children,
}: {
  lens: Lens
  current: Lens | null
  children: ReactNode
}) {
  return lens === current ? children : <Navigate to={homeFor(current)} replace />
}

export function App() {
  const { session, refresh } = useSession()
  const { t } = useT()

  if (session.state === 'signed-out') {
    return (
      <Routes>
        <Route path="/signin" element={<SignIn />} />
        <Route path="/signup" element={<SignUp />} />
        <Route path="*" element={<Navigate to="/signin" replace />} />
      </Routes>
    )
  }

  if (session.state === 'resolving') {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <p className="meta" role="status">
            {t('auth_restoring')}
          </p>
          <Loading rows={2} />
        </div>
      </div>
    )
  }

  if (session.state === 'failed') {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <ErrorCard
            title={session.error.offline ? t('offline_title') : t('error_unexpected')}
            error={session.error}
            onRetry={refresh}
          />
        </div>
      </div>
    )
  }

  if (session.choosing) return <LensPicker options={session.options} />

  const lens = session.lens
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route
          path="/today"
          element={
            <Only lens="teacher" current={lens}>
              <Today />
            </Only>
          }
        />
        <Route
          path="/batches"
          element={
            <Only lens="teacher" current={lens}>
              <Batches />
            </Only>
          }
        />
        <Route
          path="/batches/new"
          element={
            <Only lens="teacher" current={lens}>
              <CreateBatch />
            </Only>
          }
        />
        <Route
          path="/batches/:batchId"
          element={
            <Only lens="teacher" current={lens}>
              <BatchDetail />
            </Only>
          }
        />
        <Route
          path="/dues"
          element={
            <Only lens="teacher" current={lens}>
              <Dues />
            </Only>
          }
        />
        <Route
          path="/verify"
          element={
            <Only lens="teacher" current={lens}>
              <Verify />
            </Only>
          }
        />
        <Route
          path="/my-batches"
          element={
            <Only lens="student" current={lens}>
              <MyBatches />
            </Only>
          }
        />
        <Route
          path="/children"
          element={
            <Only lens="guardian" current={lens}>
              <GuardianHome />
            </Only>
          }
        />
        {AREA_ROUTES.map((r) => (
          <Route
            key={r.path}
            path={r.path}
            element={
              <Only lens="teacher" current={lens}>
                {r.element}
              </Only>
            }
          />
        ))}
        {(['me', 'child'] as const).flatMap((reader) =>
          FAMILY_ROUTES.map((r) => {
            const path = r.path ? `${seatPattern(reader)}/${r.path}` : seatPattern(reader)
            return (
              <Route
                key={path}
                path={path}
                element={
                  <Only lens={READER_LENS[reader]} current={lens}>
                    {r.element(reader)}
                  </Only>
                }
              />
            )
          }),
        )}
        {accountRoutes.map((r) => (
          <Route key={r.path} path={r.path} element={r.element} />
        ))}
        <Route path="/invitations" element={<Invitations />} />
        <Route path="/more" element={<More />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to={homeFor(lens)} replace />} />
      </Route>
    </Routes>
  )
}
