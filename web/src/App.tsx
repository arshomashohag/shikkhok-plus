/**
 * Routes. Which tabs exist depends on the lens (see shell/nav.ts); a
 * route outside the current lens's set redirects home rather than
 * rendering — the server would refuse its data anyway, and a screen that
 * loads only to show an authorization error teaches nothing.
 *
 * Before any lens, and before any route, an account the server says has
 * no username sees only the choose-username gate [FR5.2].
 */
import { useEffect, useState, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router'
import { lazyScreen } from './core/lazy'
import { useT } from './i18n/i18n'
import { useSession, type Lens } from './session/session'
import { AppShell } from './shell/AppShell'
import { RouteErrorBoundary } from './shell/RouteErrorBoundary'
import { homeFor } from './shell/nav'
import { ErrorCard, Loading } from './ui/components'
import { SignIn } from './features/auth/SignIn'
import { SignUp } from './features/auth/SignUp'
import { PasswordCode } from './features/auth/PasswordCode'
import { Today } from './features/teacher/Today'
import { Batches, CreateBatch } from './features/teacher/Batches'
import { BatchDetail } from './features/teacher/BatchDetail'
import { Dues } from './features/teacher/Dues'
import { Verify } from './features/teacher/Verify'
import { MyBatches } from './features/student/MyBatches'
import { GuardianHome } from './features/guardian/GuardianHome'
import { MyReviews } from './features/family/reviews/MyReviews'
import { MyEnquiries } from './features/account/MyEnquiries'
import { Invitations } from './features/account/Invitations'
import { ClassScreen } from './features/classTeacher/ClassScreen'
import { MyClasses } from './features/classTeacher/MyClasses'
import { MyExamMarks, MyExams } from './features/classTeacher/MyExams'
import { MyPay } from './features/classTeacher/MyPay'
import { LensPicker } from './features/account/LensPicker'
import { ChooseUsernameGate } from './features/account/username/ChooseUsernameGate'
import { More } from './features/account/More'
import { Settings } from './features/account/Settings'
import { classesRoutes } from './features/teacher/classes'
import { examsRoutes } from './features/teacher/exams'
import { peopleRoutes } from './features/teacher/people'
import { studentsRoutes } from './features/teacher/students'
import { moneyRoutes } from './features/teacher/money'
import { centreRoutes } from './features/teacher/centre'
import { hubRoutes } from './features/teacher/hub'

import { batchRoutes } from './features/family/batch'
import { payRoutes } from './features/family/pay'
import { accountRoutes } from './features/account/area'
import { helpRoutes } from './features/help'
import { securityRoutes } from './features/account/security'
import { seatPattern, type Reader } from './features/family/reader'
import { forgetReturn, peekReturn, rememberReturn } from './session/returnPath'

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
  ...centreRoutes,
  ...hubRoutes,
]

/**
 * Reporting a public hub page, opened from the page's "Report this page"
 * link; any lens may report. A separate chunk: most sessions never open it.
 */
const HUB_REPORT = lazyScreen(() => import('./features/common/HubReport'), 'HubReport')

/**
 * Asking an owner to take a student, opened from a public page's "Ask to
 * join" link [H5]; any lens may ask. A chunk of its own: most sessions
 * never open it. The caller's own requests load with More, whose row
 * shares their module.
 */
const HUB_ENQUIRY = lazyScreen(() => import('./features/common/HubEnquiry'), 'HubEnquiry')

/**
 * One batch's review, by its guardian author [H4]. The list loads with the
 * guardian home, whose entry it shares a module with; the editor on first use.
 */
const REVIEW_EDITOR = lazyScreen(
  () => import('./features/family/reviews/ReviewEditor'),
  'ReviewEditor',
)

/**
 * Signed out on a public link (report a page [H2 task 9], ask to join
 * [H5]): remember it, then sign in. `returnPath.ts` keeps only those two.
 */
function SignInThenReturn() {
  const { pathname, search } = useLocation()
  const [here] = useState(`${pathname}${search}`)
  useEffect(() => rememberReturn(here), [here])
  return <Navigate to="/signin" replace />
}

/**
 * Where an address the routes do not know lands: home, unless a report or
 * join-request link was remembered before sign-in, in which case there.
 * Read without consuming during render (StrictMode renders twice) and
 * forgotten once the landing has happened.
 */
function Landing({ home }: { home: string }) {
  const [to] = useState(() => peekReturn() ?? home)
  useEffect(forgetReturn, [])
  return <Navigate to={to} replace />
}

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

/**
 * Everything the app renders, inside the one render-error boundary, which
 * clears itself when the pathname changes [functional-spec § 10 item 2].
 */
export function App() {
  const { pathname } = useLocation()
  const { signOut } = useSession()
  return (
    <RouteErrorBoundary pathname={pathname} onSignOut={signOut}>
      <AppRoutes />
    </RouteErrorBoundary>
  )
}

function AppRoutes() {
  const { session, refresh, signOut } = useSession()
  const { t } = useT()

  if (session.state === 'signed-out') {
    return (
      <Routes>
        <Route path="/signin" element={<SignIn />} />
        <Route path="/signin/code" element={<PasswordCode />} />
        <Route path="/signup" element={<SignUp />} />
        <Route path="/hub-report" element={<SignInThenReturn />} />
        <Route path="/hub-enquiry" element={<SignInThenReturn />} />
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
          {/* Always a way out, even when the failure offers no Retry [NFR3.15]. */}
          <div className="button-row">
            <button type="button" className="btn btn-text" onClick={signOut}>
              {t('more_log_out')}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Not a route: a typed URL, Back and Forward all land here, and the
  // URL is kept for when the gate lifts [FR5.2] [NFR3.14].
  if (session.state === 'username-required') return <ChooseUsernameGate me={session.me} />

  if (session.choosing) return <LensPicker options={session.options} />

  const lens = session.lens
  // Keyed on the workspace, so switching between a tutor's own batches and
  // a centre re-reads every screen under the new one.
  return (
    <Routes key={session.workspace ?? 'default'}>
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
          path="/my-classes"
          element={
            <Only lens="class_teacher" current={lens}>
              <MyClasses />
            </Only>
          }
        />
        <Route
          path="/my-classes/:sessionId"
          element={
            <Only lens="class_teacher" current={lens}>
              <ClassScreen />
            </Only>
          }
        />
        <Route
          path="/my-exams"
          element={
            <Only lens="class_teacher" current={lens}>
              <MyExams />
            </Only>
          }
        />
        <Route
          path="/my-exams/:examId"
          element={
            <Only lens="class_teacher" current={lens}>
              <MyExamMarks />
            </Only>
          }
        />
        <Route
          path="/my-pay"
          element={
            <Only lens="class_teacher" current={lens}>
              <MyPay />
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
        <Route
          path="/reviews"
          element={
            <Only lens="guardian" current={lens}>
              <MyReviews />
            </Only>
          }
        />
        <Route
          path="/reviews/:batchId"
          element={
            <Only lens="guardian" current={lens}>
              {REVIEW_EDITOR}
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
        {/* Every lens: the account area, two-step verification and the help centre. */}
        {[...accountRoutes, ...securityRoutes, ...helpRoutes].map((r) => (
          <Route key={r.path} path={r.path} element={r.element} />
        ))}
        <Route path="/hub-report" element={HUB_REPORT} />
        <Route path="/hub-enquiry" element={HUB_ENQUIRY} />
        <Route path="/hub-enquiries" element={<MyEnquiries />} />
        <Route path="/invitations" element={<Invitations />} />
        <Route path="/more" element={<More />} />
        <Route path="/settings" element={<Settings />} />
        {/* After sign-in the address is /signin or /signup: this lands it. */}
        <Route path="*" element={<Landing home={homeFor(lens)} />} />
      </Route>
    </Routes>
  )
}
