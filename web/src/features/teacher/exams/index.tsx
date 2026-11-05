/** Exams area: Exams tab, create exam, Marks entry (T3), review and publish, results. */
import type { TeacherRoute } from '../area'
import { CreateExam } from './ExamForm'
import { ExamResults } from './ExamResults'
import { MarkEntry } from './MarkEntry'
import './exams.css'

export { ExamsTab } from './ExamsTab'

export const examsRoutes: TeacherRoute[] = [
  // Paths match `paths.examNew`, `paths.examMarks` and `paths.examResults`.
  { path: '/batches/:batchId/exams/new', element: <CreateExam /> },
  { path: '/exams/:examId/marks', element: <MarkEntry /> },
  { path: '/exams/:examId/results', element: <ExamResults /> },
]
