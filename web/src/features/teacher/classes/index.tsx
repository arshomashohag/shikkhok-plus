/** Classes area: Classes tab, Record a class (T2), attendance, schedule and batch editing. */
import { lazyComponent, lazyScreen } from '../../../core/lazy'
import type { BatchTabProps, TeacherRoute } from '../area'
import './classes.css'

export const ClassesTab = lazyComponent<BatchTabProps, typeof import('./ClassesTab')>(
  () => import('./ClassesTab'),
  'ClassesTab',
)

/** Patterns match `paths.session`, `paths.batchSchedule` and `paths.batchEdit`. */
export const classesRoutes: TeacherRoute[] = [
  {
    path: '/batches/:batchId/classes/:sessionId',
    element: lazyScreen(() => import('./SessionScreen'), 'SessionScreen'),
  },
  {
    path: '/batches/:batchId/schedule',
    element: lazyScreen(() => import('./ScheduleScreen'), 'ScheduleScreen'),
  },
  {
    path: '/batches/:batchId/edit',
    element: lazyScreen(() => import('./EditBatchScreen'), 'EditBatchScreen'),
  },
]
