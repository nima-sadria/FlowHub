import { useId, useState } from 'react'
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
  error?: string
}

/**
 * A write-only credential field.
 *
 * Stored secrets are represented only by `configured`; their value is never
 * placed in the DOM. Reveal and copy operate exclusively on a replacement
 * value typed during the current form session.
 */
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
  error,
}: SecretFieldProps) {
  const id = useId()
  const [revealed, setRevealed] = useState(false)
  const hasLocalValue = value.length > 0

  async function copyLocalValue() {
    if (!hasLocalValue) return
    await navigator.clipboard.writeText(value)
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
          placeholder={configured && !hasLocalValue ? '••••••••' : undefined}
          onChange={event => onChange(event.target.value)}
          className="fh-input pe-20"
          autoComplete="new-password"
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : configured ? `${id}-configured` : undefined}
        />
        <div className="absolute inset-y-0 end-2 flex items-center gap-1">
          <button
            type="button"
            className="fh-icon-button-sm"
            disabled={disabled || !hasLocalValue}
            aria-label={revealed ? concealLabel : revealLabel}
            title={revealed ? concealLabel : revealLabel}
            onClick={() => setRevealed(current => !current)}
          >
            <Icon name="preview" />
          </button>
          <button
            type="button"
            className="fh-icon-button-sm"
            disabled={disabled || !hasLocalValue}
            aria-label={copyLabel}
            title={copyLabel}
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
