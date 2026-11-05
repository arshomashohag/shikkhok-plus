/**
 * Every teacher URL, in one place, so the areas built separately (classes,
 * exams, students, money) link to each other by function rather than by
 * a string typed twice. An area that owns a path registers its route in
 * `<area>/index.tsx`; anyone may link to it from here.
 */
export type BatchTab = 'students' | 'classes' | 'exams' | 'notices'

const id = (s: string) => encodeURIComponent(s)

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

  // money/
  payment: (submissionId: string) => `/verify/${id(submissionId)}`,
  seatFees: (enrollmentId: string) => `/seats/${id(enrollmentId)}/fees`,
  paymentMethods: () => '/payment-methods',
  paymentMethodNew: (kind: 'mobile' | 'bank') => `/payment-methods/new?kind=${kind}`,
  paymentMethodEdit: (methodId: string) => `/payment-methods/${id(methodId)}`,
  collections: () => '/collections',
  batchMonth: (batchId: string, period: string) => `/batches/${id(batchId)}/month/${id(period)}`,
} as const
