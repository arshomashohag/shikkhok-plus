/**
 * S2 · One batch, for the student who attends it or a guardian of the
 * child who does (Android `StudentBatchScreen`, both readers).
 *
 * Header: subjects, the next class and the ones after it, this month's
 * fee (opening the fee history, with "Send money" while something is
 * owed), and Progress. Then four tabs, kept in the URL: the month's
 * classes with their topics and attendance, exams (results and coming
 * up), notices, and the teacher.
 *
 * The fee card is the one place a payment status is shown, so when the
 * page could not refresh it is replaced by "Fee status unavailable"
 * rather than left showing what may no longer be true.
 */
import { Link, useSearchParams } from 'react-router'
import { formatMark, formatMonth, formatShortDate, howSoon, initial } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import {
  EmptyState,
  ErrorCard,
  FeeChip,
  Loading,
  Section,
  StaleBanner,
  TopBar,
} from '../../../ui/components'
import { ChevronIcon } from '../../../ui/icons'
import { familyPaths, type Reader } from '../reader'
import { readProgress, readTeaching } from './api'
import { ClassesTab } from './ClassesTab'
import { dayLabel, timeRange } from './format'
import {
  mapProgress,
  mapTeaching,
  RESULT_STATE_LABEL,
  resultsByExam,
  type FamilyExam,
  type FeeLine,
  type NextClass,
  type ProgressRow,
  type SeatView,
} from './mappers'
import { seatTitles, useHeading, useSeatId, useSeatIdentity } from './seat'
import type { SeatIdentity } from './mappers'

type Tab = 'classes' | 'exams' | 'notices' | 'teacher'
const TABS: readonly Tab[] = ['classes', 'exams', 'notices', 'teacher']
const TAB_LABEL: Record<Tab, string> = {
  classes: 'batch_tab_classes',
  exams: 'batch_tab_exams',
  notices: 'batch_tab_notices',
  teacher: 'family_tab_teacher',
}

interface Loaded {
  view: SeatView
  /** Null when results could not be read; the rest of the page still shows. */
  results: Map<string, ProgressRow> | null
}

async function load(reader: Reader, seat: string, signal?: AbortSignal): Promise<Loaded> {
  const [teaching, progress] = await Promise.all([
    readTeaching(reader, seat, signal),
    readProgress(reader, seat, signal).then(
      (rows) => rows,
      () => null,
    ),
  ])
  return {
    view: mapTeaching(teaching),
    results: progress ? resultsByExam(mapProgress(progress)) : null,
  }
}

export function SeatBatch({ reader }: { reader: Reader }) {
  const seat = useSeatId()
  const { t } = useT()
  const identity = useSeatIdentity(reader, seat)
  const { batch, who } = seatTitles(identity)
  const title = batch ?? t('my_batches_title')
  const [search, setSearch] = useSearchParams()
  const requested = search.get('tab') as Tab | null
  const tab: Tab = requested && TABS.includes(requested) ? requested : 'classes'
  const { resource, reload } = useResource((signal) => load(reader, seat, signal), [reader, seat])

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={title} subtitle={who} back />
        <Loading rows={4} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={title} subtitle={who} back />
        <ErrorCard title={title} error={resource.error} onRetry={reload} />
      </>
    )
  }

  const { view, results } = resource.data
  const stale = resource.error !== null
  return (
    <>
      <TopBar title={title} subtitle={who} back />
      {stale && resource.error ? (
        <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
      ) : null}
      {view.subjects.length ? <p className="meta">{view.subjects.join(' · ')}</p> : null}
      <div className="dash dash-2 seat-top">
        <NextClassCard next={view.next} following={view.following} identity={identity} />
        <FeeCard
          reader={reader}
          seat={seat}
          fee={view.fee}
          stale={stale}
          identity={identity}
          onRetry={reload}
        />
      </div>
      <div className="button-row" style={{ marginTop: 8 }}>
        <Link className="btn btn-text btn-small" to={familyPaths.progress(reader, seat)}>
          {t('dashboard_open_progress')}
        </Link>
      </div>

      <div className="tabs" role="tablist" style={{ marginTop: 8 }}>
        {TABS.map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            onClick={() => setSearch(k === 'classes' ? {} : { tab: k }, { replace: true })}
          >
            {t(TAB_LABEL[k])}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === 'classes' ? <ClassesTab reader={reader} seat={seat} identity={identity} /> : null}
        {tab === 'exams' ? (
          <ExamsTab reader={reader} seat={seat} view={view} results={results} identity={identity} />
        ) : null}
        {tab === 'notices' ? <NoticesTab reader={reader} seat={seat} view={view} /> : null}
        {tab === 'teacher' ? <TeacherTab view={view} /> : null}
      </div>
    </>
  )
}

function NextClassCard({
  next,
  following,
  identity,
}: {
  next: NextClass | null
  following: NextClass[]
  identity: SeatIdentity | null
}) {
  const { t, lang } = useT()
  const heading = useHeading()
  if (!next) {
    return (
      <div className="card" style={{ marginTop: 12 }}>
        <span className="meta">{t('student_no_next_class')}</span>
      </div>
    )
  }
  const range = timeRange(next.startTime, next.endTime, lang)
  // "Today" only where the server sent a countdown, which it does only
  // for a class today; the client compares no dates (`whenLabel`).
  const when =
    next.startsInMinutes !== null
      ? t('student_today_at', range)
      : t('student_day_at', dayLabel(next.date, lang), range)
  const then = following.length
    ? t(
        'student_then',
        following
          .map((f) =>
            f.moved
              ? t('student_moved_to', dayLabel(f.date, lang), timeRange(f.startTime, null, lang))
              : dayLabel(f.date, lang),
          )
          .join(', '),
      )
    : null
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="meta accent">
        {identity?.childName
          ? heading(identity, 'student_next_class', 'web_fb_child_next_class')
          : howSoon(next.startsInMinutes, t)}
      </div>
      <div className="hero-amount" style={{ fontSize: '1.5rem' }}>
        {when}
      </div>
      {next.subjectName ? <div className="meta">{next.subjectName}</div> : null}
      {then ? <div className="meta">{then}</div> : null}
    </div>
  )
}

function FeeCard({
  reader,
  seat,
  fee,
  stale,
  identity,
  onRetry,
}: {
  reader: Reader
  seat: string
  fee: FeeLine | null
  stale: boolean
  identity: SeatIdentity | null
  onRetry: () => void
}) {
  const { t, lang } = useT()
  if (stale) {
    return (
      <div className="card" style={{ marginTop: 12 }}>
        <div className="title">{t('family_fee_unavailable')}</div>
        <p className="meta">{t('family_fee_unavailable_body')}</p>
        <button type="button" className="btn btn-outline" onClick={onRetry}>
          {t('auth_retry')}
        </button>
      </div>
    )
  }
  if (!fee) {
    return (
      <div className="button-row" style={{ marginTop: 8 }}>
        <Link className="btn btn-text btn-small" to={familyPaths.fees(reader, seat)}>
          {t('screen_title_fee_history')}
        </Link>
      </div>
    )
  }
  const month = formatMonth(fee.period, lang)
  const line = fee.charged
    ? t('student_fee_month_amount', month, fee.charged.format())
    : t('student_fee_month', month)
  return (
    <div className="card fb-fee" style={{ marginTop: 12 }}>
      <Link className="fb-fee-main" to={familyPaths.fees(reader, seat)}>
        <span className="grow">
          {identity?.childName ? (
            <span className="label">{t('web_fb_child_fee', identity.childName)}</span>
          ) : null}
          <span className="title" style={{ display: 'block' }}>
            {line}
          </span>
          <span className="meta">
            {fee.paidOn
              ? t('student_paid_on', formatShortDate(fee.paidOn, lang))
              : t('student_due_by', formatShortDate(fee.dueDate, lang))}
          </span>
        </span>
        <FeeChip chip={fee.chip} />
      </Link>
      {fee.payable ? (
        <div className="button-row">
          <Link className="btn btn-primary btn-money" to={familyPaths.pay(reader, seat)}>
            {t('student_pay_this')}
          </Link>
        </div>
      ) : null}
    </div>
  )
}

function ExamsTab({
  reader,
  seat,
  view,
  results,
  identity,
}: {
  reader: Reader
  seat: string
  view: SeatView
  results: Map<string, ProgressRow> | null
  identity: SeatIdentity | null
}) {
  const { t } = useT()
  const heading = useHeading()
  if (view.doneExams.length === 0 && view.upcomingExams.length === 0) {
    return <EmptyState title={t('student_results_empty')} />
  }
  return (
    <>
      {view.doneExams.length ? (
        <Section title={heading(identity, 'student_results', 'web_fb_child_results')}>
          <ul className="card flush list">
            {view.doneExams.map((e) => (
              <li key={e.examId}>
                <ExamRow
                  exam={e}
                  result={results?.get(e.examId) ?? null}
                  to={familyPaths.marksheet(reader, seat, e.examId)}
                />
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {view.upcomingExams.length ? (
        <Section title={heading(identity, 'student_coming_up', 'web_fb_child_coming_up')}>
          <ul className="card flush list">
            {view.upcomingExams.map((e) => (
              <li key={e.examId}>
                <ExamRow exam={e} result={null} to={familyPaths.exam(reader, seat, e.examId)} />
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </>
  )
}

function ExamRow({
  exam,
  result,
  to,
}: {
  exam: FamilyExam
  result: ProgressRow | null
  to: string
}) {
  const { t, lang } = useT()
  const meta = [exam.subjectName, formatShortDate(exam.date, lang)]
  if (result?.rank !== null && result?.rank !== undefined && result.rankedOutOf !== null) {
    meta.push(t('web_fb_rank_of', result.rank, result.rankedOutOf))
  } else {
    meta.push(t('batch_exam_out_of', exam.totalMarks))
  }
  return (
    <Link className="row" to={to}>
      <span className="grow">
        <span className="title" style={{ display: 'block' }}>
          {exam.title}
        </span>
        <span className="meta">{meta.join(' · ')}</span>
      </span>
      {result ? (
        result.marks !== null ? (
          <span>
            <strong style={{ fontSize: '1.25rem' }}>{formatMark(result.marks)}</strong>
            <span className="meta">{t('student_out_of', result.totalMarks)}</span>
          </span>
        ) : (
          <span className="meta">{t(RESULT_STATE_LABEL[result.state])}</span>
        )
      ) : null}
      <ChevronIcon />
    </Link>
  )
}

function NoticesTab({ reader, seat, view }: { reader: Reader; seat: string; view: SeatView }) {
  const { t } = useT()
  if (view.notices.length === 0) return <EmptyState title={t('family_notices_empty')} />
  return (
    <ul className="card flush list">
      {view.notices.map((n) => (
        <li key={n.id}>
          <Link className="row" to={familyPaths.notice(reader, seat, n.id)}>
            <span className="grow">
              <span className="fb-clamp">{n.body}</span>
              <NoticeMeta postedAt={n.postedAt} edited={n.edited} />
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

export function NoticeMeta({ postedAt, edited }: { postedAt: string; edited: boolean }) {
  const { t, lang } = useT()
  return (
    <span className="meta" style={{ display: 'block' }}>
      {[formatShortDate(postedAt, lang), edited ? t('family_notice_edited') : null]
        .filter(Boolean)
        .join(' · ')}
    </span>
  )
}

function TeacherTab({ view }: { view: SeatView }) {
  const { t } = useT()
  return (
    <>
      <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span className="avatar primary" aria-hidden="true">
          {initial(view.teacherName ?? '?')}
        </span>
        <span className="title" style={{ fontSize: '1.25rem' }}>
          {view.teacherName ?? t('family_teacher_unnamed')}
        </span>
      </div>
      <Section title={t('family_teacher_subjects')}>
        {view.subjects.length === 0 ? (
          <div className="card meta">{t('family_teacher_no_subjects')}</div>
        ) : (
          <ul className="card flush list">
            {view.subjects.map((s) => (
              <li key={s} className="row" style={{ minHeight: 56 }}>
                {s}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  )
}
