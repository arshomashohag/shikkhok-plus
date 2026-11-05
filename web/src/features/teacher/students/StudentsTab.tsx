/**
 * T7 · Students tab. Moved out of BatchDetail so the students area owns
 * it. Fee chips load separately from names, as the design's Loading/Error
 * board draws: names still show when fee status could not load, and fee
 * status is hidden rather than shown out of date.
 */
import { readBatchFees, readRoster } from '../../../api/endpoints'
import { ApiError } from '../../../api/errors'
import { formatPhone } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { EmptyState, ErrorCard, FeeChip, Loading } from '../../../ui/components'
import type { BatchTabProps } from '../area'
import { mapRoster, type RosterSeat } from '../mappers'

interface Loaded {
  seats: RosterSeat[]
  feesError: ApiError | null
}

async function load(batchId: string): Promise<Loaded> {
  const [roster, fees] = await Promise.all([
    readRoster(batchId),
    readBatchFees(batchId).then(
      (f) => ({ ok: true as const, f }),
      (e: unknown) => ({ ok: false as const, e }),
    ),
  ])
  if (!fees.ok && !(fees.e instanceof ApiError)) throw fees.e
  return {
    seats: mapRoster(roster, fees.ok ? fees.f : null),
    feesError: fees.ok ? null : (fees.e as ApiError),
  }
}

export function StudentsTab({ batchId }: BatchTabProps) {
  const { t } = useT()
  const { resource, reload } = useResource(() => load(batchId), [batchId])

  if (resource.state === 'loading') return <Loading rows={5} />
  if (resource.state === 'failed') {
    return <ErrorCard title={t('batch_not_found')} error={resource.error} onRetry={reload} />
  }
  const { seats, feesError } = resource.data
  if (seats.length === 0) return <EmptyState title={t('roster_empty')} />
  return (
    <>
      {feesError ? (
        <div className="card error" role="status" style={{ marginBottom: 12 }}>
          <div className="title">{t('batch_fees_failed')}</div>
          <p className="meta">{t('batch_fees_failed_body')}</p>
          <button type="button" className="btn btn-outline" onClick={reload}>
            {t('auth_retry')}
          </button>
        </div>
      ) : null}
      <ul className="card flush list">
        {seats.map((s) => (
          <li key={s.enrollmentId} className="row">
            <div className="grow">
              <div className="title">{s.displayName}</div>
              <div className="meta">
                {s.guardianPhone
                  ? `${t('roster_link_guardian')} ${formatPhone(s.guardianPhone)}`
                  : t('roster_link_absent')}
                {s.status === 'inactive' ? ` · ${t('roster_status_inactive')}` : ''}
              </div>
            </div>
            {s.chip && !feesError ? <FeeChip chip={s.chip} /> : null}
          </li>
        ))}
      </ul>
    </>
  )
}
