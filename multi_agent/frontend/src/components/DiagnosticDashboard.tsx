import React, { useState } from 'react';
import type {
  DiagnoseApiResponse,
  IncidentState,
  KubectlCommand,
  TroubleshootingPlan,
} from '../types';
import { CommandBlock } from './CommandBlock';

const API_BASE_URL = 'http://localhost:8000';

const SAMPLE_INCIDENTS = [
  {
    label: 'OOMKilled (Exit Code 137)',
    logs: 'Pod payment-service-7f8b9c6d4-x92lk in namespace prod is in CrashLoopBackOff. Last State: Terminated (Reason: OOMKilled, Exit Code: 137). Memory limit: 512Mi.',
  },
  {
    label: 'CoreDNS CrashLoopBackOff',
    logs: 'Pod coredns-76f75df574-zp9kx in kube-system stuck in CrashLoopBackOff: plugin/loop: Loop (127.0.0.1:55953 -> :53) detected for zone "." after ConfigMap update.',
  },
  {
    label: 'ImagePullBackOff (Registry Auth)',
    logs: 'Failed to pull image "us-central1-docker.pkg.dev/prod-proj/containers/checkout-api:v2.4.1": rpc error: code = Unknown desc = failed to pull and unpack image: 403 Forbidden.',
  },
];

function isSafeHttpUrl(candidate: string): boolean {
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:';
  } catch {
    return false;
  }
}

export const DiagnosticDashboard: React.FC = () => {
  const [incidentLogs, setIncidentLogs] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [incidentState, setIncidentState] = useState<IncidentState | null>(null);
  const [troubleshootingPlan, setTroubleshootingPlan] =
    useState<TroubleshootingPlan | null>(null);
  const [feedbackRating, setFeedbackRating] = useState<
    'thumbs_up' | 'thumbs_down' | null
  >(null);
  const [feedbackStatus, setFeedbackStatus] = useState<string | null>(null);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState<boolean>(false);

  const handleDiagnoseSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedLogs = incidentLogs.trim();
    if (!trimmedLogs) {
      setError('Please paste Kubernetes crash logs or describe the cluster anomaly.');
      return;
    }

    setLoading(true);
    setError(null);
    setFeedbackRating(null);
    setFeedbackStatus(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/diagnose`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          incident_logs: trimmedLogs,
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(
          `Diagnosis request failed (${response.status}): ${errText || response.statusText}`
        );
      }

      const data: DiagnoseApiResponse = await response.json();

      if (data.success === false || data.error) {
        throw new Error(data.error || 'The diagnosis pipeline returned an error.');
      }

      // Normalize response whether backend returns { plan, state } envelope or flat state/plan
      const resolvedState: IncidentState = data.state || {
        incident_id: data.incident_id || `inc-${Date.now().toString(36)}`,
        raw_logs: trimmedLogs,
        status: 'COMPLETED',
        final_validated_command: data.plan?.steps || data.steps || [],
        source_citations:
          data.plan?.source_citations || data.source_citations || [],
        plan: data.plan || null,
      };

      const resolvedSteps: KubectlCommand[] =
        data.plan?.steps ||
        data.steps ||
        resolvedState.final_validated_command ||
        [];

      const resolvedCitations: string[] =
        data.plan?.source_citations ||
        data.source_citations ||
        resolvedState.source_citations ||
        [];

      const resolvedSummary: string =
        data.plan?.problem_summary ||
        data.problem_summary ||
        (typeof resolvedState.metadata?.problem_summary === 'string'
          ? resolvedState.metadata.problem_summary
          : '') ||
        `Root-cause analysis completed for incident ${resolvedState.incident_id || 'session'}.`;

      setIncidentState(resolvedState);
      setTroubleshootingPlan({
        problem_summary: resolvedSummary,
        steps: resolvedSteps,
        source_citations: resolvedCitations,
      });
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : 'Unable to reach the Kubernetes Troubleshooting Copilot backend.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleFeedback = async (rating: 'thumbs_up' | 'thumbs_down') => {
    setFeedbackSubmitting(true);
    setFeedbackRating(rating);
    setFeedbackStatus(null);

    const activeIncidentId =
      incidentState?.incident_id || `inc-${Date.now().toString(36)}`;

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/feedback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          incident_id: activeIncidentId,
          rating,
          comments:
            rating === 'thumbs_up'
              ? 'SRE verified remediation plan accuracy.'
              : 'SRE flagged remediation plan for review.',
        }),
      });

      if (!response.ok) {
        throw new Error(`Feedback submission failed (${response.status})`);
      }

      setFeedbackStatus(
        rating === 'thumbs_up'
          ? 'Thank you! Positive SRE telemetry recorded to Firestore.'
          : 'Feedback logged. Incident trace flagged for SRE evaluation.'
      );
    } catch {
      setFeedbackStatus(
        'Feedback recorded locally (telemetry endpoint unreachable).'
      );
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  // Check if PlannerAgent Scope Lock was triggered
  const scopeLockTriggered =
    incidentState?.planner_checklist?.some((item) =>
      item.includes('Error: Query is out of scope')
    ) || false;

  return (
    <div className="space-y-8">
      {/* Crash Log Input Form Card */}
      <section
        aria-label="Incident Crash Log Input"
        className="rounded-2xl border border-slate-800 bg-slate-900/90 p-6 shadow-xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-400" />
              Incident Telemetry &amp; Crash Log Analyzer
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Paste raw <code className="text-slate-300">kubectl describe</code>,{' '}
              <code className="text-slate-300">kubectl logs</code>, or pod event
              streams for grounded multi-agent triage.
            </p>
          </div>

          {/* Preset Sample Crash Logs */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400 font-mono">Presets:</span>
            {SAMPLE_INCIDENTS.map((sample) => (
              <button
                key={sample.label}
                type="button"
                onClick={() => {
                  setIncidentLogs(sample.logs);
                  setError(null);
                }}
                className="rounded-md border border-slate-700 bg-slate-800/90 hover:bg-slate-700/80 hover:border-blue-500/50 px-2.5 py-1 text-xs font-mono text-slate-300 transition-colors cursor-pointer"
              >
                {sample.label}
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={handleDiagnoseSubmit} className="space-y-4">
          <div>
            <label htmlFor="incident-logs-textarea" className="sr-only">
              Kubernetes Crash Logs
            </label>
            <textarea
              id="incident-logs-textarea"
              rows={6}
              value={incidentLogs}
              onChange={(e) => setIncidentLogs(e.target.value)}
              placeholder="Paste Kubernetes pod events, CrashLoopBackOff stack traces, or OOMKilled container logs here..."
              className="w-full rounded-xl border border-slate-700 bg-slate-950 p-4 font-mono text-sm text-slate-100 placeholder-slate-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4 text-xs text-slate-400 font-mono">
              <span>Pipeline: PlannerAgent (MCP Search) → ExecutorAgent → SafetyGuardian</span>
            </div>

            <div className="flex items-center gap-3">
              {incidentLogs && (
                <button
                  type="button"
                  onClick={() => {
                    setIncidentLogs('');
                    setError(null);
                  }}
                  className="rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 px-3.5 py-2.5 text-xs font-medium text-slate-300 transition-colors cursor-pointer"
                >
                  Clear
                </button>
              )}
              <button
                type="submit"
                id="diagnose-submit-btn"
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800/60 disabled:cursor-not-allowed px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-blue-900/40 transition-all cursor-pointer"
              >
                {loading ? (
                  <>
                    <span
                      aria-hidden="true"
                      className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
                    />
                    <span>Running Multi-Agent Diagnosis...</span>
                  </>
                ) : (
                  <>
                    <span>⚡ Run Root-Cause Diagnosis</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
      </section>

      {/* Loading Spinner State */}
      {loading && (
        <div
          role="status"
          aria-live="polite"
          className="rounded-2xl border border-blue-500/40 bg-slate-900/90 p-8 text-center shadow-lg"
        >
          <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
          <h3 className="text-base font-semibold text-slate-100">
            Analyzing Incident Telemetry &amp; Querying Vertex AI Search...
          </h3>
          <p className="text-xs text-slate-400 mt-1 font-mono">
            1. PlannerAgent querying k8s-custom-chunks-store → 2. ExecutorAgent
            synthesizing kubectl commands → 3. SafetyGuardian validating risk matrix
          </p>
        </div>
      )}

      {/* Error Alert Banner */}
      {error && !loading && (
        <div
          role="alert"
          className="rounded-xl border-2 border-red-500/80 bg-red-950/50 p-4 text-sm text-red-200"
        >
          <div className="flex items-center gap-2 font-semibold text-red-300 mb-1">
            <span>⚠️ Diagnosis Pipeline Error</span>
          </div>
          <p className="font-mono text-xs text-red-200">{error}</p>
        </div>
      )}

      {/* Diagnosis Results View */}
      {troubleshootingPlan && !loading && (
        <div className="space-y-6">
          {/* Scope Lock Alert if triggered */}
          {scopeLockTriggered && (
            <div
              role="alert"
              className="rounded-xl border-2 border-amber-500 bg-amber-950/50 p-5 text-amber-100"
            >
              <h3 className="text-base font-bold text-amber-300 mb-1">
                🔒 AI Safety Scope Lock Triggered
              </h3>
              <p className="font-mono text-sm">
                {incidentState?.planner_checklist?.[0]}
              </p>
            </div>
          )}

          {/* Problem Summary Banner */}
          <section
            aria-label="Problem Summary"
            className="rounded-2xl border border-slate-800 bg-slate-900/90 p-6 shadow-lg"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <span className="text-xs font-mono uppercase tracking-wider text-blue-400 font-semibold">
                Executive Root-Cause Summary
              </span>
              {incidentState?.incident_id && (
                <span className="rounded-md bg-slate-800 border border-slate-700 px-2.5 py-0.5 text-xs font-mono text-slate-300">
                  ID: {incidentState.incident_id}
                </span>
              )}
            </div>

            <p
              id="problem-summary-text"
              className="text-base text-slate-100 leading-relaxed"
            >
              {troubleshootingPlan.problem_summary}
            </p>

            {/* Planner Checklist Accordion / Pill Summary */}
            {incidentState?.planner_checklist &&
              incidentState.planner_checklist.length > 0 && (
                <div className="mt-4 pt-4 border-t border-slate-800">
                  <h4 className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-2">
                    PlannerAgent Diagnostic Checklist (
                    {incidentState.planner_checklist.length} steps)
                  </h4>
                  <ul className="space-y-1.5 text-xs text-slate-300 font-mono">
                    {incidentState.planner_checklist.map((item, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <span className="text-blue-400">▸</span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
          </section>

          {/* Sequential List of Validated Kubectl CommandBlocks */}
          <section aria-label="Remediation Command Plan" className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-100">
                Safety-Validated <code className="text-blue-400">kubectl</code>{' '}
                Execution Plan ({troubleshootingPlan.steps.length} Steps)
              </h2>
              <div className="flex items-center gap-3 text-xs font-mono">
                <span className="inline-flex items-center gap-1 text-blue-300">
                  <span className="h-2 w-2 rounded-full bg-blue-400" /> LOW
                </span>
                <span className="inline-flex items-center gap-1 text-amber-300">
                  <span className="h-2 w-2 rounded-full bg-amber-400" /> MEDIUM
                </span>
                <span className="inline-flex items-center gap-1 text-red-300">
                  <span className="h-2 w-2 rounded-full bg-red-400" /> HIGH
                </span>
              </div>
            </div>

            <div className="space-y-4">
              {troubleshootingPlan.steps.map((step) => (
                <CommandBlock
                  key={`${step.step_number}-${step.title}`}
                  step={step}
                />
              ))}
            </div>
          </section>

          {/* Grounded Source Citations & SRE Feedback Footer */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Grounded Citations */}
            <section
              aria-label="Kubernetes Documentation Citations"
              className="md:col-span-2 rounded-2xl border border-slate-800 bg-slate-900/90 p-5"
            >
              <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-3">
                📚 Grounded Kubernetes Documentation Citations (Vertex AI Search)
              </h3>
              {troubleshootingPlan.source_citations &&
              troubleshootingPlan.source_citations.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {troubleshootingPlan.source_citations.map((citation, idx) => {
                    // Extract URL if formatted as "Breadcrumb (https://...)"
                    const urlMatch = citation.match(/https?:\/\/[^\s)]+/);
                    const href = urlMatch ? urlMatch[0] : citation;
                    const isValidLink = isSafeHttpUrl(href);

                    return isValidLink ? (
                      <a
                        key={idx}
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 rounded-lg border border-blue-500/40 bg-blue-950/30 hover:bg-blue-900/40 px-3 py-1.5 text-xs font-mono text-blue-300 transition-colors"
                      >
                        <span>🔗</span>
                        <span>{citation}</span>
                      </a>
                    ) : (
                      <span
                        key={idx}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-mono text-slate-300"
                      >
                        <span>📄</span>
                        <span>{citation}</span>
                      </span>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-slate-500 font-mono">
                  No external documentation citations attached to this session.
                </p>
              )}
            </section>

            {/* SRE Feedback Telemetry Box */}
            <section
              aria-label="SRE Diagnosis Feedback"
              className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 flex flex-col justify-between"
            >
              <div>
                <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-1">
                  SRE Evaluation Feedback
                </h3>
                <p className="text-xs text-slate-300 mb-4">
                  Was this troubleshooting plan accurate and safe for your
                  cluster?
                </p>
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    id="feedback-thumbs-up"
                    disabled={feedbackSubmitting}
                    onClick={() => handleFeedback('thumbs_up')}
                    className={`flex-1 inline-flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold transition-all cursor-pointer ${
                      feedbackRating === 'thumbs_up'
                        ? 'border-emerald-500 bg-emerald-950/60 text-emerald-300'
                        : 'border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-200'
                    }`}
                  >
                    <span>👍</span>
                    <span>Thumbs Up</span>
                  </button>

                  <button
                    type="button"
                    id="feedback-thumbs-down"
                    disabled={feedbackSubmitting}
                    onClick={() => handleFeedback('thumbs_down')}
                    className={`flex-1 inline-flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold transition-all cursor-pointer ${
                      feedbackRating === 'thumbs_down'
                        ? 'border-red-500 bg-red-950/60 text-red-300'
                        : 'border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-200'
                    }`}
                  >
                    <span>👎</span>
                    <span>Thumbs Down</span>
                  </button>
                </div>

                {feedbackStatus && (
                  <p className="text-xs font-mono text-emerald-400">
                    {feedbackStatus}
                  </p>
                )}
              </div>
            </section>
          </div>
        </div>
      )}
    </div>
  );
};

export default DiagnosticDashboard;
