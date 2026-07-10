import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useServices } from '../services/ServiceContext'
import type { SourceConfig, ConnectionTestResult } from '../services/types'
import Spinner from '../components/loading/Spinner'
import { useNotification } from '../notifications/NotificationProvider'
import { inputHint } from '../utils/inputHint'
import PageShell from '../components/PageShell'

type Step = 1 | 2 | 3 | 4

function StepIndicator({ current, total }: { current: Step; total: number }) {
  return (
    <div className="flex items-center gap-2 justify-center mb-8">
      {Array.from({ length: total }, (_, i) => {
        const step = (i + 1) as Step
        const done = step < current
        const active = step === current
        return (
          <div key={step} className="flex items-center gap-2">
            <div className={[
              'w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-colors',
              active  ? 'bg-accent text-white' :
              done    ? 'bg-wp-green/20 text-wp-green' :
              'bg-bg-base border border-border text-wp-muted',
            ].join(' ')}>
              {done ? (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="w-3.5 h-3.5">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              ) : step}
            </div>
            {i < total - 1 && (
              <div className={['w-10 h-px', done ? 'bg-wp-green/40' : 'bg-border'].join(' ')} />
            )}
          </div>
        )
      })}
    </div>
  )
}

const STEP_LABELS = ['Select Type', 'Configure', 'Test Connection', 'Done']

export default function SourceWizard() {
  const { sources } = useServices()
  const navigate = useNavigate()
  const { success } = useNotification()

  const [step, setStep] = useState<Step>(1)
  const [config, setConfig] = useState<SourceConfig>({
    name: '',
    type: 'nextcloud_excel',
    url: '',
    username: '',
    password: '',
    filePath: '',
  })
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<keyof SourceConfig, string>>>({})

  function validateStep2(): boolean {
    const errs: typeof errors = {}
    if (!config.name.trim()) errs.name = 'Name is required'
    if (!config.url.trim()) errs.url = 'URL is required'
    if (!config.username.trim()) errs.username = 'Username is required'
    if (!config.password.trim()) errs.password = 'Password is required'
    if (!config.filePath.trim()) errs.filePath = 'File path is required'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  async function handleTest() {
    if (!validateStep2()) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await sources.testConnection(config)
      setTestResult(result)
      if (result.success) setStep(3)
    } finally {
      setTesting(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    try {
      await sources.createSource(config)
      success(`Source "${config.name}" added successfully`)
      setStep(4)
    } finally {
      setSaving(false)
    }
  }

  function field(name: keyof SourceConfig, label: string, type = 'text', template_variable = '') {
    return (
      <div key={name} className="fh-field">
        <label className="fh-help-text">{label}</label>
        <input
          type={type}
          value={config[name] as string}
          onChange={e => { setConfig(c => ({ ...c, [name]: e.target.value })); setErrors(ev => ({ ...ev, [name]: undefined })) }}
          {...inputHint(template_variable)}
          autoComplete={type === 'password' ? 'new-password' : undefined}
          className={[
            'fh-input',
            errors[name] ? 'fh-input-error' : '',
          ].join(' ')}
        />
        {errors[name] && <p className="fh-field-error">{errors[name]}</p>}
      </div>
    )
  }

  return (
    <PageShell className="max-w-3xl">
      <div className="fh-page-header">
        <div>
          <h1 className="fh-page-title">Add a Source</h1>
          <p className="fh-page-subtitle">{STEP_LABELS[step - 1]}</p>
        </div>
      </div>

      <StepIndicator current={step} total={4} />

      <div className="fh-card fh-card-pad">

        {/* Step 1 - Select type */}
        {step === 1 && (
          <div className="flex flex-col gap-4">
            <p className="fh-text-body-sm">Select the type of data source to connect.</p>
            <button
              onClick={() => setStep(2)}
              className="fh-card flex w-full items-start gap-4 border-accent bg-accent/5 p-4 text-start transition-colors hover:bg-accent/10"
            >
              <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-accent">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
              </div>
              <div>
                <div className="fh-text-body font-semibold">Nextcloud Excel</div>
                <div className="fh-text-caption mt-0.5">
                  Read prices from an Excel spreadsheet hosted on Nextcloud or a compatible WebDAV server.
                </div>
              </div>
            </button>
          </div>
        )}

        {/* Step 2 - Configure */}
        {step === 2 && (
          <div className="flex flex-col gap-4">
            {field('name', 'Source name', 'text', 'My Price List')}
            {field('url', 'Nextcloud URL', 'url', 'https://cloud.example.com')}
            {field('username', 'Username')}
            {field('password', 'Password', 'password')}
            {field('filePath', 'File path', 'text', '/Price_List.xlsx')}
            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setStep(1)}
                className="fh-button-secondary flex-1"
              >
                Back
              </button>
              <button
                onClick={() => void handleTest()}
                disabled={testing}
                className="fh-button-primary flex-1"
              >
                {testing && <Spinner size="sm" className="text-white" />}
                {testing ? 'Testing...' : 'Test Connection'}
              </button>
            </div>
          </div>
        )}

        {/* Step 3 - Test result / save */}
        {step === 3 && (
          <div className="flex flex-col gap-4">
            {testResult?.success ? (
              <div className="fh-alert fh-alert-success">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-wp-green flex-shrink-0 mt-0.5">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <div>
                  <p className="fh-text-body font-medium text-wp-green">Connection successful</p>
                  <p className="fh-text-caption mt-0.5">{testResult.message}</p>
                </div>
              </div>
            ) : testResult && !testResult.success ? (
              <div className="fh-alert fh-alert-danger">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-wp-red flex-shrink-0 mt-0.5">
                  <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
                </svg>
                <p className="fh-text-body text-wp-red">{testResult.message}</p>
              </div>
            ) : null}

            <div className="flex gap-3">
              <button
                onClick={() => { setStep(2); setTestResult(null) }}
                className="fh-button-secondary flex-1"
              >
                Back
              </button>
              {testResult?.success && (
                <button
                  onClick={() => void handleSave()}
                  disabled={saving}
                  className="fh-button-primary flex-1"
                >
                  {saving && <Spinner size="sm" className="text-white" />}
                  {saving ? 'Saving...' : 'Save Source'}
                </button>
              )}
              {testResult && !testResult.success && (
                <button
                  onClick={() => void handleTest()}
                  disabled={testing}
                  className="fh-button-secondary flex-1"
                >
                  Retry
                </button>
              )}
            </div>
          </div>
        )}

        {/* Step 4 - Done */}
        {step === 4 && (
          <div className="flex flex-col items-center gap-5 py-4 text-center">
            <div className="w-14 h-14 rounded-full bg-wp-green/10 flex items-center justify-center">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-7 h-7 text-wp-green">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <div>
              <p className="fh-section-title">{config.name} added</p>
              <p className="fh-text-body-sm mt-1">Your source is active and ready to sync.</p>
            </div>
            <div className="flex gap-3 w-full">
              <button
                onClick={() => navigate('/products')}
                className="fh-button-secondary flex-1"
              >
                View Products
              </button>
              <button
                onClick={() => navigate('/sources')}
                className="fh-button-primary flex-1"
              >
                Back to Sources
              </button>
            </div>
          </div>
        )}
      </div>
    </PageShell>
  )
}
