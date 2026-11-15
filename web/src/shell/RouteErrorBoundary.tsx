/**
 * The one render-error boundary, around everything `App` returns
 * [functional-spec § 10 item 2].
 *
 * Without it, any error thrown while rendering unmounts the root and the
 * page goes blank — which is how one email-only invitation once blanked
 * the whole app for a centre's managers. With it, the failing page shows
 * the ordinary error card (`error_unexpected`, Retry) and the rest of the
 * app is reachable.
 *
 * **It resets on a pathname change, and is deliberately not keyed on the
 * path.** A `key` would remount the shell, its open sheets and its loaded
 * data on every navigation. Instead `App` passes the pathname, and the
 * error is cleared when it changes, so navigating away recovers without
 * remounting anything that did not fail. Retry clears it in place.
 *
 * It logs nothing: React already reports a caught render error, without
 * props or state [NFR3.5 limit].
 */
import { Component, type ReactNode } from 'react'
import { ApiError, UNEXPECTED_KEY } from '../api/errors'
import { useT } from '../i18n/i18n'
import { ErrorCard } from '../ui/components'

/** What the card is given: retryable, so it offers Retry. */
const RENDER_FAILED = new ApiError(500, 'UNEXPECTED', UNEXPECTED_KEY, true)

function Failed({ onRetry }: { onRetry: () => void }) {
  const { t } = useT()
  return (
    <div className="auth-page">
      <div className="auth-card">
        <ErrorCard title={t('error_unexpected')} error={RENDER_FAILED} onRetry={onRetry} />
      </div>
    </div>
  )
}

interface Props {
  /** The current location's pathname; a change clears the error. */
  pathname: string
  children: ReactNode
}

interface State {
  failed: boolean
}

export class RouteErrorBoundary extends Component<Props, State> {
  override state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  override componentDidUpdate(previous: Props): void {
    if (this.state.failed && previous.pathname !== this.props.pathname)
      this.setState({ failed: false })
  }

  private readonly retry = () => this.setState({ failed: false })

  override render(): ReactNode {
    return this.state.failed ? <Failed onRetry={this.retry} /> : this.props.children
  }
}
