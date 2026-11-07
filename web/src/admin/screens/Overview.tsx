/**
 * The platform at a glance. Every figure is an aggregate the server
 * computed; nothing here counts, compares or derives a figure, except
 * the width of a bar, and the number beside the bar is always written.
 */
import { formatDateTime } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { Loading, Section, StaleBanner } from '../../ui/components'
import { readOverview } from './api'
import { AdminFailure, AdminFrame, Stat } from './AdminFrame'
import { formatCount, PLATFORM_KEY, platformUsage, share } from './mappers'
import { adminPaths } from './paths'

export function AdminOverview() {
  const { t, lang } = useT()
  const { resource, reload } = useResource(() => readOverview(), [])

  if (resource.state === 'loading')
    return (
      <AdminFrame tab="overview">
        <Loading rows={4} />
      </AdminFrame>
    )
  if (resource.state === 'failed')
    return (
      <AdminFailure
        tab="overview"
        title={t('web_admin_tab_overview')}
        error={resource.error}
        onRetry={reload}
      />
    )

  const o = resource.data
  const n = formatCount
  return (
    <AdminFrame
      tab="overview"
      subtitle={t('web_admin_generated', formatDateTime(o.generated_at, lang, true))}
    >
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}
      <p className="meta admin-note">{t('web_admin_privacy_note')}</p>

      <Section title={t('web_admin_section_accounts')}>
        <div className="admin-stats">
          <Stat
            label={t('web_admin_accounts')}
            value={n(o.accounts)}
            sub={t('web_admin_accounts_sub')}
          />
          <Stat label={t('web_admin_active_7')} value={n(o.active_7_days)} />
          <Stat label={t('web_admin_active_30')} value={n(o.active_30_days)} />
          <Stat label={t('web_admin_new_7')} value={n(o.new_7_days)} />
          <Stat label={t('web_admin_new_30')} value={n(o.new_30_days)} />
        </div>
      </Section>

      <Section title={t('web_admin_section_roles')}>
        <div className="admin-stats">
          <Stat
            label={t('web_admin_role_teachers')}
            value={n(o.teachers)}
            sub={t('web_admin_role_teachers_sub')}
          />
          <Stat label={t('web_admin_role_centres')} value={n(o.centres)} />
          <Stat
            label={t('web_admin_role_centre_members')}
            value={n(o.centre_members)}
            sub={t('web_admin_role_centre_members_sub')}
          />
          <Stat
            label={t('web_admin_role_students')}
            value={n(o.students)}
            sub={t('web_admin_role_count_sub')}
          />
          <Stat
            label={t('web_admin_role_guardians')}
            value={n(o.guardians)}
            sub={t('web_admin_role_count_sub')}
          />
        </div>
      </Section>

      <Section title={t('web_admin_section_platforms')}>
        <div className="card">
          {platformUsage(o).map((p) => (
            <div key={p.platform} className="admin-platform">
              <div className="admin-platform-head">
                <span className="title">{t(PLATFORM_KEY[p.platform])}</span>
                <span className="meta">
                  {t('web_admin_platform_accounts', n(p.accounts), n(o.accounts))}
                </span>
              </div>
              <div className={`admin-bar ${p.platform}`} aria-hidden="true">
                <span style={{ width: `${share(p.accounts, o.accounts)}%` }} />
              </div>
              <span className="meta">
                {t('web_admin_platform_active', n(p.active7), n(p.active30))}
              </span>
            </div>
          ))}
          <dl className="kv admin-kv">
            <dt>{t('web_admin_both')}</dt>
            <dd>{n(o.both_platforms)}</dd>
            <dt>{t('web_admin_not_reported')}</dt>
            <dd>
              {n(o.no_platform)}
              <span className="help">{t('web_admin_not_reported_help')}</span>
            </dd>
          </dl>
        </div>
      </Section>

      <div className="dash dash-2 admin-pair">
        <Section title={t('web_admin_section_versions')}>
          <div className="card flush">
            {o.versions.length === 0 ? (
              <p className="meta admin-empty-line">{t('web_admin_no_versions')}</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">{t('web_admin_col_app')}</th>
                      <th scope="col">{t('web_admin_col_version')}</th>
                      <th scope="col" className="num">
                        {t('web_admin_col_accounts')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {o.versions.map((v) => (
                      <tr key={`${v.platform}-${v.version}`}>
                        <td>{t(PLATFORM_KEY[v.platform])}</td>
                        <td className="mono">{v.version}</td>
                        <td className="num">{n(v.accounts)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Section>
        <Section title={t('web_admin_section_teaching')}>
          <div className="admin-stats two">
            <Stat label={t('web_admin_batches')} value={n(o.batches)} />
            <Stat label={t('web_admin_seats')} value={n(o.seats)} />
          </div>
        </Section>
      </div>

      <Section title={t('web_admin_section_help')}>
        <div className="admin-stats three">
          <Stat
            label={t('web_admin_status_open')}
            value={n(o.help_open)}
            sub={t('web_admin_status_open_sub')}
            to={adminPaths.tickets({ status: 'open' })}
          />
          <Stat
            label={t('web_admin_status_answered')}
            value={n(o.help_answered)}
            sub={t('web_admin_status_answered_sub')}
            to={adminPaths.tickets({ status: 'answered' })}
          />
          <Stat
            label={t('web_admin_status_closed')}
            value={n(o.help_closed)}
            sub={t('web_admin_status_closed_sub')}
            to={adminPaths.tickets({ status: 'closed' })}
          />
        </div>
      </Section>
    </AdminFrame>
  )
}
