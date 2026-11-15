/**
 * Settings → Phone and email: the account's contacts, with Add, Replace
 * and Remove [FR8.1] [functional-spec W6].
 *
 * It renders `session.me`, the session's last read, and every write
 * re-reads through the session; it never edits its own copy. Remove is
 * offered for every present contact and Change actions stay enabled when
 * the account has no password — the note says a password is needed, and
 * the server's answer decides [FR11.3] [NFR3.13].
 */
import { useState } from 'react'
import { Link, useLocation } from 'react-router'
import { useT } from '../../../i18n/i18n'
import { useReadySession } from '../../../session/session'
import { TopBar } from '../../../ui/components'
import { securityPaths, type SettingsNotice } from '../security/paths'
import { contactCards, type ContactCard, type ContactKind } from './mappers'
import { RemoveContactSheet } from './RemoveContactSheet'

export function ContactsScreen() {
  const { t } = useT()
  const { session, refresh } = useReadySession()
  const arrived = (useLocation().state as SettingsNotice | null)?.notice ?? null
  /** The open Remove sheet, keyed per opening so it always starts fresh. */
  const [removing, setRemoving] = useState<{ card: ContactCard; opening: number } | null>(null)
  const [removed, setRemoved] = useState<ContactKind | null>(null)
  const [openings, setOpenings] = useState(0)
  const { me } = session

  function openRemove(card: ContactCard) {
    setOpenings((n) => n + 1)
    setRemoving({ card, opening: openings + 1 })
  }

  return (
    <>
      <TopBar title={t('contacts_title')} back="/settings" />
      {arrived ? (
        <div className="banner" role="status" style={{ marginBottom: 12 }}>
          {arrived}
        </div>
      ) : null}
      {me.has_password === false ? (
        <div
          className="banner info"
          data-testid="contacts-password-note"
          style={{ marginBottom: 12 }}
        >
          <span>
            {t('contacts_password_note')}{' '}
            <Link to={securityPaths.password()}>{t('contacts_set_password')}</Link>
          </span>
        </div>
      ) : null}
      {contactCards(me).map((card) => (
        <div className="card" key={card.kind} data-testid={`contact-card-${card.kind}`}>
          <p className="meta" style={{ marginTop: 0 }}>
            {t(card.kind === 'phone' ? 'contacts_phone' : 'contacts_email')}
          </p>
          <p className="title" style={{ overflowWrap: 'anywhere' }}>
            {card.contact ?? t(card.kind === 'phone' ? 'contacts_no_phone' : 'contacts_no_email')}
          </p>
          {removed === card.kind ? (
            <p className="meta" role="status">
              {t('contacts_removed')}
            </p>
          ) : null}
          <div className="button-row">
            {card.contact ? (
              <>
                <Link className="btn btn-outline" to={securityPaths.replaceContact(card.kind)}>
                  {t('contacts_replace')}
                </Link>
                <button type="button" className="btn btn-text" onClick={() => openRemove(card)}>
                  {t('contacts_remove')}
                </button>
              </>
            ) : (
              <Link className="btn btn-outline" to={securityPaths.addContact(card.kind)}>
                {t(card.kind === 'phone' ? 'web_contact_add_phone' : 'web_contact_add_email')}
              </Link>
            )}
          </div>
        </div>
      ))}
      {removing?.card.contact ? (
        <RemoveContactSheet
          key={removing.opening}
          kind={removing.card.kind}
          contact={removing.card.contact}
          onClose={() => setRemoving(null)}
          onRemoved={() => {
            setRemoved(removing.card.kind)
            setRemoving(null)
            refresh()
          }}
        />
      ) : null}
    </>
  )
}
