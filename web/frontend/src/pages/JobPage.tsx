import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getJob, getVideoUrl, getEditJson, rerender } from '../api/client';
import { StepTracker } from '../components/StepTracker';
import { LogViewer } from '../components/LogViewer';
import type { Job } from '../types/scenario';

export function JobPage(): React.JSX.Element {
  const { id } = useParams<{ id: string }>();

  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [scenarioOpen, setScenarioOpen] = useState(false);
  const [editJson, setEditJson] = useState<Record<string, unknown> | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [rerendering, setRerendering] = useState(false);

  const fetchJob = useCallback(async () => {
    if (!id) return;

    try {
      const data = await getJob(id);
      setJob(data);
      setError(null);

      if (data.status === 'failed') {
        setLogOpen(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch job');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchJob();
  }, [fetchJob]);

  useEffect(() => {
    if (!job || job.status === 'done' || job.status === 'failed') return;

    const interval = setInterval(fetchJob, 2000);
    return () => clearInterval(interval);
  }, [job?.status, fetchJob]);

  const handleLoadEditJson = useCallback(async () => {
    if (!id || editJson) {
      setEditOpen((prev) => !prev);
      return;
    }

    try {
      const data = await getEditJson(id);
      setEditJson(data);
      setEditOpen(true);
    } catch {
      setEditJson({ error: 'Failed to load edit.json' });
      setEditOpen(true);
    }
  }, [id, editJson]);

  const handleRerender = useCallback(async () => {
    if (!id || rerendering) return;

    setRerendering(true);
    try {
      await rerender(id);
      setEditJson(null);
      setEditOpen(false);
      setLogOpen(false);
      setLoading(true);
      await fetchJob();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rerender');
    } finally {
      setRerendering(false);
    }
  }, [id, rerendering, fetchJob]);

  if (loading && !job) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex items-center gap-3 text-gray-500">
          <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span className="text-sm">Loading job...</span>
        </div>
      </div>
    );
  }

  if (error && !job) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="bg-white rounded-xl shadow-sm border border-red-200 p-12 text-center">
          <h1 className="text-xl font-semibold text-red-600 mb-2">Error</h1>
          <p className="text-gray-500">{error}</p>
          <Link to="/history" className="inline-block mt-4 text-sm text-blue-600 hover:text-blue-800">
            Back to History
          </Link>
        </div>
      </div>
    );
  }

  if (!job) return <></>;

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/history"
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        Back to History
      </Link>

      {/* Main card */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-800">
              {job.title || 'Untitled Job'}
            </h1>
            <p className="text-sm text-gray-400 mt-1">
              {job.id}
            </p>
            <div className="mt-2 flex items-center gap-2">
              <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">
                {job.inputMode === 'auto' ? 'AI-assisted mode' : 'Manual scenario'}
              </span>
              {job.languageHint && (
                <span className="inline-flex items-center rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                  Language hint: {job.languageHint}
                </span>
              )}
            </div>
          </div>
          <StatusBadge status={job.status} />
        </div>

        {/* Step Tracker */}
        <div className="px-4">
          <StepTracker currentStep={job.currentStep} status={job.status} />
        </div>

        {/* Elapsed / Duration info */}
        {job.status === 'running' && job.startedAt && (
          <p className="text-sm text-gray-500 text-center">
            Running since {formatTime(job.startedAt)}
          </p>
        )}
        {job.status === 'done' && job.duration != null && (
          <p className="text-sm text-gray-500 text-center">
            Completed in {formatDuration(job.duration)}
          </p>
        )}

        {/* Log Viewer */}
        <LogViewer log={job.log} isOpen={logOpen} onToggle={() => setLogOpen((v) => !v)} />

        {job.scenario && (
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            <button
              type="button"
              onClick={() => setScenarioOpen((prev) => !prev)}
              className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <span>Scenario JSON</span>
              <svg
                className={`w-4 h-4 transition-transform ${scenarioOpen ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {scenarioOpen && (
              <pre
                className="px-4 py-3 text-sm text-gray-300 font-mono whitespace-pre-wrap break-words overflow-y-auto border-t border-gray-200"
                style={{ backgroundColor: '#1a1a2e', maxHeight: '320px' }}
              >
                {JSON.stringify(job.scenario, null, 2)}
              </pre>
            )}
          </div>
        )}

        {/* Done: Video player + download */}
        {job.status === 'done' && job.hasVideo && (
          <div className="space-y-4">
            <video
              src={getVideoUrl(job.id)}
              controls
              className="w-full rounded-lg"
            />

            <div className="flex items-center gap-3">
              <a
                href={getVideoUrl(job.id)}
                download
                className="inline-flex items-center gap-2 px-4 py-2 bg-[#c8102e] hover:bg-[#a00d24] text-white text-sm font-medium rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Download Video
              </a>
              {job.fileSize > 0 && (
                <span className="text-sm text-gray-400">
                  {formatFileSize(job.fileSize)}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Done: Edit JSON viewer */}
        {job.status === 'done' && job.hasEdit && (
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            <button
              type="button"
              onClick={handleLoadEditJson}
              className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <span>Edit JSON</span>
              <svg
                className={`w-4 h-4 transition-transform ${editOpen ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {editOpen && editJson && (
              <pre
                className="px-4 py-3 text-sm text-gray-300 font-mono whitespace-pre-wrap break-words overflow-y-auto border-t border-gray-200"
                style={{ backgroundColor: '#1a1a2e', maxHeight: '400px' }}
              >
                {JSON.stringify(editJson, null, 2)}
              </pre>
            )}

            {editOpen && (
              <div className="px-4 py-3 border-t border-gray-200 bg-gray-50">
                <button
                  type="button"
                  onClick={handleRerender}
                  disabled={rerendering}
                  className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                    rerendering
                      ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      : 'bg-blue-600 hover:bg-blue-700 text-white'
                  }`}
                >
                  {rerendering ? 'Re-rendering...' : 'Re-render'}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Failed: Error message */}
        {job.status === 'failed' && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <svg className="w-5 h-5 text-red-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <h3 className="text-sm font-medium text-red-800">Pipeline Failed</h3>
                <p className="text-sm text-red-600 mt-1">
                  The video generation pipeline failed at step {job.currentStep}.
                  Check the logs above for details.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }): React.JSX.Element {
  const styles: Record<string, string> = {
    queued: 'bg-yellow-100 text-yellow-800',
    running: 'bg-blue-100 text-blue-800',
    done: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
  };

  return (
    <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${styles[status] ?? 'bg-gray-100 text-gray-800'}`}>
      {status}
    </span>
  );
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
