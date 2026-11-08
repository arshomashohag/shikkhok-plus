/**
 * My children (guardian): every child a teacher linked to this number, as
 * the server groups them, with each child's batches. A guardian never adds
 * a child here: the teacher records the guardian's number, so the card at
 * the bottom says how a missing child appears.
 */
import { Link } from 'react-router'
import { formatPhone, initial } from '../../../core/format'
import { useResource } from '../../../core/useResource'
import { useT } from '../../../i18n/i18n'
import { useReadySession } from '../../../session/session'
import { Avatar, ErrorCard, Loading, StaleBanner, TopBar } from '../../../ui/components'
import { ChevronIcon } from '../../../ui/icons'
import { familyPaths } from '../../family/reader'
import { readGuardianHome } from './api'
import { mapChildren } from './mappers'
import { securityPaths } from '../security/paths'
import './account.css'

export function MyChildren() {
  const { t } = useT()
  const { session } = useReadySession()
  const { resource, reload } = useResource(
    (signal) => readGuardianHome(signal).then(mapChildren),
    [],
  )
  const phone = session.me.phone ? formatPhone(session.me.phone) : null

  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={3} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('my_children_title')} error={resource.error} onRetry={reload} />
  else
    body = (
      <>
        {resource.error ? (
          <StaleBanner error={resource.error} loadedAt={resource.loadedAt} />
        ) : null}
        <p className="meta">{t('my_children_note')}</p>
        {resource.data.length === 0 ? (
          <div className="card meta">{t('guardian_children_empty')}</div>
        ) : (
          <div className="grid-2">
            {resource.data.map((child) => (
              <article key={child.key} className="card" aria-label={child.name}>
                <div className="account-child">
                  <Avatar letter={initial(child.name)} primary />
                  <div>
                    <div className="title">{child.name}</div>
                    <div className="meta">
                      {child.batchCount === 1
                        ? t('guardian_one_batch')
                        : t('guardian_batch_count', child.batchCount)}
                    </div>
                  </div>
                </div>
                <ul className="list account-child-batches">
                  {child.batches.map((b) => (
                    <li key={b.enrollmentId}>
                      <Link className="row" to={familyPaths.batch('child', b.enrollmentId)}>
                        <span className="grow">
                          <span className="title">{b.batchName}</span>
                          {b.teacherName ? (
                            <>
                              <br />
                              <span className="meta">{b.teacherName}</span>
                            </>
                          ) : null}
                        </span>
                        <ChevronIcon />
                      </Link>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        )}
        <div className="card" style={{ marginTop: 12 }}>
          <div className="title">{t('my_children_missing_title')}</div>
          <p className="meta" style={{ marginBottom: 0 }}>
            {phone ? t('my_children_missing_body', phone) : t('my_children_missing_body_plain')}
          </p>
          {session.me.phone === null ? (
            // An email-only guardian: teachers find guardians by number.
            <div className="button-row">
              <Link className="btn btn-tonal btn-small" to={securityPaths.addContact('phone')}>
                {t('web_contact_add_phone')}
              </Link>
            </div>
          ) : null}
        </div>
      </>
    )

  return (
    <>
      <TopBar title={t('my_children_title')} back="/more" />
      {body}
    </>
  )
}
