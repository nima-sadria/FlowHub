import { useEffect, useId, useState } from 'react'
import { useNotification } from '../notifications/NotificationProvider'
import Icon from './Icon'

interface SecretFieldProps {
  label: string
  value: string
  configured?: boolean
  required?: boolean
  disabled?: boolean
  onChange: (value: string) => void
  configuredHint: string
  revealLabel: string
  concealLabel: string
  copyLabel: string
  copiedLabel: string
  emptySecretHint: string
  placeholder: string
  configuredMask?: string
  error?: string
}

/** A write-only credential field; stored secrets are never placed in the DOM. */
export default function SecretField({
  label,
  value,
  configured = false,
  required = false,
  disabled = false,
  onChange,
  configuredHint,
  revealLabel,
  concealLabel,
  copyLabel,
  copiedLabel,
  emptySecretHint,
  placeholder,
  configuredMask = '••••••••••••',
  error,
}: SecretFieldProps) {
  const id = useId()
  const { success } = useNotification()
  const [revealed, setRevealed] = useState(false)
  const [focused, setFocused] = useState(false)
  const hasLocalValue = value.length > 0
  const showsSaved = configured && !hasLocalValue
  const showConfiguredMask = showsSaved && !focused

  useEffect(() => {
    if (!hasLocalValue) setRevealed(false)
  }, [hasLocalValue])

  async function copyLocalValue() {
    if (!hasLocalValue) return
    await navigator.clipboard.writeText(value)
    success(copiedLabel)
  }

  return (
    <div className="fh-field">
      <label className="fh-help-text" htmlFor={id}>{label}</label>
      <div className="relative">
        <input
          id={id}
          type={revealed ? 'text' : 'password'}
          value={value}
          required={required && !configured}
          disabled={disabled}
          onChange={event => onChange(event.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          className="fh-input pe-20"
          placeholder={showConfiguredMask ? '' : placeholder}
          autoComplete="new-password"
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : configured ? `${id}-configured` : undefined}
        />
        {showConfiguredMask && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 start-3 flex items-center font-mono tracking-wider text-text-muted"
            data-testid="configured-secret-mask"
          >
            {configuredMask}
          </span>
        )}
        <div className="absolute inset-y-0 end-2 flex items-center gap-1">
          <button
            type="button"
            className="fh-icon-button-sm"
            disabled={disabled || !hasLocalValue}
            aria-label={revealed ? concealLabel : revealLabel}
            title={showsSaved ? emptySecretHint : (revealed ? concealLabel : revealLabel)}
            onClick={() => setRevealed(current => !current)}
          >
            <Icon name="preview" />
          </button>
          <button
            type="button"
            className="fh-icon-button-sm"
            disabled={disabled || !hasLocalValue}
            aria-label={copyLabel}
            title={showsSaved ? emptySecretHint : copyLabel}
            onClick={() => void copyLocalValue()}
          >
            <Icon name="copy" />
          </button>
        </div>
      </div>
      {configured && (
        <span className="fh-help-text" id={`${id}-configured`}>
          {configuredHint}
        </span>
      )}
      {error && <span className="fh-field-error" id={`${id}-error`}>{error}</span>}
    </div>
  )
}
