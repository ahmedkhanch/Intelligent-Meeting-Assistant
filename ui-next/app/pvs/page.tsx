'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import {
  FileText,
  Calendar,
  User,
  ChevronRight,
  ArrowLeft,
  RefreshCw,
  Filter,
  ClipboardList,
  CalendarCheck,
  PhoneCall,
} from 'lucide-react';
import { listPVs, PVSummary } from '@/lib/api';
import { formatDate, formatRelativeTime, shortId, initials } from '@/lib/utils';
import { EmptyState } from '@/components/EmptyState';
import { LoadingSkeleton } from '@/components/LoadingSkeleton';
import { ErrorBanner } from '@/components/ErrorBanner';

export default function PVsPage() {
  const [pvs, setPVs] = useState<PVSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | '#appel-tech' | '#appel-commercial'>('all');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listPVs();
      setPVs(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Impossible de charger les PVs');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const filtered = filter === 'all' ? pvs : pvs.filter((p) => p.call_type === filter);

  const techCount = pvs.filter((p) => p.call_type === '#appel-tech').length;
  const commercialCount = pvs.filter((p) => p.call_type === '#appel-commercial').length;

  return (
    <div className="max-w-4xl mx-auto px-4 animate-fade-in pb-12">
      {/* Header */}
      <div className="flex items-center gap-3 mb-2">
        <Link href="/" className="btn-ghost p-2 rounded-lg">
          <ArrowLeft size={18} />
        </Link>
        <div>
          <h1 className="text-2xl font-extrabold text-text flex items-center gap-3">
            <FileText size={24} className="text-accent-bright" />
            Procès-Verbaux
          </h1>
          <p className="text-sm text-text-muted mt-0.5">
            {pvs.length} PV{pvs.length !== 1 ? 's' : ''} stocké{pvs.length !== 1 ? 's' : ''}
            {techCount > 0 && ` · ${techCount} tech`}
            {commercialCount > 0 && ` · ${commercialCount} commercial`}
          </p>
        </div>
        <button onClick={fetchData} className="btn-ghost p-2 rounded-lg ml-auto" title="Rafraîchir">
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Filter pills */}
      {pvs.length > 0 && (
        <div className="flex items-center gap-2 mt-4 mb-6">
          <Filter size={14} className="text-text-dim" />
          {(['all', '#appel-tech', '#appel-commercial'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
                filter === f
                  ? 'bg-accent text-white shadow-md shadow-accent/20'
                  : 'bg-bg-tertiary text-text-muted hover:text-text border border-border'
              }`}
            >
              {f === 'all' ? 'Tous' : f}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      {error ? (
        <ErrorBanner message={error} onRetry={fetchData} />
      ) : loading ? (
        <LoadingSkeleton count={4} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<FileText size={28} />}
          title="Aucun PV"
          description={
            filter !== 'all'
              ? 'Aucun PV ne correspond à ce filtre.'
              : 'Les Procès-Verbaux apparaîtront ici après le traitement d\'un appel.'
          }
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((pv) => {
            const isTech = pv.call_type === '#appel-tech';
            return (
              <Link
                key={pv.pv_id}
                href={`/pvs/${pv.pv_id}`}
                className={`card flex items-center gap-4 no-underline group cursor-pointer hover:shadow-lg transition-all duration-200 overflow-hidden relative ${
                  isTech ? 'hover:border-tech/30 hover:shadow-tech/5' : 'hover:border-commercial/30 hover:shadow-commercial/5'
                }`}
              >
                {/* Call-type accent edge */}
                <span
                  className={`absolute left-0 top-0 bottom-0 w-1 ${
                    isTech ? 'bg-gradient-to-b from-tech to-tech/40' : 'bg-gradient-to-b from-commercial to-commercial/40'
                  }`}
                />

                {/* Icon */}
                <div
                  className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 ml-1 ${
                    isTech ? 'bg-tech/10 text-tech' : 'bg-commercial/10 text-commercial'
                  }`}
                >
                  <FileText size={20} />
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className={`badge text-[10px] ${isTech ? 'badge-tech' : 'badge-commercial'}`}>
                      {pv.call_type}
                    </span>
                    <span className="text-xs text-text-dim font-mono">{shortId(pv.pv_id)}</span>
                    {pv.stored_at && (
                      <span className="text-xs text-text-dim">{formatRelativeTime(pv.stored_at)}</span>
                    )}
                  </div>
                  <h3 className="text-base font-semibold text-text group-hover:text-text transition-colors truncate">
                    {pv.subject || 'Sans sujet'}
                  </h3>
                  <div className="flex items-center gap-4 mt-1.5 text-xs text-text-muted flex-wrap">
                    <span className="flex items-center gap-1.5">
                      <PhoneCall size={11} />
                      <span className="flex items-center gap-1">
                        <b className="font-semibold text-text/80">{pv.left || '?'}</b>
                        <span className="text-text-dim">↔</span>
                        <b className="font-semibold text-text/80">{pv.right || '?'}</b>
                        {pv.additional_participants && pv.additional_participants.length > 0 && (
                          <span className="text-text-dim">+{pv.additional_participants.length}</span>
                        )}
                      </span>
                    </span>
                    <span className="flex items-center gap-1">
                      <Calendar size={11} />
                      {formatDate(pv.call_date)}
                    </span>
                    {pv.task_count > 0 && (
                      <span className="flex items-center gap-1">
                        <ClipboardList size={11} />
                        {pv.task_count} tâche{pv.task_count > 1 ? 's' : ''}
                      </span>
                    )}
                    {pv.meeting_created && (
                      <span className="flex items-center gap-1 text-success">
                        <CalendarCheck size={11} />
                        RDV
                      </span>
                    )}
                  </div>
                </div>

                <ChevronRight
                  size={18}
                  className={`text-text-dim transition-colors shrink-0 ${
                    isTech ? 'group-hover:text-tech' : 'group-hover:text-commercial'
                  }`}
                />
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
