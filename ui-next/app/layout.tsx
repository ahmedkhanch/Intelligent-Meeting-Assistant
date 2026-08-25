import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'CRM Vocal — Fallback UI',
  description: 'Ora Telecom — AI-powered call analysis pipeline. Temporary fallback UI for tech call todos and PV display.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body className="min-h-screen">
        {/* Subtle top accent line */}
        <div className="fixed top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-accent via-tech to-commercial z-50" />

        {/* Navigation */}
        <nav className="fixed top-0 left-0 right-0 z-40 bg-bg/80 backdrop-blur-md border-b border-border">
          <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
            <a href="/" className="flex items-center gap-2.5 font-bold text-lg text-text no-underline hover:opacity-80 transition-opacity">
              <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-accent to-tech flex items-center justify-center text-white text-xs">CV</span>
              <span>CRM Vocal</span>
            </a>
            <div className="flex items-center gap-1">
              <a href="/todos" className="btn-ghost text-sm px-3 py-2 rounded-lg">
                Todos
              </a>
              <a href="/pvs" className="btn-ghost text-sm px-3 py-2 rounded-lg">
                PVs
              </a>
              <span className="ml-3 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-warning/10 text-warning border border-warning/20">
                Fallback
              </span>
            </div>
          </div>
        </nav>

        {/* Main content — offset for fixed nav */}
        <main className="pt-16 pb-12">
          {children}
        </main>
      </body>
    </html>
  );
}
