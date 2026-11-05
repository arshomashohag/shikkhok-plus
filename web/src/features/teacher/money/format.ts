/** Formatting the money area needs that the shared formatters do not have. */
import type { Lang } from '../../../core/format'

/** "17 Oct, 4:52 pm" in Dhaka time, Western digits in both languages. */
export function formatDateTime(iso: string, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === 'bn' ? 'bn-BD-u-nu-latn' : 'en-GB', {
    timeZone: 'Asia/Dhaka',
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
    .format(new Date(iso))
    .replace(/\s?([AP]M)$/i, (_, m: string) => ` ${m.toLowerCase()}`)
}

/** The period Dhaka is in now, `YYYY-MM`. */
export function dhakaPeriod(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Dhaka',
    year: 'numeric',
    month: '2-digit',
  }).formatToParts(now)
  const year = parts.find((p) => p.type === 'year')?.value ?? '1970'
  const month = parts.find((p) => p.type === 'month')?.value ?? '01'
  return `${year}-${month}`
}

/** Move a `YYYY-MM` period by whole months. Calendar navigation, not money. */
export function shiftPeriod(period: string, by: number): string {
  const [y = '1970', m = '01'] = period.split('-')
  const index = Number.parseInt(y, 10) * 12 + (Number.parseInt(m, 10) - 1) + by
  const year = Math.floor(index / 12)
  const month = (index % 12) + 1
  return `${year}-${String(month).padStart(2, '0')}`
}

/** Whether a string is a `YYYY-MM` period the API will accept. */
export function isPeriod(value: string): boolean {
  return /^[0-9]{4}-(0[1-9]|1[0-2])$/.test(value)
}
