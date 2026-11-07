/**
 * Display formatting that is not money. Mirrors `core/format/*.kt`.
 *
 * **Western digits in both languages.** The design's numeral rule: phone
 * numbers, fees and marks read the same on a receipt, an SMS and the
 * screen, so Bangla text keeps Latin digits.
 */
import { toLatinDigits } from './money'

export type Lang = 'bn' | 'en'

const LOCAL_PHONE_LENGTH = 11

/** `8801711234567` or `01711234567` → `01711-234567`; else unchanged. */
export function formatPhone(raw: string): string {
  const digits = toLatinDigits(raw).replace(/\D/g, '')
  let local = digits.startsWith('880') ? digits.slice(3) : digits
  if (local.length === LOCAL_PHONE_LENGTH - 1 && !local.startsWith('0')) local = `0${local}`
  if (local.length !== LOCAL_PHONE_LENGTH) return raw
  return `${local.slice(0, 5)}-${local.slice(5)}`
}

/**
 * Normalise a typed phone number to the 11-digit local form, or null.
 * Client-side validation is **format only**; the server decides policy.
 */
export function normalisePhone(typed: string): string | null {
  const digits = toLatinDigits(typed).replace(/\D/g, '')
  const local = digits.startsWith('880') ? `0${digits.slice(3)}` : digits
  return /^01[0-9]{9}$/.test(local) ? local : null
}

/** A mark as the server sent it, without trailing zeros: 36.70 → 36.7. */
export function formatMark(value: number): string {
  // Marks are not money; the server sends them as JSON numbers with at
  // most two places. toFixed(2) then trimming is exact at that precision.
  return value.toFixed(2).replace(/\.?0+$/, '')
}

const dateFormatters = new Map<string, Intl.DateTimeFormat>()

function formatter(lang: Lang, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = lang + JSON.stringify(options)
  let f = dateFormatters.get(key)
  if (!f) {
    // `-u-nu-latn` keeps Western digits under the Bangla locale.
    f = new Intl.DateTimeFormat(lang === 'bn' ? 'bn-BD-u-nu-latn' : 'en-GB', {
      timeZone: 'Asia/Dhaka',
      ...options,
    })
    dateFormatters.set(key, f)
  }
  return f
}

/**
 * "17 Oct, 4:52 pm" in Dhaka time, Western digits in both languages;
 * "17 Oct 2026, 4:52 pm" with `withYear`, for dates that may be old.
 */
export function formatDateTime(iso: string, lang: Lang, withYear = false): string {
  return formatter(lang, {
    day: 'numeric',
    month: 'short',
    ...(withYear ? { year: 'numeric' } : {}),
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
    .format(new Date(iso))
    .replace(/\s?([AP]M)$/i, (_, m: string) => ` ${m.toLowerCase()}`)
}

/** "17 Oct 2026": the Dhaka calendar day of a timestamp. */
export function formatDayOf(iso: string, lang: Lang): string {
  return formatter(lang, { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(iso))
}

/** Parse a server `YYYY-MM-DD` as a calendar date (noon UTC, so no TZ drift). */
export function parseDate(isoDate: string): Date {
  return new Date(`${isoDate.slice(0, 10)}T12:00:00Z`)
}

/** "Saturday, 17 Oct". */
export function formatLongDay(isoDate: string, lang: Lang): string {
  return formatter(lang, { weekday: 'long', day: 'numeric', month: 'short' }).format(
    parseDate(isoDate),
  )
}

/** "17 Oct". */
export function formatShortDate(isoDate: string, lang: Lang): string {
  return formatter(lang, { day: 'numeric', month: 'short' }).format(parseDate(isoDate))
}

/** "October" from a period `2026-10` or a date. */
export function formatMonth(period: string, lang: Lang): string {
  return formatter(lang, { month: 'long' }).format(parseDate(`${period.slice(0, 7)}-15`))
}

/** "Oct" from a period. */
export function formatShortMonth(period: string, lang: Lang): string {
  return formatter(lang, { month: 'short' }).format(parseDate(`${period.slice(0, 7)}-15`))
}

/** A wall-clock `HH:MM[:SS]` as `{ time: "4:00", meridiem: "pm" }`. */
export function splitClock(hhmm: string, lang: Lang): { time: string; meridiem: string } {
  const [h = '0', m = '00'] = hhmm.split(':')
  const hour = Number.parseInt(h, 10)
  const twelve = hour % 12 === 0 ? 12 : hour % 12
  const pm = hour >= 12
  // "am"/"pm" in both languages, as Android's displayTime: the numeral
  // rule keeps clock times identical on a receipt, an SMS and the screen.
  void lang
  const meridiem = pm ? 'pm' : 'am'
  return { time: `${twelve}:${m.slice(0, 2)}`, meridiem }
}

/** "4:00 pm". */
export function formatClock(hhmm: string, lang: Lang): string {
  const { time, meridiem } = splitClock(hhmm, lang)
  return `${time} ${meridiem}`
}

/** The first letter of a name, for an avatar. Grapheme-aware for Bangla. */
export function initial(name: string): string {
  const trimmed = name.trim()
  if (!trimmed) return '?'
  const Segmenter = (Intl as { Segmenter?: typeof Intl.Segmenter }).Segmenter
  if (Segmenter) {
    const first = new Segmenter(undefined, { granularity: 'grapheme' }).segment(trimmed)
    for (const s of first) return s.segment
  }
  return trimmed.charAt(0)
}

/**
 * "2 h ago" since an ISO timestamp, with the Android app's own strings
 * (`time_*_ago`), so both clients say it the same way.
 *
 * @param t The translator from `useT()`
 */
export function ago(
  iso: string,
  now: Date,
  t: (key: string, ...args: (string | number)[]) => string,
): string {
  const minutes = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 60000))
  if (minutes < 1) return t('time_just_now')
  if (minutes < 60) return t('time_minutes_ago', minutes)
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return t('time_hours_ago', hours)
  return t('time_days_ago', Math.floor(hours / 24))
}

/**
 * "Today, 4:00 pm" or "Mon 19 Oct, 4:00 pm".
 *
 * "Today" is said only where the server sent a countdown, which it does
 * only for a class today; the client compares no dates (as `whenLabel`).
 */
export function whenLabel(
  next: { date: string; startTime: string; startsInMinutes: number | null },
  lang: Lang,
  t: (key: string, ...args: (string | number)[]) => string,
): string {
  const start = formatClock(next.startTime, lang)
  if (next.startsInMinutes !== null) return t('student_today_at', start)
  const day = formatter(lang, { weekday: 'short', day: 'numeric', month: 'short' }).format(
    parseDate(next.date),
  )
  return t('student_day_at', day, start)
}

/** "Next class · in 35 min" / "· in 2 h 5 min" / "Next class". */
export function howSoon(
  startsInMinutes: number | null,
  t: (key: string, ...args: (string | number)[]) => string,
): string {
  if (startsInMinutes === null) return t('student_next_class')
  if (startsInMinutes < 60) return t('student_next_in_min', startsInMinutes)
  return t('student_next_in_hours', Math.floor(startsInMinutes / 60), startsInMinutes % 60)
}
