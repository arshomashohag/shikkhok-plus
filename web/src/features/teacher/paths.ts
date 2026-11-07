/**
 * Every teacher URL, in one place, so the areas built separately (classes,
 * exams, students, money) link to each other by function rather than by
 * a string typed twice. An area that owns a path registers its route in
 * `<area>/index.tsx`; anyone may link to it from here.
 */
export type BatchTab = 'students' | 'classes' | 'exams' | 'notices'

const id = (s: string) => encodeURIComponent(s)

/** The names a seat screen shows under its title. */
export interface SeatNames {
  name?: string
  batch?: string
}

/**
 * Seat screens are handed the student's and batch's names, because no
 * seat response carries them (Android passes them as route arguments for
 * the same reason). They travel in navigation state, never in the URL: a
 * child's name in a query string lands in browser history, in server and
 * CDN access logs and in anything the link is pasted into, and a crafted
 * link could put any text under a seat's real figures. Pass this as a
 * Link's or navigate's `state`.
 */
export function seatState(name?: string, batch?: string): { seatNames: SeatNames } {
  return { seatNames: { name: name || undefined, batch: batch || undefined } }
}

/**
 * The names from navigation state, if this screen was opened from a link
 * that sent them. Opened any other way (a pasted link, a bookmark) there
 * are none and the screen shows its plain title: nothing is read from the
 * URL for display.
 */
export function readSeatNames(state: unknown): SeatNames {
  const names = (state as { seatNames?: unknown } | null)?.seatNames
  if (typeof names !== 'object' || names === null) return {}
  const { name, batch } = names as Record<string, unknown>
  return {
    name: typeof name === 'string' && name ? name : undefined,
    batch: typeof batch === 'string' && batch ? batch : undefined,
  }
}

export const paths = {
  today: () => '/today',
  batches: () => '/batches',
  batch: (batchId: string, tab?: BatchTab) => `/batches/${id(batchId)}${tab ? `?tab=${tab}` : ''}`,
  dues: () => '/dues',
  verify: () => '/verify',

  // classes/
  session: (batchId: string, sessionId: string) =>
    `/batches/${id(batchId)}/classes/${id(sessionId)}`,
  batchSchedule: (batchId: string) => `/batches/${id(batchId)}/schedule`,
  batchEdit: (batchId: string) => `/batches/${id(batchId)}/edit`,

  // exams/
  examNew: (batchId: string) => `/batches/${id(batchId)}/exams/new`,
  examMarks: (examId: string) => `/exams/${id(examId)}/marks`,
  examResults: (examId: string) => `/exams/${id(examId)}/results`,

  // students/
  studentAdd: (batchId: string) => `/batches/${id(batchId)}/students/new`,

  // people/ -- a teacher's students, apart from any batch [0018]
  students: () => '/students',
  studentNew: (batchId?: string) =>
    batchId ? `/students/new?batch=${id(batchId)}` : '/students/new',
  studentDetail: (studentId: string) => `/students/${id(studentId)}`,
  pickStudents: (batchId: string) => `/batches/${id(batchId)}/students/pick`,

  // money/
  payment: (submissionId: string) => `/verify/${id(submissionId)}`,
  // With seatState(name, batch) as the link's state; see above.
  seatFees: (enrollmentId: string) => `/seats/${id(enrollmentId)}/fees`,
  seatProgress: (enrollmentId: string) => `/seats/${id(enrollmentId)}/progress`,
  paymentMethods: () => '/payment-methods',
  extraFees: (batchId: string) => `/batches/${id(batchId)}/fees`,
  extraFeeNew: (batchId: string) => `/batches/${id(batchId)}/fees/new`,
  extraFee: (feeId: string) => `/extra-fees/${id(feeId)}`,
  paymentMethodNew: (kind: 'mobile' | 'bank') => `/payment-methods/new?kind=${kind}`,
  paymentMethodEdit: (methodId: string) => `/payment-methods/${id(methodId)}`,
  collections: () => '/collections',
  expenses: () => '/expenses',
  moneySummary: () => '/money-summary',
  centreMembers: () => '/centre-members',
  centreStaff: () => '/centre-staff',
  centreTimetable: () => '/centre-timetable',
  centrePayroll: () => '/centre-payroll',
  batchMonth: (batchId: string, period: string) => `/batches/${id(batchId)}/month/${id(period)}`,
} as const
