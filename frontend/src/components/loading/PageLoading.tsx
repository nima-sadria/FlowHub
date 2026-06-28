import Spinner from './Spinner'

interface Props {
  message?: string
}

export default function PageLoading({ message }: Props) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3">
      <Spinner size="lg" />
      {message && <p className="text-[13px] text-wp-muted">{message}</p>}
    </div>
  )
}
