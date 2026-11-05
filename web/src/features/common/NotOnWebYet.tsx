import { useT } from '../../i18n/i18n'
import { EmptyState } from '../../ui/components'

/** Said plainly, rather than a half-built screen. */
export function NotOnWebYet() {
  const { t } = useT()
  return <EmptyState title={t('web_not_on_web_title')} body={t('web_not_on_web_body')} />
}
