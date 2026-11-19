/**
 * A guardian's reviews [H4]: the batches they may review, are waiting to,
 * or have reviewed, each opening its review. And the entry to it on the
 * guardian home, drawn only while the server lists at least one batch:
 * with reviews switched off the list holds only what was already reviewed,
 * so a guardian who never wrote one sees no entry at all.
 */
import { Link } from 'react-router'
import { formatDayOf } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, StaleBanner, TopBar } from '../../../ui/components'
import { ChevronIcon } from '../../../ui/icons'
import { reviewPaths } from '../reader'
import { listReviewable } from './api'
import { REVIEWABLE_KEY } from './mappers'

/** Navigation state the list hands the editor: the batch's public title. */
export interface ReviewLinkState {
  title: string
}

/** The guardian home's "Reviews" row; nothing at all until the list has a row. */
export function ReviewsEntry() {
  const { t } = useT()
  const { resource } = useResource((signal) => listReviewable(signal), [])
  if (resource.state !== 'loaded' || resource.data.length === 0) return null
  return (
    <Link
      className="card card-link"
      to={reviewPaths.list()}
      style={{ display: 'flex', gap: 12, alignItems: 'center' }}
    >
      <div className="grow">
        <div className="title">{t('hub_reviews_title')}</div>
        <div className="meta">{t('hub_reviews_entry_guardian_sub')}</div>
      </div>
      <ChevronIcon />
    </Link>
  )
}

export function MyReviews() {
  const { t, lang } = useT()
  const { resource, reload } = useResource((signal) => listReviewable(signal), [])

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('hub_reviews_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0) body = <EmptyState title={t('hub_reviews_empty')} />
  else
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <ul className="card flush list" aria-label={t('hub_reviews_title')}>
          {resource.data.map((b) => (
            <li key={b.batch_id}>
              <Link
                className="row"
                to={reviewPaths.editor(b.batch_id)}
                state={{ title: b.batch_title } satisfies ReviewLinkState}
              >
                <div className="grow">
                  <div className="title">{b.batch_title}</div>
                  <div className="meta">{b.owner_public_name}</div>
                </div>
                <div className="end">
                  <span className="chip">{t(REVIEWABLE_KEY[b.state])}</span>
                  {b.eligible_from ? (
                    <span className="meta">
                      {t('hub_reviews_from', formatDayOf(b.eligible_from, lang))}
                    </span>
                  ) : null}
                </div>
                <ChevronIcon />
              </Link>
            </li>
          ))}
        </ul>
      </>
    )

  return (
    <>
      <TopBar title={t('hub_reviews_title')} back="/children" />
      {body}
    </>
  )
}
