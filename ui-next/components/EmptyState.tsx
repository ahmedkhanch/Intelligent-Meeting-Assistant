import { ReactNode } from 'react';

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center animate-fade-in">
      <div className="w-14 h-14 rounded-2xl bg-bg-tertiary flex items-center justify-center mb-4 text-text-dim">
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-text mb-1.5">{title}</h3>
      <p className="text-sm text-text-muted max-w-sm mb-5 leading-relaxed">
        {description}
      </p>
      {action}
    </div>
  );
}
