'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import {
  ClipboardList,
  Calendar,
  User,
  Zap,
  AlertCircle,
  ChevronRight,
  ArrowLeft,
  RefreshCw,
  Filter,
} from 'lucide-react';
import { listTodos, listPVs, TodoItem, PVSummary } from '@/lib/api';
import {
  formatDate,
  difficultyLabel,
  difficultyColor,
  modelHintLabel,
  isOverdue,
  shortId,
  formatRelativeTime,
} from '@/lib/utils';
import { EmptyState } from '@/components/EmptyState';
import { LoadingSkeleton } from '@/components/LoadingSkeleton';
import { ErrorBanner } from '@/components/ErrorBanner';

type GroupedTodos = Map<string, { pv: PVSummary; todos: TodoItem[] }>;

export default function TodosPage() {
  const [grouped, setGrouped] = useState<GroupedTodos | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'overdue' | 'facile' | 'difficile' | 'très difficile'>('all');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [todos, pvs] = await Promise.all([listTodos(), listPVs()]);
      const pvMap = new Map(pvs.map((p) => [p.pv_id, p]));

      const grouped: GroupedTodos = new Map();
      for (const todo of todos) {
        const key = todo.pv_id;
        if (!grouped.has(key)) {
          const pv = pvMap.get(key);
          grouped.set(key, { pv: pv || fallbackPV(key), todos: [] });
        }
        grouped.get(key)!.todos.push(todo);
      }

      setGrouped(grouped);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Impossible de charger les todos');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const allEntries = grouped ? Array.from(grouped.entries()) : [];

  const filteredEntries = allEntries.filter(([, group]) => {
    if (filter === 'all') return true;
    if (filter === 'overdue') return group.todos.some((t) => isOverdue(t.deadline));
    return group.todos.some((t) => t.difficulty === filter);
  });

  const totalTasks = allEntries.reduce((sum, [, g]) => sum + g.todos.length, 0);

  return (
    <div className="max-w-4xl mx-auto px-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-3 mb-2">
        <Link href="/" className="btn-ghost p-2 rounded-lg">
          <ArrowLeft size={18} />
        </Link>
        <div>
          <h1 className="text-2xl font-extrabold text-text flex items-center gap-3">
            <ClipboardList size={24} className="text-tech" />
            Liste des Tâches
          </h1>
          <p className="text-sm text-text-muted mt-0.5">
            Fallback Ora Studio — {totalTasks} tâche{totalTasks !== 1 ? 's' : ''} extraite{totalTasks !== 1 ? 's' : ''} des appels tech
          </p>
        </div>
        <button onClick={fetchData} className="btn-ghost p-2 rounded-lg ml-auto" title="Rafraîchir">
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Filter pills */}
      {allEntries.length > 0 && (
        <div className="flex items-center gap-2 mt-4 mb-6 flex-wrap">
          <Filter size={14} className="text-text-dim" />
          {(
            ['all', 'overdue', 'facile', 'difficile', 'très difficile'] as const
          ).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
                filter === f
                  ? 'bg-accent text-white shadow-md shadow-accent/20'
                  : 'bg-bg-tertiary text-text-muted hover:text-text border border-border'
              }`}
            >
              {f === 'all' ? 'Toutes' : f === 'overdue' ? 'En retard' : difficultyLabel(f)}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      {error ? (
        <ErrorBanner message={error} onRetry={fetchData} />
      ) : loading ? (
        <LoadingSkeleton count={3} />
      ) : filteredEntries.length === 0 ? (
        <EmptyState
          icon={<ClipboardList size={28} />}
          title="Aucune tâche"
          description={
            filter !== 'all'
              ? 'Aucune tâche ne correspond à ce filtre.'
              : 'Les todos des appels tech apparaîtront ici après le premier traitement. Utilise le Transcript Processor dans le Test Console pour générer un PV tech.'
          }
          action={
            <a href="http://localhost:8000" className="btn-primary text-sm">
              <Zap size={16} />
              Ouvrir le Test Console
            </a>
          }
        />
      ) : (
        <div className="space-y-6">
          {filteredEntries.map(([pvId, group]) => (
            <Link
              key={pvId}
              href={`/todos/${pvId}`}
              className="card block no-underline group cursor-pointer hover:border-tech/30 transition-all duration-200"
            >
              {/* PV header row */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="badge badge-tech text-[10px]">#appel-tech</span>
                    <span className="text-xs text-text-dim font-mono">{shortId(pvId)}</span>
                    {group.pv.stored_at && (
                      <span className="text-xs text-text-dim">{formatRelativeTime(group.pv.stored_at)}</span>
                    )}
                  </div>
                  <h3 className="text-base font-bold text-text group-hover:text-tech transition-colors truncate">
                    {group.pv.subject || 'Sans sujet'}
                  </h3>
                  <p className="text-xs text-text-muted mt-0.5">
                    {group.pv.left || '?'} ↔ {group.pv.right || '?'} · {formatDate(group.pv.call_date)}
                  </p>
                </div>
                <ChevronRight
                  size={18}
                  className="text-text-dim group-hover:text-tech transition-colors shrink-0 mt-2"
                />
              </div>

              {/* Todo items preview */}
              <div className="space-y-2">
                {group.todos.slice(0, 3).map((todo, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-3 p-2.5 rounded-lg bg-bg/60 border border-border/50"
                  >
                    <span className="w-6 h-6 rounded flex items-center justify-center text-xs font-bold bg-bg-tertiary text-text-muted shrink-0">
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-text truncate">{todo.title}</p>
                      <div className="flex items-center gap-3 mt-1 text-xs text-text-muted">
                        <span className="flex items-center gap-1">
                          <User size={11} />
                          {todo.owner}
                        </span>
                        {todo.deadline && (
                          <span className={`flex items-center gap-1 ${isOverdue(todo.deadline) ? 'text-danger' : ''}`}>
                            <Calendar size={11} />
                            {formatDate(todo.deadline)}
                            {isOverdue(todo.deadline) && (
                              <AlertCircle size={11} className="text-danger" />
                            )}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {todo.difficulty && (
                        <span className={`badge text-[10px] ${difficultyColor(todo.difficulty)}`}>
                          {difficultyLabel(todo.difficulty)}
                        </span>
                      )}
                      {todo.model_hint && (
                        <span className="text-[10px] text-text-dim font-mono bg-bg-tertiary px-1.5 py-0.5 rounded">
                          {modelHintLabel(todo.model_hint)}
                        </span>
                      )}
                    </div>
                  </div>
                ))}

                {group.todos.length > 3 && (
                  <p className="text-xs text-text-muted pl-2">
                    +{group.todos.length - 3} autre{group.todos.length - 3 > 1 ? 's' : ''} tâche{group.todos.length - 3 > 1 ? 's' : ''}…
                  </p>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function fallbackPV(pvId: string): PVSummary {
  return {
    pv_id: pvId,
    call_date: '',
    call_type: '#appel-tech',
    subject: 'PV chargé',
    left: '?',
    right: '?',
    task_count: 0,
    meeting_created: false,
    stored_at: '',
  };
}
