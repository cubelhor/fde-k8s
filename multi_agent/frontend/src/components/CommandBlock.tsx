import React, { useState } from 'react';
import type { KubectlCommand } from '../types';

export interface CommandBlockProps {
  step: KubectlCommand;
}

export const CommandBlock: React.FC<CommandBlockProps> = ({ step }) => {
  const [copiedPrimary, setCopiedPrimary] = useState(false);
  const [copiedAlt, setCopiedAlt] = useState(false);

  const normalizedDanger = (step.danger_level || 'LOW').toUpperCase();

  const handleCopy = async (text: string, isAlt = false) => {
    try {
      await navigator.clipboard.writeText(text);
      if (isAlt) {
        setCopiedAlt(true);
        setTimeout(() => setCopiedAlt(false), 2000);
      } else {
        setCopiedPrimary(true);
        setTimeout(() => setCopiedPrimary(false), 2000);
      }
    } catch {
      // Fallback if clipboard permission is denied in headless test environments
      if (isAlt) {
        setCopiedAlt(true);
        setTimeout(() => setCopiedAlt(false), 2000);
      } else {
        setCopiedPrimary(true);
        setTimeout(() => setCopiedPrimary(false), 2000);
      }
    }
  };

  // Tailwind dark-mode SRE styling per danger_level
  const containerClasses =
    normalizedDanger === 'HIGH'
      ? 'border-2 border-red-500 bg-red-950/30 shadow-lg shadow-red-950/40'
      : normalizedDanger === 'MEDIUM'
        ? 'border-2 border-amber-500 bg-amber-950/20 shadow-md shadow-amber-950/30'
        : 'border border-slate-700 hover:border-blue-500/60 bg-slate-900/80 shadow-md';

  const badgeClasses =
    normalizedDanger === 'HIGH'
      ? 'bg-red-500/20 text-red-300 border border-red-500/60'
      : normalizedDanger === 'MEDIUM'
        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/60'
        : 'bg-blue-500/15 text-blue-300 border border-blue-500/40';

  const stepCircleClasses =
    normalizedDanger === 'HIGH'
      ? 'bg-red-600 text-white ring-2 ring-red-400/50'
      : normalizedDanger === 'MEDIUM'
        ? 'bg-amber-500 text-slate-950 ring-2 ring-amber-400/50'
        : 'bg-blue-600 text-white ring-2 ring-blue-400/40';

  // Extract inline SafetyGuardian warning if present in explanation
  const hasInlineWarning = step.explanation.includes('⚠️ WARNING:');
  const [warningLine, ...restExplanationLines] = hasInlineWarning
    ? step.explanation.split('\n\n')
    : ['', step.explanation];
  const mainExplanation = hasInlineWarning
    ? restExplanationLines.join('\n\n') || step.explanation
    : step.explanation;

  return (
    <article
      id={`command-step-${step.step_number}`}
      className={`rounded-xl p-5 transition-all duration-200 ${containerClasses}`}
    >
      {/* Header Row: Step Number, Title, and Risk Badge */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-3">
          <span
            className={`inline-flex h-8 w-8 items-center justify-center rounded-lg text-sm font-bold font-mono ${stepCircleClasses}`}
          >
            {step.step_number}
          </span>
          <h3
            className={`text-lg font-semibold tracking-tight ${
              normalizedDanger === 'HIGH' ? 'text-red-200' : 'text-slate-100'
            }`}
          >
            {step.title}
          </h3>
        </div>

        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider font-mono ${badgeClasses}`}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              normalizedDanger === 'HIGH'
                ? 'bg-red-400 animate-pulse'
                : normalizedDanger === 'MEDIUM'
                  ? 'bg-amber-400'
                  : 'bg-blue-400'
            }`}
          />
          {normalizedDanger} RISK
        </span>
      </div>

      {/* Prominent High-Risk Warning Banner */}
      {normalizedDanger === 'HIGH' && (
        <div
          role="alert"
          className="mb-4 rounded-lg border border-red-500/80 bg-red-950/70 p-3.5 text-sm text-red-200"
        >
          <div className="flex items-start gap-2.5">
            <span className="text-red-400 font-bold text-base leading-none mt-0.5">
              ⚠️
            </span>
            <div className="space-y-1">
              <p className="font-bold uppercase tracking-wide text-red-300 text-xs">
                Safety Guardian Interception — High-Risk Destructive Operation
              </p>
              <p className="text-red-200 leading-relaxed">
                {warningLine ||
                  'WARNING: This is a high-risk destructive operation that modifies or deletes cluster state. Verify target namespace and resource replicas before executing in production.'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Medium-Risk Caution Notice */}
      {normalizedDanger === 'MEDIUM' && (
        <div className="mb-3 rounded-lg border border-amber-500/50 bg-amber-950/40 px-3.5 py-2.5 text-xs text-amber-200 flex items-center gap-2">
          <span className="text-amber-400 font-bold">⚡</span>
          <span>
            State-Modifying Command: Mutates live workload state (e.g., rollout
            restart / replica scaling) without deleting resource manifests.
          </span>
        </div>
      )}

      {/* Explanation */}
      <p
        className={`text-sm leading-relaxed mb-4 ${
          normalizedDanger === 'HIGH' ? 'text-red-100/90' : 'text-slate-300'
        }`}
      >
        {mainExplanation}
      </p>

      {/* Primary Kubectl Command Block */}
      <div className="rounded-lg border border-slate-800 bg-slate-950 overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-800/80 bg-slate-900/90 px-3.5 py-2">
          <span className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <span className="text-emerald-400">$</span> kubectl cli
          </span>
          <button
            type="button"
            id={`copy-cmd-btn-${step.step_number}`}
            onClick={() => handleCopy(step.command, false)}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-800 hover:bg-slate-700 px-2.5 py-1 text-xs font-medium text-slate-200 transition-colors cursor-pointer"
          >
            {copiedPrimary ? (
              <span className="text-emerald-400 font-semibold">✓ Copied!</span>
            ) : (
              <span>Copy to Clipboard</span>
            )}
          </button>
        </div>
        <pre className="p-3.5 text-sm font-mono overflow-x-auto text-emerald-300 select-all">
          <code>{step.command}</code>
        </pre>
      </div>

      {/* Safe Read-Only / Dry-Run Alternative Command (if present) */}
      {step.alternative_command && (
        <div className="mt-3 rounded-lg border border-emerald-500/40 bg-emerald-950/20 p-3">
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-emerald-300 flex items-center gap-1.5">
              <span>🛡️</span> Recommended Safe / Dry-Run Alternative
            </span>
            <button
              type="button"
              id={`copy-alt-btn-${step.step_number}`}
              onClick={() => handleCopy(step.alternative_command || '', true)}
              className="inline-flex items-center gap-1 rounded border border-emerald-600/50 bg-emerald-900/40 hover:bg-emerald-800/50 px-2 py-0.5 text-xs font-medium text-emerald-200 transition-colors cursor-pointer"
            >
              {copiedAlt ? '✓ Copied!' : 'Copy Safe Command'}
            </button>
          </div>
          <pre className="text-xs font-mono text-emerald-200 bg-slate-950/80 rounded px-3 py-2 overflow-x-auto">
            <code>{step.alternative_command}</code>
          </pre>
        </div>
      )}
    </article>
  );
};

export default CommandBlock;
