/** Date words the seat screens share. Western digits in both languages. */
import { formatClock, parseDate, type Lang } from '../../../core/format'

/** "Mon 19 Oct", as Android's `dayLabel`. */
export function dayLabel(isoDate: string, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === 'bn' ? 'bn-BD-u-nu-latn' : 'en-GB', {
    timeZone: 'Asia/Dhaka',
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(parseDate(isoDate))
}

/** "Mon". */
export function weekdayLabel(isoDate: string, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === 'bn' ? 'bn-BD-u-nu-latn' : 'en-GB', {
    timeZone: 'Asia/Dhaka',
    weekday: 'short',
  }).format(parseDate(isoDate))
}

/** "4:00–5:30 pm", dropping the first am/pm when both halves share it. */
export function timeRange(start: string, end: string | null, lang: Lang): string {
  const a = formatClock(start, lang)
  if (!end) return a
  const b = formatClock(end, lang)
  const [aTime, aHalf] = a.split(' ')
  const bHalf = b.split(' ')[1]
  return aHalf === bHalf ? `${aTime}–${b}` : `${a}–${b}`
}

/** "October 2026". */
export function monthTitle(year: number, month: number, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === 'bn' ? 'bn-BD-u-nu-latn' : 'en-GB', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, 15)))
}
