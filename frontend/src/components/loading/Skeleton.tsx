interface SkeletonProps {
  className?: string
}

export function Skeleton({ className = '' }: SkeletonProps) {
  return <div className={['animate-pulse rounded-lg bg-bg-subtle border border-border/50', className].join(' ')} />
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  const widths = ['w-full', 'w-4/5', 'w-3/4', 'w-5/6', 'w-2/3']
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={`h-3 ${widths[i % widths.length]}`} />
      ))}
    </div>
  )
}

export function SkeletonCard() {
  return (
    <div className="fh-card fh-card-pad flex flex-col gap-3">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-5 w-32" />
      <SkeletonText lines={2} />
    </div>
  )
}
