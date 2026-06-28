import { useNavigate } from 'react-router-dom'

export default function NotFound() {
  const navigate = useNavigate()
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 text-center">
      <p className="text-[72px] font-bold text-border leading-none mb-4 select-none">404</p>
      <h1 className="text-[20px] font-bold text-text-base mb-2">Page not found</h1>
      <p className="text-[13px] text-wp-muted mb-6">This page doesn't exist.</p>
      <button
        onClick={() => navigate('/home')}
        className="px-4 py-2 rounded-lg bg-accent text-white text-[13px] font-medium hover:bg-accent-hover transition-colors"
      >
        Return to Dashboard
      </button>
    </div>
  )
}
