import { translate } from '../i18n'
import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  override render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div className="p-4 sm:p-7">
          <div className="fh-card max-w-xl p-6">
            <h2 className="fh-section-title mb-2">{translate('common:errorBoundary.somethingWentWrong')}</h2>
            <p className="fh-text-body-sm mb-4">
              {translate('common:errorBoundary.anUnexpectedErrorOccurredOnThisPage')}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="fh-button-primary"
            >
              {translate('common:errorBoundary.tryAgain')}
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
