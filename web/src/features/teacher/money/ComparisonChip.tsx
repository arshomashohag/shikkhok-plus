/**
 * How a payment stands against what is owed, as the server compared it.
 * Shared by the queue card and the payment detail (`ComparisonChip` in
 * VerifyScreen.kt). The difference shown is the server's.
 */
import { formatShortMonth } from '../../../core/format'
import { useT } from '../../../i18n/i18n'
import { CheckCircleIcon, CircleIcon, HalfCircleIcon } from '../../../ui/icons'
import type { PaymentReview } from '../mappers'

export function ComparisonChip({ review }: { review: PaymentReview }) {
  const { t, lang } = useT()
  const period = review.children[0]?.period
  switch (review.comparison) {
    case 'matches':
      return (
        <span className="chip chip-paid">
          <CheckCircleIcon size={14} />
          {t('verify_matches', period ? formatShortMonth(period, lang) : '')}
        </span>
      )
    case 'short':
      return (
        <span className="chip chip-partial">
          <HalfCircleIcon size={14} />
          {t('verify_short', review.difference.format(), review.owedTogether.format())}
        </span>
      )
    case 'over':
      return (
        <span className="chip chip-due">
          <CircleIcon size={14} />
          {t('verify_over', review.difference.format(), review.owedTogether.format())}
        </span>
      )
  }
}
