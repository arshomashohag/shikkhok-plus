/**
 * A centre teacher's own pay, read-only [D15]: their approved salary lines
 * at every centre, with bonuses, deductions and what has been paid. The
 * server returns only lines that pay this account.
 */
import { readMyPay } from '../../api/endpoints'
import { formatMonth } from '../../core/format'
import { useResource } from '../../core/useResource'
import { useT } from '../../i18n/i18n'
import { EmptyState, ErrorCard, Loading, Section, TopBar } from '../../ui/components'
import { SalaryCard } from '../teacher/centre/Payroll'

export function MyPay() {
  const { t, lang } = useT()
  const { resource, reload } = useResource(() => readMyPay(), [])
  let body: React.ReactNode
  if (resource.state === 'loading') body = <Loading rows={2} />
  else if (resource.state === 'failed')
    body = <ErrorCard title={t('my_pay_title')} error={resource.error} onRetry={reload} />
  else if (resource.data.length === 0)
    body = <EmptyState title={t('my_pay_title')} body={t('my_pay_empty')} />
  else
    body = resource.data.map((line) => (
      <Section key={line.line_id} title={`${formatMonth(line.period, lang)} · ${line.centre_name}`}>
        <SalaryCard line={line} />
      </Section>
    ))
  return (
    <>
      <TopBar title={t('my_pay_title')} />
      {body}
    </>
  )
}
