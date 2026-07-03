import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useServices } from '../services/ServiceContext'
import type { SourceConfig, ConnectionTestResult } from '../services/types'
import Spinner from '../components/loading/Spinner'
import { useNotification } from '../notifications/NotificationProvider'
import { inputHint } from '../utils/inputHint'

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
              'w-7 h-7 rounded-full flex items-center justify-center text-[12px] font-bold transition-colors',
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
      <div key={name}>
        <label className="block text-[12px] font-medium text-text-base mb-1.5">{label}</label>
        <input
          type={type}
          value={config[name] as string}
          onChange={e => { setConfig(c => ({ ...c, [name]: e.target.value })); setErrors(ev => ({ ...ev, [name]: undefined })) }}
          {...inputHint(template_variable)}
          autoComplete={type === 'password' ? 'new-password' : undefined}
          className={[
            'w-full px-3 py-2 text-[13px] border rounded-lg bg-bg-base text-text-base focus:outline-none focus:border-accent transition-colors',
            errors[name] ? 'border-wp-red' : 'border-border',
          ].join(' ')}
        />
        {errors[name] && <p className="text-[11px] text-wp-red mt-1">{errors[name]}</p>}
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-7 max-w-lg mx-auto">
      <div className="mb-6">
        <h1 className="text-[22px] font-bold text-text-base">Add a Source</h1>
        <p className="text-[13px] text-wp-muted mt-0.5">{STEP_LABELS[step - 1]}</p>
      </div>

      <StepIndicator current={step} total={4} />

      <div className="bg-bg-card border border-border rounded-card shadow-card p-[22px]">

        {/* Step 1 - Select type */}
        {step === 1 && (
          <div className="flex flex-col gap-4">
            <p className="text-[13px] text-wp-muted">Select the type of data source to connect.</p>
            <button
              onClick={() => setStep(2)}
              className="flex items-start gap-4 p-4 border-2 border-accent rounded-card bg-accent/5 text-start w-full hover:bg-accent/10 transition-colors"
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
                <div className="text-[14px] font-semibold text-text-base">Nextcloud Excel</div>
                <div className="text-[12px] text-wp-muted mt-0.5">
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
                className="flex-1 py-2 text-[13px] border border-border rounded-lg text-wp-muted hover:text-text-base hover:border-accent transition-colors"
              >
                Back
              </button>
              <button
                onClick={() => void handleTest()}
                disabled={testing}
                className="flex-1 py-2 text-[13px] bg-accent text-white rounded-lg font-medium hover:bg-accent-hover transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
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
              <div className="flex items-start gap-3 p-4 bg-wp-green/10 border border-wp-green/30 rounded-lg">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-wp-green flex-shrink-0 mt-0.5">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <div>
                  <p className="text-[13px] font-medium text-wp-green">Connection successful</p>
                  <p className="text-[12px] text-wp-muted mt-0.5">{testResult.message}</p>
                </div>
              </div>
            ) : testResult && !testResult.success ? (
              <div className="flex items-start gap-3 p-4 bg-wp-red/10 border border-wp-red/30 rounded-lg">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-wp-red flex-shrink-0 mt-0.5">
                  <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
                </svg>
                <p className="text-[13px] text-wp-red">{testResult.message}</p>
              </div>
            ) : null}

            <div className="flex gap-3">
              <button
                onClick={() => { setStep(2); setTestResult(null) }}
                className="flex-1 py-2 text-[13px] border border-border rounded-lg text-wp-muted hover:text-text-base hover:border-accent transition-colors"
              >
                Back
              </button>
              {testResult?.success && (
                <button
                  onClick={() => void handleSave()}
                  disabled={saving}
                  className="flex-1 py-2 text-[13px] bg-accent text-white rounded-lg font-medium hover:bg-accent-hover transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {saving && <Spinner size="sm" className="text-white" />}
                  {saving ? 'Saving...' : 'Save Source'}
                </button>
              )}
              {testResult && !testResult.success && (
                <button
                  onClick={() => void handleTest()}
                  disabled={testing}
                  className="flex-1 py-2 text-[13px] border border-accent text-accent rounded-lg font-medium hover:bg-accent/5 transition-colors disabled:opacity-50"
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
              <p className="text-[16px] font-semibold text-text-base">{config.name} added</p>
              <p className="text-[13px] text-wp-muted mt-1">Your source is active and ready to sync.</p>
            </div>
            <div className="flex gap-3 w-full">
              <button
                onClick={() => navigate('/products')}
                className="flex-1 py-2 text-[13px] border border-border rounded-lg text-wp-muted hover:text-text-base hover:border-accent transition-colors"
              >
                View Products
              </button>
              <button
                onClick={() => navigate('/sources')}
                className="flex-1 py-2 text-[13px] bg-accent text-white rounded-lg font-medium hover:bg-accent-hover transition-colors"
              >
                Back to Sources
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
