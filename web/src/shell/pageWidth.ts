/**
 * How wide a screen's content may grow on a desktop window.
 *
 * The web boards draw three widths: dashboards and tables use the whole
 * content area; a form keeps a column a person can scan (Profile, Add
 * student); a page of reading — settings, the inbox, an invitation, one
 * fee history — sits in a column between the two (Invitations is drawn
 * at 960px). Decided here from the route, in one place, so a screen does
 * not each carry its own width.
 */
export type PageWidth = 'full' | 'reading' | 'form'

const SEAT = '(?:my|child)/[^/]+'

const FORM: RegExp[] = [
  /^\/batches\/new$/,
  /^\/batches\/[^/]+\/(?:edit|schedule)$/,
  /^\/batches\/[^/]+\/exams\/new$/,
  /^\/batches\/[^/]+\/students\/new$/,
  /^\/students\/new$/,
  /^\/payment-methods\/[^/]+$/,
  /^\/profile\/(?:edit|delete)$/,
  /^\/settings$/,
  new RegExp(`^/${SEAT}/pay$`),
]

const READING: RegExp[] = [
  /^\/more$/,
  /^\/invitations$/,
  /^\/inbox(?:\/[^/]+)?$/,
  /^\/profile\/children$/,
  /^\/payment-methods$/,
  /^\/seats\/[^/]+\/(?:fees|progress)$/,
  /^\/batches\/[^/]+\/students\/pick$/,
  new RegExp(`^/${SEAT}/(?:fees|progress|dashboard)$`),
  new RegExp(`^/${SEAT}/(?:classes|exams|notices)/[^/]+$`),
]

export function pageWidth(pathname: string): PageWidth {
  const path = pathname.replace(/\/+$/, '') || '/'
  if (FORM.some((r) => r.test(path))) return 'form'
  if (READING.some((r) => r.test(path))) return 'reading'
  return 'full'
}
