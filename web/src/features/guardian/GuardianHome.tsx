/**
 * G1 · Guardian home. A child switcher pinned at the top, then that
 * child's next payment, payments being checked, latest results and
 * batches.
 *
 * **One child at a time, and the selected child's name is in every card
 * title**, so a guardian of two never reads one child's marks as the
 * other's. Switching is instant because the server sent every child's
 * summary in one response; nothing is fetched or computed per child.
 */
import { useState } from 'react'
import { Link } from 'react-router'
import { familyPaths } from '../family/reader'
import { readGuardianHome, type Schemas } from '../../api/endpoints'
import { formatMark, formatMonth, formatPhone, formatShortDate, initial } from '../../core/format'
import { Money } from '../../core/money'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { useReadySession } from '../../session/session'
import {
  Avatar,
  ErrorCard,
  FeeChip,
  Loading,
  Section,
  StaleBanner,
  TopBar,
} from '../../ui/components'
import { ChevronIcon, WarningIcon } from '../../ui/icons'

type Child = Schemas['ChildSummaryResponse']

export function GuardianHome() {
  const { t } = useT()
  const { session } = useReadySession()
  const { resource, reload } = useResource(() => readGuardianHome(), [])
  const [selected, setSelected] = useState<string | null>(null)

  if (resource.state === 'loading') {
    return (
      <>
        <TopBar title={t('guardian_home_title')} />
        <Loading rows={3} />
      </>
    )
  }
  if (resource.state === 'failed') {
    return (
      <>
        <TopBar title={t('guardian_home_title')} />
        <ErrorCard title={t('guardian_home_title')} error={resource.error} onRetry={reload} />
      </>
    )
  }

  const children = resource.data.children ?? []
  if (children.length === 0) {
    const phone = session.me.phone ? formatPhone(session.me.phone) : null
    return (
      <>
        <TopBar title="ShikkhokPlus" />
        <div className="card">
          <h2 style={{ marginTop: 0, fontSize: '1.125rem' }}>{t('guardian_none_title')}</h2>
          <p className="meta">{t('guardian_empty_body')}</p>
          {phone ? <div className="hero-amount">{phone}</div> : null}
        </div>
      </>
    )
  }

  const child = children.find((c) => c.key === selected) ?? children[0]
  if (!child) return null
  return (
    <>
      <TopBar title={t('guardian_home_title')} />
      {children.length > 1 ? (
        <div
          className="segmented"
          role="group"
          aria-label={t('guardian_switch_label')}
          style={{ marginBottom: 16 }}
        >
          {children.map((c) => (
            <button
              key={c.key}
              type="button"
              aria-pressed={c.key === child.key}
              onClick={() => setSelected(c.key)}
            >
              {c.display_name}
            </button>
          ))}
        </div>
      ) : null}
      {resource.error ? <StaleBanner error={resource.error} loadedAt={resource.loadedAt} /> : null}
      <ChildView child={child} />
    </>
  )
}

function ChildView({ child }: { child: Child }) {
  const { t, lang } = useT()
  const name = child.display_name
  const pay = child.next_payment ?? null

  return (
    <div aria-live="polite">
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', margin: '4px 0 16px' }}>
        <Avatar letter={initial(name)} primary />
        <div>
          <div className="title" style={{ fontSize: '1.25rem' }}>
            {name}
          </div>
          <div className="meta">
            {child.batch_count === 1
              ? t('guardian_one_batch')
              : t('guardian_batch_count', child.batch_count)}
          </div>
        </div>
      </div>

      {pay ? (
        <div className="card">
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              gap: 8,
              alignItems: 'center',
            }}
          >
            <span className="label">{t('guardian_next_payment', name)}</span>
            {pay.days_late !== null && pay.days_late !== undefined ? (
              <span className="chip chip-overdue">
                <WarningIcon size={14} />
                {t('guardian_days_late', pay.days_late)}
              </span>
            ) : null}
          </div>
          <div className="hero-amount">{Money.fromWire(pay.amount_due).format()}</div>
          <div className="meta">
            {[
              pay.batch_name,
              formatMonth(pay.period, lang),
              pay.due_date ? t('guardian_due_on', formatShortDate(pay.due_date, lang)) : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </div>
          {pay.later_periods > 0 ? (
            <div className="meta">
              {t('guardian_more_owed', pay.later_periods, Money.fromWire(pay.total_due).format())}
            </div>
          ) : null}
          {/* G1: Pay opens the child's payments first, as on Android; that
              screen offers Send money. */}
          <div className="button-row">
            <Link
              className="btn btn-primary btn-money"
              to={familyPaths.payments('child', pay.enrollment_id)}
            >
              {t('guardian_pay_amount', Money.fromWire(pay.amount_due).format())}
            </Link>
          </div>
        </div>
      ) : null}

      {(child.waiting ?? []).map((w, i) => (
        <Link
          key={i}
          className="card card-link"
          to={familyPaths.payments(
            'child',
            pay?.enrollment_id ?? child.batches?.[0]?.enrollment_id ?? '',
          )}
          style={{ display: 'flex', gap: 12, alignItems: 'center' }}
        >
          <div className="grow">
            <div className="title">
              {w.batch_name} · {formatMonth(w.period, lang)}
            </div>
            <div className="amount">{Money.fromWire(w.amount).format()}</div>
            {w.submitted_at ? (
              <div className="meta">
                {t('guardian_sent_checking', formatShortDate(w.submitted_at, lang))}
              </div>
            ) : null}
          </div>
          <FeeChip chip={{ kind: 'verifying', amount: null }} />
        </Link>
      ))}

      <Section title={t('guardian_latest_results', name)}>
        {(child.latest_results ?? []).length === 0 ? (
          <div className="card meta">{t('student_results_empty')}</div>
        ) : (
          <ul className="card flush list">
            {(child.latest_results ?? []).map((r, i) => (
              <li key={i}>
                <Link className="row" to={familyPaths.progress('child', r.enrollment_id)}>
                  <div className="grow">
                    <div className="title">{r.batch_name}</div>
                    <div className="meta">
                      {r.title} · {formatShortDate(r.date, lang)}
                    </div>
                  </div>
                  <div className="end">
                    <span>
                      <strong style={{ fontSize: '1.25rem' }}>{formatMark(r.marks)}</strong>
                      {t('student_out_of', r.total_marks)}
                    </span>
                    <span className="meta">{trendLine(r, t)}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={t('guardian_batches_of', name)}>
        <ul className="card flush list">
          {(child.batches ?? []).map((b) => (
            <li key={b.enrollment_id}>
              <Link className="row" to={familyPaths.batch('child', b.enrollment_id)}>
                <div className="grow">
                  <div className="title">{b.batch_name}</div>
                  <div className="meta">{b.teacher_display_name ?? ''}</div>
                </div>
                <ChevronIcon />
              </Link>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  )
}

/** The server says which way it went; the client only words it. */
function trendLine(
  r: Schemas['ChildResultResponse'],
  t: (key: string, ...args: (string | number)[]) => string,
): string {
  const previous =
    r.previous_marks === null || r.previous_marks === undefined
      ? null
      : formatMark(r.previous_marks)
  switch (r.trend) {
    case 'up':
      return previous ? t('guardian_up_from', previous) : ''
    case 'down':
      return previous ? t('guardian_down_from', previous) : ''
    case 'same':
      return t('guardian_same_as_last')
    case 'first':
      return t('guardian_first_test')
  }
}
