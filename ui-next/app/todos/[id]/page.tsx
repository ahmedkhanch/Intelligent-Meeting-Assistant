'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  ArrowLeft,
  Calendar,
  User,
  AlertCircle,
  Gauge,
  Cpu,
  Clock,
  FileText,
  ExternalLink,
  CheckCircle2,
} from 'lucide-react';
import { getPV, listTodos, PV, TodoItem } from '@/lib/api';
import {
  formatDate,
  formatDateTime,
  difficultyLabel,
  difficultyColor,
  modelHintLabel,
  isOverdue,
  shortId,
} from '@/lib/utils';
import { LoadingSkeleton } from '@/components/LoadingSkeleton';
import { ErrorBanner } from '@/components/ErrorBanner';

export default function TodoDetailPage() {
  const params = useParams();
  const pvId = params.id as string;

  const [pv, setPV] = useState<PV | null>(null);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pvData, todoData] = await Promise.all([
        getPV(pvId),
        listTodos(pvId),
      ]);
      setPV(pvData);
      setTodos(todoData);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Impossible de charger les données');
    } finally {
      setLoading(false);
    }
  }, [pvId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-4">
        <Link href="/todos" className="btn-ghost inline-flex mb-4 px-3 py-2 rounded-lg">
          <ArrowLeft size={18} />
          Retour aux tâches
        </Link>
        <ErrorBanner message={error} onRetry={fetchData} />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4">
        <div className="h-8 bg-bg-tertiary rounded w-36 mb-6" />
        <LoadingSkeleton count={4} />
      </div>
    );
  }

  if (!pv) {
    return (
      <div className="max-w-4xl mx-auto px-4">
        <Link href="/todos" className="btn-ghost inline-flex mb-4 px-3 py-2 rounded-lg">
          <ArrowLeft size={18} />
          Retour aux tâches
        </Link>
        <div className="card text-center py-12">
          <FileText size={32} className="text-text-dim mx-auto mb-3" />
          <p className="text-text-muted">PV introuvable</p>
        </div>
      </div>
    );
  }

  const completedCount = todos.filter(
    (t) => !isOverdue(t.deadline) && t.difficulty === 'facile'
  ).length;

  return (
    <div className="max-w-4xl mx-auto px-4 animate-fade-in">
      {/* Back */}
      <Link href="/todos" className="btn-ghost inline-flex mb-5 px-3 py-2 rounded-lg">
        <ArrowLeft size={18} />
        Retour aux tâches
      </Link>

      {/* PV summary card */}
      <div className="card mb-6">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="badge badge-tech text-[10px]">#appel-tech</span>
              <span className="text-xs text-text-dim font-mono">{shortId(pvId)}</span>
            </div>
            <h1 className="text-xl font-extrabold text-text mb-1">{pv.subject}</h1>
            <div className="flex items-center gap-3 text-sm text-text-muted flex-wrap">
              <span className="flex items-center gap-1.5">
                <User size={14} />
                {pv.left.name} ↔ {pv.right.name}
              </span>
              <span className="flex items-center gap-1.5">
                <Calendar size={14} />
                {formatDateTime(pv.call_date)}
              </span>
            </div>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-4 shrink-0">
            <div className="text-center">
              <p className="text-2xl font-extrabold text-text">{todos.length}</p>
              <p className="text-[10px] text-text-muted uppercase tracking-wider">Tâches</p>
            </div>
            {pv.meeting_created && (
              <div className="text-center">
                <p className="text-2xl font-extrabold text-success">
                  <CheckCircle2 size={20} className="inline" />
                </p>
                <p className="text-[10px] text-text-muted uppercase tracking-wider">RDV</p>
              </div>
            )}
          </div>
        </div>

        {/* Compte rendu excerpt */}
        {pv.compte_rendu && (
          <details className="mt-4">
            <summary className="text-sm text-text-muted cursor-pointer hover:text-text transition-colors flex items-center gap-2">
              <FileText size={14} />
              Voir le compte rendu
            </summary>
            <div className="mt-3 p-3.5 rounded-lg bg-bg border border-border text-sm leading-relaxed text-text/90 whitespace-pre-wrap max-h-64 overflow-y-auto scrollbar-thin">
              {pv.compte_rendu}
            </div>
          </details>
        )}
      </div>

      {/* Todo list — the core fallback display */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="section-title !mb-0">Tâches à réaliser</h2>
        <Link
          href={`/pvs/${pvId}`}
          className="btn-ghost text-xs px-3 py-1.5 rounded-lg"
        >
          <ExternalLink size={13} />
          Voir le PV complet
        </Link>
      </div>

      {todos.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-text-muted text-sm">Aucune tâche extraite de cet appel.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {todos.map((todo, i) => {
            const overdue = isOverdue(todo.deadline);
            return (
              <div
                key={i}
                className={`card flex items-start gap-4 group transition-all duration-200 ${
                  overdue ? 'border-danger/20 bg-danger/[0.02]' : ''
                }`}
              >
                {/* Index + status */}
                <div
                  className={`w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold shrink-0 mt-0.5 ${
                    overdue
                      ? 'bg-danger/10 text-danger border border-danger/20'
                      : 'bg-bg-tertiary text-text-muted border border-border'
                  }`}
                >
                  {overdue ? <AlertCircle size={18} /> : i + 1}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <h3 className="text-base font-semibold text-text mb-1.5">{todo.title}</h3>
                  <div className="flex items-center gap-4 flex-wrap text-xs text-text-muted">
                    <span className="flex items-center gap-1.5">
                      <User size={12} />
                      <span className="font-medium text-text/80">{todo.owner}</span>
                    </span>
                    {todo.deadline && (
                      <span className={`flex items-center gap-1.5 ${overdue ? 'text-danger font-semibold' : ''}`}>
                        <Clock size={12} />
                        {formatDate(todo.deadline)}
                        {overdue && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-danger/15 text-danger">
                            En retard
                          </span>
                        )}
                      </span>
                    )}
                  </div>
                </div>

                {/* Badges */}
                <div className="flex items-center gap-2 shrink-0 flex-wrap">
                  {todo.difficulty && (
                    <span className={`badge text-[10px] ${difficultyColor(todo.difficulty)}`}>
                      <Gauge size={11} />
                      {difficultyLabel(todo.difficulty)}
                    </span>
                  )}
                  {todo.model_hint && (
                    <span className="badge text-[10px] bg-bg-tertiary text-text-muted border border-border">
                      <Cpu size={11} />
                      {modelHintLabel(todo.model_hint)}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Meeting info */}
      {pv.meeting_created && pv.meeting_datetime && (
        <div className="card mt-6 border-accent/20 bg-accent/[0.02]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-accent/10 flex items-center justify-center">
              <Calendar size={18} className="text-accent-bright" />
            </div>
            <div>
              <p className="text-sm font-semibold text-text">Rendez-vous planifié</p>
              <p className="text-sm text-text-muted">{formatDateTime(pv.meeting_datetime)}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
