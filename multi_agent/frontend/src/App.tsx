import React from 'react';
import { DiagnosticDashboard } from './components/DiagnosticDashboard';

export const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top SRE Command Bar Header */}
      <header className="border-b border-slate-800/90 bg-slate-900/95 backdrop-blur sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="h-10 w-10 rounded-xl bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400 font-mono font-bold text-lg shadow-inner">
              ⎈
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-xl font-bold tracking-tight text-slate-100">
                  Kubernetes Troubleshooting Copilot
                </h1>
                <span className="rounded-full bg-emerald-500/15 border border-emerald-500/40 px-2.5 py-0.5 text-xs font-mono font-semibold text-emerald-300">
                  ADK v2.6 + Gemini 2.5 Pro
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono">
                Grounded SRE Root-Cause Triage • Vertex AI Search MCP •
                Deterministic Safety Guardian
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs font-mono text-slate-400">
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-950 px-3 py-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>SafetyGuardian: ACTIVE</span>
            </span>
          </div>
        </div>
      </header>

      {/* Main Dashboard Content */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-8">
        <DiagnosticDashboard />
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 py-4 text-center text-xs font-mono text-slate-500">
        Kubernetes Troubleshooting Copilot • Decoupled Planner-Executor
        Architecture with Strict Pydantic Validation
      </footer>
    </div>
  );
};

export default App;
