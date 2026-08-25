'use client';

import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div className="flex items-start gap-3 p-4 rounded-xl bg-danger/5 border border-danger/20 text-danger animate-slide-up">
      <AlertTriangle size={18} className="shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold mb-0.5">Erreur</p>
        <p className="text-sm opacity-80">{message}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="btn-ghost text-xs px-3 py-1.5 rounded-lg shrink-0"
        >
          <RefreshCw size={14} />
          Réessayer
        </button>
      )}
    </div>
  );
}
