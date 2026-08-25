export function LoadingSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="space-y-4 animate-fade-in">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="card flex items-center gap-4 animate-pulse-soft"
        >
          <div className="w-10 h-10 rounded-lg bg-bg-tertiary" />
          <div className="flex-1 space-y-2">
            <div className="h-4 bg-bg-tertiary rounded w-1/3" />
            <div className="h-3 bg-bg-tertiary rounded w-2/3" />
          </div>
          <div className="h-6 w-20 bg-bg-tertiary rounded-full" />
        </div>
      ))}
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="max-w-6xl mx-auto px-4 animate-fade-in">
      <div className="h-8 bg-bg-tertiary rounded w-48 mb-2" />
      <div className="h-4 bg-bg-tertiary rounded w-72 mb-8" />
      <LoadingSkeleton />
    </div>
  );
}
