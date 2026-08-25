'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ClipboardList, FileText, Activity, ArrowRight, Zap } from 'lucide-react';
import { checkHealth } from '@/lib/api';

export default function HomePage() {
  const [health, setHealth] = useState<{
    status: string;
    version: string;
    deepseek_configured: boolean;
  } | null>(null);

  useEffect(() => {
    checkHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <div className="max-w-6xl mx-auto px-4 animate-fade-in">
      {/* Hero */}
      <div className="relative text-center py-12 md:py-16">
        {/* Soft glow behind the title */}
        <div
          aria-hidden
          className="pointer-events-none absolute left-1/2 top-0 -translate-x-1/2 w-[520px] h-[320px] rounded-full bg-accent/20 blur-[120px]"
        />
        <div className="relative">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-warning/10 border border-warning/20 text-warning text-xs font-semibold uppercase tracking-wider mb-4">
            <Zap size={14} />
            Phase 1 — Fallback UI
          </div>
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight mb-3">
            <span className="text-gradient">CRM Vocal</span>
          </h1>
          <p className="text-text-muted text-lg max-w-lg mx-auto">
            Analyse de appels pilotée par IA. Les PVs tech atterrissent ici en attendant
            l&apos;intégration Ora Studio.
          </p>
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-center gap-6 mb-12 text-sm text-text-muted">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${health ? 'bg-success animate-pulse-soft' : 'bg-danger'}`} />
          <span>API {health?.status || 'offline'}</span>
        </div>
        <span>·</span>
        <div className="flex items-center gap-2">
          <Activity size={14} />
          <span>v{health?.version || '—'}</span>
        </div>
      </div>

      {/* Navigation cards */}
      <div className="grid md:grid-cols-2 gap-5 max-w-2xl mx-auto">
        {/* Todo list card */}
        <Link
          href="/todos"
          className="card group hover:border-tech/30 hover:shadow-lg hover:shadow-tech/5 transition-all duration-300 no-underline"
        >
          <div className="flex items-start justify-between mb-3">
            <div className="w-10 h-10 rounded-xl bg-tech/10 flex items-center justify-center">
              <ClipboardList size={22} className="text-tech" />
            </div>
            <ArrowRight
              size={18}
              className="text-text-dim group-hover:text-tech transition-colors group-hover:translate-x-0.5"
            />
          </div>
          <h2 className="text-lg font-bold text-text mb-1">Liste des Tâches</h2>
          <p className="text-sm text-text-muted leading-relaxed">
            Les todos extraits des appels tech. Difficulté, deadline, modèle IA
            recommandé — tout au même endroit.
          </p>
          <div className="mt-4 flex items-center gap-2">
            <span className="badge badge-tech">#appel-tech</span>
            <span className="text-xs text-text-dim">Fallback Ora Studio</span>
          </div>
        </Link>

        {/* PV card */}
        <Link
          href="/pvs"
          className="card group hover:border-accent/30 hover:shadow-lg hover:shadow-accent/5 transition-all duration-300 no-underline"
        >
          <div className="flex items-start justify-between mb-3">
            <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
              <FileText size={22} className="text-accent-bright" />
            </div>
            <ArrowRight
              size={18}
              className="text-text-dim group-hover:text-accent-bright transition-colors group-hover:translate-x-0.5"
            />
          </div>
          <h2 className="text-lg font-bold text-text mb-1">Procès-Verbaux</h2>
          <p className="text-sm text-text-muted leading-relaxed">
            Les comptes rendus complets avec participants, résumé IA, actions,
            et informations de rendez-vous.
          </p>
          <div className="mt-4 flex items-center gap-2">
            <span className="badge badge-tech">#appel-tech</span>
            <span className="badge badge-commercial">#appel-commercial</span>
          </div>
        </Link>
      </div>

      {/* Footer note */}
      <p className="text-center text-xs text-text-dim mt-10">
        Cette UI est temporaire — elle remplace le routage vers Ora Studio en
        attendant l&apos;intégration.
      </p>
    </div>
  );
}
