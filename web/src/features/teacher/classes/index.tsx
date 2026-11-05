/** Classes area: Classes tab, Record a class (T2), attendance, schedule and batch editing. */
import type { TeacherRoute } from '../area'
import { EditBatchScreen } from './EditBatchScreen'
import { ScheduleScreen } from './ScheduleScreen'
import { SessionScreen } from './SessionScreen'
import './classes.css'

export { ClassesTab } from './ClassesTab'

/** Patterns match `paths.session`, `paths.batchSchedule` and `paths.batchEdit`. */
export const classesRoutes: TeacherRoute[] = [
  { path: '/batches/:batchId/classes/:sessionId', element: <SessionScreen /> },
  { path: '/batches/:batchId/schedule', element: <ScheduleScreen /> },
  { path: '/batches/:batchId/edit', element: <EditBatchScreen /> },
]
