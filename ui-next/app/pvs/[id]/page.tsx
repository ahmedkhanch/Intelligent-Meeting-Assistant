'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  ArrowLeft,
  FileText,
  Calendar,
  User,
  Phone,
  Briefcase,
  Clock,
  Gauge,
  Cpu,
  CheckCircle2,
  ClipboardList,
  Hash,
  MessageSquareText,
  AlertCircle,
  CalendarCheck,
  RefreshCw,
  PhoneCall,
  ExternalLink,
  Braces,
} from 'lucide-react';
import { getPV, PV } from '@/lib/api';
import {
  formatDate,
  formatDateTime,
  difficultyLabel,
  difficultyColor,
  modelHintLabel,
  isOverdue,
  shortId,
  initials,
} from '@/lib/utils';
import { PageSkeleton } from '@/components/LoadingSkeleton';
import { ErrorBanner } from '@/components/ErrorBanner';

export default function PVDetailPage() {
  const params = useParams();
  const pvId = params.id as string;

  const [pv, setPV] = useState<PV | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getPV(pvId);
      setPV(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Impossible de charger le PV');
    } finally {
      setLoading(false);
    }
  }, [pvId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (error) {
    return (
      <div className="max-w-5xl mx-auto px-4">
        <Link href="/pvs" className="btn-ghost inline-flex mb-4 px-3 py-2 rounded-lg">
          <ArrowLeft size={18} />
          Retour aux PVs
        </Link>
        <ErrorBanner message={error} onRetry={fetchData} />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4">
        <div className="h-8 bg-bg-tertiary rounded w-36 mb-6" />
        <PageSkeleton />
      </div>
    );
  }

  if (!pv) {
    return (
      <div className="max-w-5xl mx-auto px-4">
        <Link href="/pvs" className="btn-ghost inline-flex mb-4 px-3 py-2 rounded-lg">
          <ArrowLeft size={18} />
          Retour aux PVs
        </Link>
        <div className="card text-center py-12">
          <FileText size={32} className="text-text-dim mx-auto mb-3" />
          <p className="text-text-muted">PV introuvable</p>
        </div>
      </div>
    );
  }

  const isTech = pv.call_type === '#appel-tech';
  const taskCount = pv.actions.length;
  const extras = pv.additional_participants ?? [];

  const theme = isTech
    ? {
        text: 'text-tech',
        bg: 'bg-tech/10',
        border: 'border-tech/25',
        gradient: 'from-tech to-accent',
        soft: 'bg-tech/5',
      }
    : {
        text: 'text-commercial',
        bg: 'bg-commercial/10',
        border: 'border-commercial/25',
        gradient: 'from-commercial to-accent',
        soft: 'bg-commercial/5',
      };

  return (
    <div className="max-w-5xl mx-auto px-4 animate-fade-in pb-16">
      {/* ═══ Top bar ═══ */}
      <div className="flex items-center justify-between mb-6">
        <Link href="/pvs" className="btn-ghost inline-flex px-3 py-2 rounded-lg">
          <ArrowLeft size={18} />
          Retour aux PVs
        </Link>
        <div className="flex items-center gap-2">
          <button onClick={fetchData} className="btn-ghost p-2 rounded-lg" title="Rafraîchir">
            <RefreshCw size={16} />
          </button>
          {isTech && (
            <Link href={`/todos/${pvId}`} className="btn-secondary text-xs px-3 py-2 rounded-lg">
              <ClipboardList size={14} />
              Voir les tâches
            </Link>
          )}
        </div>
      </div>

      {/* ═══ Document — Procès-Verbal ═══ */}
      <article className="card-glass border-border-light overflow-hidden shadow-2xl shadow-black/40">
        {/* ── Hero header ── */}
        <header className={`relative border-b border-border bg-gradient-to-br ${theme.soft} to-transparent`}>
          <div className={`h-1 w-full bg-gradient-to-r ${theme.gradient}`} />
          <div className="px-6 md:px-8 py-7">
            <div className="flex items-start justify-between flex-wrap gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2.5 mb-3 flex-wrap">
                  <span className={`badge ${isTech ? 'badge-tech' : 'badge-commercial'}`}>
                    {pv.call_type}
                  </span>
                  <span className="text-xs text-text-dim font-mono flex items-center gap-1.5">
                    <Hash size={11} />
                    {pv.pv_id}
                  </span>
                </div>
                <h1 className="text-2xl md:text-3xl font-extrabold text-text tracking-tight leading-tight">
                  {pv.subject || 'Procès-Verbal'}
                </h1>
              </div>

              <div className="shrink-0 flex flex-col items-end gap-2">
                <div className="flex items-center gap-2 text-sm text-text-muted">
                  <Calendar size={15} className="text-text-dim" />
                  <span>{formatDateTime(pv.call_date)}</span>
                </div>
                {pv.meeting_created && pv.meeting_datetime && (
                  <span className="badge badge-success">
                    <CalendarCheck size={11} />
                    RDV planifié
                  </span>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* ── Stat tiles ── */}
        <div className="px-6 md:px-8 pt-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile
              icon={<Calendar size={16} />}
              label="Date"
              value={formatDate(pv.call_date)}
              tone={theme.text}
            />
            <StatTile
              icon={<User size={16} />}
              label="Participants"
              value={`${pv.left.name ?? '?'} · ${pv.right.name ?? '?'}${extras.length ? ` +${extras.length}` : ''}`}
              tone={theme.text}
            />
            <StatTile
              icon={<ClipboardList size={16} />}
              label={isTech ? 'Tâches' : 'Actions'}
              value={String(taskCount)}
              tone={theme.text}
            />
            <StatTile
              icon={<CalendarCheck size={16} />}
              label="Réunion"
              value={pv.meeting_created ? 'Planifiée' : 'Aucune'}
              tone={pv.meeting_created ? 'text-success' : 'text-text-muted'}
            />
          </div>
        </div>

        {/* ── Participants ── */}
        <section className="px-6 md:px-8 py-7">
          <SectionHeading
            icon={<User size={14} />}
            title="Participants"
            trailing={
              <span className="text-xs font-semibold text-text-muted">
                {2 + extras.length}
              </span>
            }
          />
          <div className="grid md:grid-cols-[1fr_auto_1fr] gap-3 items-stretch">
            <ParticipantCard participant={pv.left} side="left" />
            <div className="hidden md:flex flex-col items-center justify-center px-1">
              <div className="w-10 h-10 rounded-full bg-bg-tertiary border border-border flex items-center justify-center">
                <PhoneCall size={18} className="text-text-dim" />
              </div>
              <div className="w-px flex-1 bg-border/60 my-1" />
            </div>
            <ParticipantCard participant={pv.right} side="right" />
          </div>

          {extras.length > 0 && (
            <div className="mt-5">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-text-dim mb-3">
                Autres participants
              </p>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {extras.map((p, i) => (
                  <ParticipantCard key={i} participant={p} side={p.side} />
                ))}
              </div>
            </div>
          )}
        </section>

        {/* ── Compte rendu ── */}
        <section className="px-6 md:px-8 py-7 border-t border-border">
          <SectionHeading icon={<MessageSquareText size={14} />} title="Compte Rendu" />
          <div className={`p-5 rounded-xl border ${theme.border} ${theme.soft}`}>
            <p className="text-[15px] leading-relaxed text-text/95 whitespace-pre-wrap">
              {pv.compte_rendu || 'Aucun compte rendu généré.'}
            </p>
          </div>
        </section>

        {/* ── Actions / Todos ── */}
        <section className="px-6 md:px-8 py-7 border-t border-border">
          <SectionHeading
            icon={<ClipboardList size={14} />}
            title={isTech ? 'Tâches à réaliser' : 'Actions'}
            trailing={
              <span className="text-xs font-semibold text-text-muted">{taskCount}</span>
            }
          />

          {taskCount === 0 ? (
            <p className="text-sm text-text-muted py-2">
              Aucune action extraite de cet appel.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-border">
              <table className="w-full">
                <thead>
                  <tr className="bg-bg/60 border-b border-border">
                    <th className="text-left text-[11px] font-semibold text-text-muted uppercase tracking-wider py-3 px-4 w-10">
                      #
                    </th>
                    <th className="text-left text-[11px] font-semibold text-text-muted uppercase tracking-wider py-3 px-4">
                      Tâche
                    </th>
                    <th className="text-left text-[11px] font-semibold text-text-muted uppercase tracking-wider py-3 px-4">
                      Responsable
                    </th>
                    <th className="text-left text-[11px] font-semibold text-text-muted uppercase tracking-wider py-3 px-4">
                      Deadline
                    </th>
                    {isTech && (
                      <>
                        <th className="text-left text-[11px] font-semibold text-text-muted uppercase tracking-wider py-3 px-4">
                          Difficulté
                        </th>
                        <th className="text-left text-[11px] font-semibold text-text-muted uppercase tracking-wider py-3 px-4">
                          Modèle IA
                        </th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {pv.actions.map((action, i) => {
                    const overdue = isOverdue(action.deadline);
                    return (
                      <tr
                        key={i}
                        className={`border-b border-border/40 last:border-0 transition-colors hover:bg-bg/30 ${
                          overdue ? 'bg-danger/[0.03]' : ''
                        }`}
                      >
                        <td className="py-3.5 px-4">
                          <span
                            className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold ${
                              overdue
                                ? 'bg-danger/10 text-danger'
                                : 'bg-bg-tertiary text-text-muted'
                            }`}
                          >
                            {overdue ? <AlertCircle size={14} /> : i + 1}
                          </span>
                        </td>
                        <td className="py-3.5 px-4">
                          <p className="text-sm font-medium text-text">{action.title}</p>
                        </td>
                        <td className="py-3.5 px-4">
                          <span className="inline-flex items-center gap-2 text-sm text-text/80">
                            <span className="w-6 h-6 rounded-md bg-bg-tertiary flex items-center justify-center text-[10px] font-bold text-text-muted">
                              {initials(action.owner)}
                            </span>
                            {action.owner}
                          </span>
                        </td>
                        <td className="py-3.5 px-4">
                          {action.deadline ? (
                            <span
                              className={`text-sm flex items-center gap-1.5 ${
                                overdue ? 'text-danger font-semibold' : 'text-text/80'
                              }`}
                            >
                              <Clock size={12} className={overdue ? 'text-danger' : 'text-text-dim'} />
                              {formatDate(action.deadline)}
                              {overdue && (
                                <span className="ml-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-danger/15 text-danger">
                                  Retard
                                </span>
                              )}
                            </span>
                          ) : (
                            <span className="text-sm text-text-dim">—</span>
                          )}
                        </td>
                        {isTech && (
                          <>
                            <td className="py-3.5 px-4">
                              {action.difficulty ? (
                                <span className={`badge text-[10px] ${difficultyColor(action.difficulty)}`}>
                                  <Gauge size={10} />
                                  {difficultyLabel(action.difficulty)}
                                </span>
                              ) : (
                                <span className="text-sm text-text-dim">—</span>
                              )}
                            </td>
                            <td className="py-3.5 px-4">
                              {action.model_hint ? (
                                <span className="badge text-[10px] bg-bg-tertiary text-text-muted border border-border">
                                  <Cpu size={10} />
                                  {modelHintLabel(action.model_hint)}
                                </span>
                              ) : (
                                <span className="text-sm text-text-dim">—</span>
                              )}
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* ── Meeting ── */}
        <section className="px-6 md:px-8 py-7 border-t border-border">
          <SectionHeading icon={<CalendarCheck size={14} />} title="Rendez-vous" />
          {pv.meeting_created && pv.meeting_datetime ? (
            <div className="flex items-center gap-4 p-5 rounded-xl bg-success/5 border border-success/20">
              <div className="w-12 h-12 rounded-xl bg-success/10 flex items-center justify-center shrink-0">
                <CalendarCheck size={24} className="text-success" />
              </div>
              <div>
                <p className="text-sm font-semibold text-text">Réunion planifiée</p>
                <p className="text-lg font-bold text-success mt-0.5">
                  {formatDateTime(pv.meeting_datetime)}
                </p>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-4 p-5 rounded-xl bg-bg border border-border/60">
              <div className="w-12 h-12 rounded-xl bg-bg-tertiary flex items-center justify-center shrink-0">
                <Calendar size={22} className="text-text-dim" />
              </div>
              <p className="text-sm text-text-muted">
                Aucun rendez-vous planifié durant cet appel.
              </p>
            </div>
          )}
        </section>

        {/* ── Footer ── */}
        <footer className="px-6 md:px-8 py-5 border-t border-border bg-bg/40">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <span className="text-xs text-text-dim font-mono">PV ID: {pv.pv_id}</span>
            <details className="group">
              <summary className="text-xs text-text-muted cursor-pointer hover:text-text transition-colors flex items-center gap-1.5 select-none">
                <Braces size={13} />
                Voir le JSON brut
              </summary>
              <pre className="mt-3 p-4 rounded-lg bg-bg border border-border text-xs text-text/80 overflow-x-auto max-h-96 overflow-y-auto scrollbar-thin font-mono">
                {JSON.stringify(pv, null, 2)}
              </pre>
            </details>
          </div>
        </footer>
      </article>
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────

function SectionHeading({
  icon,
  title,
  trailing,
}: {
  icon: React.ReactNode;
  title: string;
  trailing?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="section-title !mb-0 flex items-center gap-2">{icon}{title}</h2>
      {trailing}
    </div>
  );
}

function StatTile({
  icon,
  label,
  value,
  tone = 'text-text',
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="p-3.5 rounded-xl bg-bg border border-border/60">
      <div className="flex items-center gap-2 mb-1.5 text-text-dim">
        {icon}
        <span className="text-[10px] font-semibold uppercase tracking-wider">{label}</span>
      </div>
      <p className={`text-sm font-semibold truncate ${tone}`}>{value}</p>
    </div>
  );
}

function ParticipantCard({
  participant,
  side,
}: {
  participant: {
    name: string;
    phone_number: string | null;
    role: string;
    side: 'left' | 'right';
  };
  side: 'left' | 'right';
}) {
  const isLeft = side === 'left';
  return (
    <div className={`flex flex-col p-5 rounded-xl border ${isLeft ? 'border-accent/25 bg-accent/[0.04]' : 'border-tech/25 bg-tech/[0.04]'}`}>
      <div className="flex items-center gap-3.5">
        <div
          className={`w-12 h-12 rounded-xl flex items-center justify-center text-base font-bold shrink-0 ${
            isLeft ? 'bg-accent/15 text-accent-bright' : 'bg-tech/15 text-tech'
          }`}
        >
          {initials(participant.name)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-base font-bold text-text truncate">{participant.name || 'Inconnu'}</p>
          <p className="text-xs text-text-muted flex items-center gap-1.5 mt-0.5 truncate">
            <Briefcase size={11} />
            {participant.role || '—'}
          </p>
        </div>
        <span className={`badge text-[10px] ${isLeft ? 'bg-accent/10 text-accent-bright border border-accent/20' : 'bg-tech/10 text-tech border border-tech/20'}`}>
          {isLeft ? 'Ora Telecom' : 'Externe'}
        </span>
      </div>
      <div className="mt-3 pt-3 border-t border-border/60">
        {participant.phone_number ? (
          <a
            href={`tel:${participant.phone_number}`}
            className="inline-flex items-center gap-1.5 text-xs text-text-muted hover:text-text transition-colors"
          >
            <Phone size={11} />
            {participant.phone_number}
          </a>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs text-text-dim">
            <Phone size={11} />
            Téléphone non renseigné
          </span>
        )}
      </div>
    </div>
  );
}
