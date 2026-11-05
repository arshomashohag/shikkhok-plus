/**
 * G3 · Progress in one batch, for a student or a guardian (Android
 * `ProgressScreen`, the design's "Guardian progress").
 *
 * A guardian first sees the server's one-sentence run ("Marks went up in
 * each of the last 4 tests, from 31 to 44 out of 50. Now above the batch
 * average."); the server sends the run, both marks and the direction, and
 * sends nothing when there are fewer than two results. Then every exam in
 * the server's order with the mark, rank and batch average it sent — an
 * absence says "Absent", never a zero. Each row opens the marksheet.
 */
import { Link } from 'react-router'
import { formatMark, formatShortDate } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, TopBar } from '../../../ui/components'
import { familyPaths, type Reader } from '../reader'
import { readProgress, readProgressSummary } from './api'
import {
  formatAverage,
  mapProgress,
  mapSummary,
  RESULT_STATE_LABEL,
  type ProgressRow,
  type ProgressSummary,
} from './mappers'
import { useSeatId, useSeatIdentity } from './seat'

async function load(reader: Reader, seat: string) {
  const [rows, summary] = await Promise.all([
    readProgress(reader, seat).then(mapProgress),
    reader === 'child'
      ? readProgressSummary(seat).then(mapSummary, () => null)
      : Promise.resolve(null),
  ])
  return { rows, summary }
}

export function ProgressScreen({ reader }: { reader: Reader }) {
  const seat = useSeatId()
  const { t } = useT()
  const identity = useSeatIdentity(reader, seat)
  const title = identity?.childName
    ? t('progress_of_child', identity.childName)
    : t('screen_title_progress')
  const subtitle =
    [identity?.childName, identity?.batchName].filter(Boolean).join(' · ') || undefined
  const { resource, reload } = useResource(() => load(reader, seat), [reader, seat])

  return (
    <>
      <TopBar title={title} subtitle={subtitle} back />
      {resource.state === 'loading' ? (
        <Loading rows={4} />
      ) : resource.state === 'failed' ? (
        <ErrorCard title={t('dashboard_load_failed')} error={resource.error} onRetry={reload} />
      ) : resource.data.rows.length === 0 ? (
        <EmptyState title={t('progress_empty')} body={t('student_results_empty')} />
      ) : (
        <>
          {resource.data.summary ? <SummaryCard summary={resource.data.summary} /> : null}
          <ProgressTable reader={reader} seat={seat} rows={resource.data.rows} />
        </>
      )}
    </>
  )
}

/** The server's run, worded. Exported for its test. */
export function summaryText(
  s: ProgressSummary,
  t: (key: string, ...args: (string | number)[]) => string,
): string {
  const key =
    s.direction === 'up'
      ? 'web_fb_summary_up'
      : s.direction === 'down'
        ? 'web_fb_summary_down'
        : 'web_fb_summary_same'
  const run = t(key, s.run, formatMark(s.firstMarks), formatMark(s.lastMarks), s.totalMarks)
  if (s.aboveAverage === null) return run
  return `${run} ${t(s.aboveAverage ? 'web_fb_above_average' : 'web_fb_below_average')}`
}

function SummaryCard({ summary }: { summary: ProgressSummary }) {
  const { t } = useT()
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <p style={{ margin: 0 }}>{summaryText(summary, t)}</p>
    </div>
  )
}

function ProgressTable({
  reader,
  seat,
  rows,
}: {
  reader: Reader
  seat: string
  rows: ProgressRow[]
}) {
  const { t, lang } = useT()
  return (
    <div className="card flush">
      <table className="fb-table">
        <thead>
          <tr>
            <th scope="col">{t('web_fb_col_test')}</th>
            <th scope="col">{t('progress_marks')}</th>
            <th scope="col">{t('web_fb_col_rank')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.examId}>
              <th scope="row">
                <Link to={familyPaths.marksheet(reader, seat, r.examId)}>{r.title}</Link>
                <span className="meta" style={{ display: 'block' }}>
                  {[r.subjectName, formatShortDate(r.date, lang)].filter(Boolean).join(' · ')}
                  {r.batchAverage !== null
                    ? ` · ${t('web_fb_batch_average', formatAverage(r.batchAverage))}`
                    : ''}
                </span>
              </th>
              <td>
                {r.marks !== null ? (
                  <>
                    <strong>{formatMark(r.marks)}</strong>
                    <span className="meta">{t('student_out_of', r.totalMarks)}</span>
                  </>
                ) : (
                  <span className="meta">{t(RESULT_STATE_LABEL[r.state])}</span>
                )}
              </td>
              <td>
                {r.rank !== null && r.rankedOutOf !== null
                  ? t('web_fb_rank_of', r.rank, r.rankedOutOf)
                  : '–'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
