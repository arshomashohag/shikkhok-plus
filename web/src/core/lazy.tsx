/**
 * Load a screen's code the first time it is opened.
 *
 * The teacher, student and guardian areas are each a separate chunk, so
 * a student's phone never downloads the marks-entry screen, and the first
 * paint carries only the shell and the screen being opened. The fallback
 * is the static skeleton every screen already uses while it loads data,
 * so a slow chunk looks like a slow request, not a different state.
 */
import { lazy, Suspense, type ComponentType, type ReactElement } from 'react'
import { Loading } from '../ui/components'

/**
 * A component from a module that is fetched on first render.
 *
 * @param load The dynamic import, e.g. `() => import('./MarkEntry')`
 * @param name The named export to render
 */
export function lazyComponent<P extends object, M extends Record<string, unknown>>(
  load: () => Promise<M>,
  name: keyof M & string,
): ComponentType<P> {
  const Lazy = lazy(async () => ({ default: (await load())[name] as ComponentType<P> }))
  function LazyComponent(props: P) {
    return (
      <Suspense fallback={<Loading rows={3} />}>
        <Lazy {...props} />
      </Suspense>
    )
  }
  LazyComponent.displayName = `Lazy(${name})`
  return LazyComponent
}

/** {@link lazyComponent} for a route element that takes no props. */
export function lazyScreen<M extends Record<string, unknown>>(
  load: () => Promise<M>,
  name: keyof M & string,
): ReactElement {
  const Screen = lazyComponent<object, M>(load, name)
  return <Screen />
}
