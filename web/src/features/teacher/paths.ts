/**
 * Every teacher URL, in one place, so the areas built separately (classes,
 * exams, students, money) link to each other by function rather than by
 * a string typed twice. An area that owns a path registers its route in
 * `<area>/index.tsx`; anyone may link to it from here.
 */
export type BatchTab = 'students' | 'classes' | 'exams' | 'notices'

const id = (s: string) => encodeURIComponent(s)

/**
 * Seat screens take the student's and batch's names as query parameters,
 * because no seat response carries them (Android passes them as route
 * arguments for the same reason). Optional: an id alone still opens it.
 */
function withNames(base: string, name?: string, batch?: string): string {
  const q = new URLSearchParams()
  if (name) q.set('name', name)
  if (batch) q.set('batch', batch)
  const s = q.toString()
  return s ? `${base}?${s}` : base
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
  seatFees: (enrollmentId: string, name?: string, batch?: string) =>
    withNames(`/seats/${id(enrollmentId)}/fees`, name, batch),
  seatProgress: (enrollmentId: string, name?: string, batch?: string) =>
    withNames(`/seats/${id(enrollmentId)}/progress`, name, batch),
  paymentMethods: () => '/payment-methods',
  extraFees: (batchId: string) => `/batches/${id(batchId)}/fees`,
  extraFeeNew: (batchId: string) => `/batches/${id(batchId)}/fees/new`,
  extraFee: (feeId: string) => `/extra-fees/${id(feeId)}`,
  paymentMethodNew: (kind: 'mobile' | 'bank') => `/payment-methods/new?kind=${kind}`,
  paymentMethodEdit: (methodId: string) => `/payment-methods/${id(methodId)}`,
  collections: () => '/collections',
  expenses: () => '/expenses',
  moneySummary: () => '/money-summary',
  batchMonth: (batchId: string, period: string) => `/batches/${id(batchId)}/month/${id(period)}`,
} as const
