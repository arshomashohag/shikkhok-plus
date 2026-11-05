/** A month's latest payment, in a line (`HistoryLineText.kt`). */
import { formatShortDate } from '../../../core/format'
import { useT } from '../../../i18n/i18n'
import { HISTORY_FORMAT, type HistoryLine } from './fees'

export function HistoryLineText({ line }: { line: HistoryLine }) {
  const { t, lang } = useT()
  const channel = line.channel === 'cash' ? t('verify_method_cash') : line.channel
  return (
    <div className="meta">
      <div>
        {t(
          HISTORY_FORMAT[line.outcome],
          line.amount.format(),
          channel,
          formatShortDate(line.paidOn, lang),
        )}
      </div>
      {line.coveredNames.length > 0 ? (
        <div>{t('history_line_for', line.coveredNames.join(', '))}</div>
      ) : null}
      {line.decisionNote ? <div>{t('history_note', line.decisionNote)}</div> : null}
    </div>
  )
}
