/**
 * Shared formatters and utilities.
 */

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-FR', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('fr-FR', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'à l\'instant';
    if (mins < 60) return `il y a ${mins} min`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `il y a ${hours}h`;
    const days = Math.floor(hours / 24);
    return `il y a ${days}j`;
  } catch {
    return '';
  }
}

export function difficultyLabel(d: string | null | undefined): string {
  if (!d) return '—';
  const map: Record<string, string> = {
    facile: 'Facile',
    difficile: 'Difficile',
    'très difficile': 'Très difficile',
  };
  return map[d] || d;
}

export function difficultyColor(d: string | null | undefined): string {
  if (!d) return 'bg-bg-tertiary text-text-muted border-border';
  switch (d) {
    case 'facile':
      return 'diff-facile';
    case 'difficile':
      return 'diff-difficile';
    case 'très difficile':
      return 'diff-tres-difficile';
    default:
      return 'bg-bg-tertiary text-text-muted border-border';
  }
}

export function modelHintLabel(m: string | null | undefined): string {
  if (!m) return '—';
  const map: Record<string, string> = {
    'gpt-4o-mini': 'GPT-4o Mini',
    'claude-sonnet-4-6': 'Claude Sonnet',
    'claude-opus-4-6': 'Claude Opus',
  };
  return map[m] || m;
}

export function shortId(id: string): string {
  if (!id) return '—';
  return id.slice(0, 8) + '…';
}

export function initials(name: string | null | undefined): string {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function isOverdue(deadline: string | null | undefined): boolean {
  if (!deadline) return false;
  try {
    return new Date(deadline) < new Date();
  } catch {
    return false;
  }
}
