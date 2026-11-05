/** "Continue as": shown once to someone holding more than one lens. */
import { useT } from '../../i18n/i18n'
import { useSession, type LensOption } from '../../session/session'

export function LensPicker({ options }: { options: LensOption[] }) {
  const { t } = useT()
  const { chooseLens } = useSession()
  return (
    <div className="auth-page">
      <div className="auth-card card">
        <div className="brand">
          <img src={`${import.meta.env.BASE_URL}icons/favicon.svg`} alt="" />
          <span>ShikkhokPlus</span>
        </div>
        <h1>{t('lens_picker_title')}</h1>
        <p className="meta">{t('lens_picker_subtitle')}</p>
        <ul className="list" style={{ marginTop: 16 }}>
          {options.map((o) => (
            <li key={o.lens}>
              <button type="button" className="row" onClick={() => chooseLens(o.lens)}>
                <span className="grow">
                  <span className="title">{t(`lens_${o.lens}`)}</span>
                  <br />
                  <span className="meta">{t(`lens_${o.lens}_count`, o.count)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
