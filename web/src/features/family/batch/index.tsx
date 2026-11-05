/**
 * Batch & results area: the seat's batch (S2 / ChildBatch), one class, one
 * exam, its marksheet, one notice, progress (G3) and the dashboard — each
 * written once and mounted for both readers (`/my/:seat/...`,
 * `/child/:seat/...`). Every screen loads on first use.
 */
import { lazyComponent } from '../../../core/lazy'
import type { FamilyRoute } from '../area'
import type { Reader } from '../reader'
import './batch.css'

type ReaderProps = { reader: Reader }
const details = () => import('./Details')

const SeatBatch = lazyComponent<ReaderProps, typeof import('./SeatBatch')>(
  () => import('./SeatBatch'),
  'SeatBatch',
)
const ClassDetail = lazyComponent<ReaderProps, typeof import('./Details')>(details, 'ClassDetail')
const ExamDetail = lazyComponent<ReaderProps, typeof import('./Details')>(details, 'ExamDetail')
const MarksheetScreen = lazyComponent<ReaderProps, typeof import('./Details')>(
  details,
  'MarksheetScreen',
)
const NoticeDetail = lazyComponent<ReaderProps, typeof import('./Details')>(details, 'NoticeDetail')
const ProgressScreen = lazyComponent<ReaderProps, typeof import('./Progress')>(
  () => import('./Progress'),
  'ProgressScreen',
)
const FamilyDashboard = lazyComponent<ReaderProps, typeof import('./Dashboard')>(
  () => import('./Dashboard'),
  'FamilyDashboard',
)

export const batchRoutes: FamilyRoute[] = [
  { path: '', element: (reader) => <SeatBatch reader={reader} /> },
  { path: 'classes/:sessionId', element: (reader) => <ClassDetail reader={reader} /> },
  { path: 'exams/:examId', element: (reader) => <ExamDetail reader={reader} /> },
  { path: 'exams/:examId/marksheet', element: (reader) => <MarksheetScreen reader={reader} /> },
  { path: 'notices/:noticeId', element: (reader) => <NoticeDetail reader={reader} /> },
  { path: 'progress', element: (reader) => <ProgressScreen reader={reader} /> },
  { path: 'dashboard', element: (reader) => <FamilyDashboard reader={reader} /> },
]
