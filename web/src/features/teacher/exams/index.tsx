/** Exams area: Exams tab, create exam, Marks entry (T3), review and publish, results. */
import { lazyComponent, lazyScreen } from '../../../core/lazy'
import type { BatchTabProps, TeacherRoute } from '../area'
import './exams.css'

export const ExamsTab = lazyComponent<BatchTabProps, typeof import('./ExamsTab')>(
  () => import('./ExamsTab'),
  'ExamsTab',
)

export const examsRoutes: TeacherRoute[] = [
  // Paths match `paths.examNew`, `paths.examMarks` and `paths.examResults`.
  {
    path: '/batches/:batchId/exams/new',
    element: lazyScreen(() => import('./ExamForm'), 'CreateExam'),
  },
  { path: '/exams/:examId/marks', element: lazyScreen(() => import('./MarkEntry'), 'MarkEntry') },
  {
    path: '/exams/:examId/results',
    element: lazyScreen(() => import('./ExamResults'), 'ExamResults'),
  },
]
