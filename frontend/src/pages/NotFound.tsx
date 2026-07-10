import { useNavigate } from 'react-router-dom'

export default function NotFound() {
  const navigate = useNavigate()
  return (
    <div className="fh-page">
      <div className="fh-page-inner">
        <div className="mx-auto flex min-h-[70vh] w-full max-w-2xl items-center justify-center">
          <div className="fh-card fh-card-pad w-full text-center">
            <p className="text-7xl font-semibold text-border leading-none mb-4 select-none">404</p>
            <h1 className="fh-page-title mb-2">Page not found</h1>
            <p className="fh-page-subtitle mb-8">This page doesn't exist.</p>
            <button
              onClick={() => navigate('/home')}
              className="fh-button-primary"
            >
              Return to Dashboard
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
