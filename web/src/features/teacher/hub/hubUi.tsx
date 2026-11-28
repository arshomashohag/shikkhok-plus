/** Small pieces the hub screens share: failure text, the status chip and a checklist. */
import { Link } from 'react-router'
import { listBatchListings, readHubPageViews, readOwnerReviews } from '../../../api/endpoints'
import { listOwnerEnquiries } from './enquiries.api'
import { ApiError } from '../../../api/errors'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { CheckCircleIcon, CircleIcon, WarningIcon } from '../../../ui/icons'
import {
  checklistLabelKey,
  STATUS_CHIP,
  STATUS_KEY,
  type ChecklistItem,
  type ListingStatus,
} from './hub.mappers'
import { paths } from '../paths'

type T = (key: string, ...args: (string | number)[]) => string

/** The sentence for a failed call: offline, or the message the server named. */
export function failureText(e: unknown, t: T, message: (k: string) => string): string {
  const error = e instanceof ApiError ? e : null
  return error?.offline
    ? t('web_money_offline_nothing_changed')
    : message(error?.messageKey ?? 'error.unexpected')
}

export function StatusChip({ status }: { status: ListingStatus }) {
  const { t } = useT()
  return <span className={`chip ${STATUS_CHIP[status]}`}>{t(STATUS_KEY[status])}</span>
}

/** The server's checklist, each item with its state in words and an icon. */
export function Checklist({ items }: { items: ChecklistItem[] }) {
  const { t } = useT()
  return (
    <ul className="list" aria-label={t('web_hub_checklist_title')}>
      {items.map((i) => (
        <li key={i.key}>
          <div className="row">
            {i.done ? <CheckCircleIcon /> : <CircleIcon />}
            <span className="grow">{t(checklistLabelKey(i.key) ?? i.key)}</span>
            <span className="meta">
              {i.done ? t('web_hub_check_done') : t('web_hub_check_todo')}
            </span>
          </div>
        </li>
      ))}
    </ul>
  )
}

/** A failure banner with an optional retry that repeats the same call. */
export function FailureBanner({ text, onRetry }: { text: string; onRetry?: () => void }) {
  const { t } = useT()
  return (
    <div className="banner error" role="alert">
      <WarningIcon />
      <span className="grow">{text}</span>
      {onRetry ? (
        <button type="button" className="btn btn-text btn-small" onClick={onRetry}>
          {t('web_hub_retry')}
        </button>
      ) : null}
    </div>
  )
}

/** The switch is off: the reviews screens draw nothing, not an error [H4]. */
export function isReviewsOff(e: unknown): boolean {
  return e instanceof ApiError && e.code === 'HUB_REVIEWS_OFF'
}

/**
 * The listing editor's way to the Reviews screen, drawn only once
 * `GET /v1/hub/reviews` has answered: with reviews switched off, or on any
 * failure, there is no entry and no error.
 */
export function OwnerReviewsEntry() {
  const { t } = useT()
  const { resource } = useResource((signal) => readOwnerReviews(signal), [])
  if (resource.state !== 'loaded') return null
  return (
    <Link
      className="card card-link"
      to={paths.hubReviews()}
      style={{ display: 'flex', gap: 12, alignItems: 'center' }}
    >
      <div className="grow">
        <div className="title">{t('hub_reviews_title')}</div>
        <div className="meta">{t('hub_reviews_entry_owner_sub')}</div>
      </div>
    </Link>
  )
}

/**
 * The listing editor's way to the join-request inbox [H5], drawn only once
 * `GET /v1/hub/enquiries` has answered: with join requests switched off
 * (`HUB_ENQUIRIES_OFF`), or on any failure, there is no row and no error.
 */
export function OwnerEnquiriesEntry() {
  const { t } = useT()
  const { resource } = useResource((signal) => listOwnerEnquiries(signal), [])
  if (resource.state !== 'loaded') return null
  return (
    <Link
      className="card card-link"
      to={paths.hubEnquiries()}
      style={{ display: 'flex', gap: 12, alignItems: 'center' }}
    >
      <div className="grow">
        <div className="title">{t('hub_enquiry_inbox_title')}</div>
        <div className="meta">{t('hub_enquiry_inbox_sub')}</div>
      </div>
    </Link>
  )
}

/**
 * How often the owner's public pages were opened [0050], shown only once the
 * listing is published. Counts of loads, not of people, and the card says
 * so; any failure draws nothing, since the counts are never needed to act.
 * Batch pages are named by the owner's own batch name, beside their counts.
 */
export function OwnerPageViews() {
  const { t } = useT()
  const { resource } = useResource(async (signal) => {
    const [views, batches] = await Promise.all([
      readHubPageViews(signal),
      listBatchListings(signal),
    ])
    return { views, batches }
  }, [])
  if (resource.state !== 'loaded') return null
  const { views, batches } = resource.data
  const names = new Map(batches.map((b) => [b.batch_id, b.batch_name]))
  return (
    <section className="card" aria-labelledby="hub-page-views">
      <div className="title" id="hub-page-views">
        {t('web_hub_views_title')}
      </div>
      <p className="meta">{t('web_hub_views_explain')}</p>
      <ul className="list">
        <li>
          <div className="row">
            <span className="grow">{t('web_hub_views_owner_page')}</span>
            <span className="meta">
              {t(
                'web_hub_views_counts',
                views.owner_page.last_7_days,
                views.owner_page.last_30_days,
              )}
            </span>
          </div>
        </li>
        {views.batches.map((b) => (
          <li key={b.batch_id}>
            <div className="row">
              <span className="grow" style={{ overflowWrap: 'anywhere' }}>
                {names.get(b.batch_id) ?? t('web_hub_views_batch_gone')}
              </span>
              <span className="meta">
                {t('web_hub_views_counts', b.last_7_days, b.last_30_days)}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
