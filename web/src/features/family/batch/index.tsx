/**
 * Batch & results area: the seat's batch (S2 / ChildBatch), one class, one
 * exam, its marksheet, one notice, and progress (G3) — each written once
 * and mounted for both readers (`/my/:seat/...`, `/child/:seat/...`).
 */
import type { FamilyRoute } from '../area'
import './batch.css'
import { ClassDetail, ExamDetail, MarksheetScreen, NoticeDetail } from './Details'
import { ProgressScreen } from './Progress'
import { SeatBatch } from './SeatBatch'

export const batchRoutes: FamilyRoute[] = [
  { path: '', element: (reader) => <SeatBatch reader={reader} /> },
  { path: 'classes/:sessionId', element: (reader) => <ClassDetail reader={reader} /> },
  { path: 'exams/:examId', element: (reader) => <ExamDetail reader={reader} /> },
  { path: 'exams/:examId/marksheet', element: (reader) => <MarksheetScreen reader={reader} /> },
  { path: 'notices/:noticeId', element: (reader) => <NoticeDetail reader={reader} /> },
  { path: 'progress', element: (reader) => <ProgressScreen reader={reader} /> },
]
