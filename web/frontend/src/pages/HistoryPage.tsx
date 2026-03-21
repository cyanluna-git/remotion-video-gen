import { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { getJobs, deleteJob } from '../api/client';
import { JobCard } from '../components/JobCard';
import type { JobSummary, JobStatus } from '../types/scenario';

type FilterTab = 'all' | 'done' | 'running' | 'failed';

const POLL_INTERVAL = 5000;

const TAB_CONFIG: { key: FilterTab; label: string; match: (s: JobStatus) => boolean }[] = [
  { key: 'all', label: 'All', match: () => true },
  { key: 'done', label: 'Done', match: (s) => s === 'done' },
  { key: 'running', label: 'Running', match: (s) => s === 'running' || s === 'queued' },
  { key: 'failed', label: 'Failed', match: (s) => s === 'failed' },
];

function hasActiveJobs(jobs: JobSummary[]): boolean {
  return jobs.some((j) => j.status === 'running' || j.status === 'queued');
}

export function HistoryPage(): React.JSX.Element {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [activeTab, setActiveTab] = useState<FilterTab>('all');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const shouldPollRef = useRef(false);

  const fetchJobs = useCallback(async () => {
    try {
      const data = await getJobs();
      setJobs(data);
      setError(null);
      shouldPollRef.current = hasActiveJobs(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load jobs';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchJobs();

    intervalRef.current = setInterval(() => {
      if (shouldPollRef.current) {
        void fetchJobs();
      }
    }, POLL_INTERVAL);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchJobs]);

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await deleteJob(id);
        setJobs((prev) => prev.filter((j) => j.id !== id));
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to delete job';
        setError(message);
      }
    },
    [],
  );

  const tabConfig = TAB_CONFIG;
  const currentFilter = tabConfig.find((t) => t.key === activeTab);
  const filteredJobs = currentFilter
    ? jobs.filter((j) => currentFilter.match(j.status))
    : jobs;

  const tabCounts = tabConfig.reduce<Record<FilterTab, number>>(
    (acc, tab) => {
      acc[tab.key] = jobs.filter((j) => tab.match(j.status)).length;
      return acc;
    },
    { all: 0, done: 0, running: 0, failed: 0 },
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <svg
            className="w-8 h-8 animate-spin text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <p className="text-sm text-gray-500">Loading jobs...</p>
        </div>
      </div>
    );
  }

  if (error && jobs.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="bg-white rounded-xl shadow-sm border border-red-200 p-8 text-center max-w-md">
          <svg
            className="w-10 h-10 text-red-400 mx-auto mb-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
            />
          </svg>
          <h2 className="text-lg font-semibold text-gray-800 mb-1">
            Failed to load jobs
          </h2>
          <p className="text-sm text-gray-500 mb-4">{error}</p>
          <button
            type="button"
            onClick={() => {
              setIsLoading(true);
              void fetchJobs();
            }}
            className="px-4 py-2 bg-[#c8102e] text-white text-sm font-medium rounded-lg hover:bg-[#a00d24] transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-800">
            Video History
          </h1>
          <p className="text-gray-500 mt-1">
            {jobs.length} {jobs.length === 1 ? 'video' : 'videos'} total
          </p>
        </div>
        <Link
          to="/"
          className="px-4 py-2 bg-[#c8102e] text-white text-sm font-medium rounded-lg hover:bg-[#a00d24] transition-colors"
        >
          + New Video
        </Link>
      </div>

      {/* Error banner (non-blocking) */}
      {error && jobs.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center gap-2 text-sm text-red-700">
          <svg className="w-4 h-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clipRule="evenodd"
            />
          </svg>
          {error}
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {tabConfig.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'border-[#c8102e] text-[#c8102e]'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {tab.label}
            <span
              className={`ml-1.5 px-1.5 py-0.5 rounded-full text-xs ${
                activeTab === tab.key
                  ? 'bg-red-100 text-[#c8102e]'
                  : 'bg-gray-100 text-gray-500'
              }`}
            >
              {tabCounts[tab.key]}
            </span>
          </button>
        ))}
      </div>

      {/* Grid or Empty state */}
      {filteredJobs.length === 0 ? (
        <div className="flex items-center justify-center min-h-[40vh]">
          <div className="text-center">
            <svg
              className="w-16 h-16 text-gray-300 mx-auto mb-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1}
                d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
              />
            </svg>
            <h2 className="text-lg font-medium text-gray-600 mb-1">
              {activeTab === 'all'
                ? 'No videos yet'
                : `No ${activeTab} videos`}
            </h2>
            <p className="text-sm text-gray-400 mb-4">
              {activeTab === 'all'
                ? 'Create your first one!'
                : 'Try a different filter.'}
            </p>
            {activeTab === 'all' && (
              <Link
                to="/"
                className="inline-block px-4 py-2 bg-[#c8102e] text-white text-sm font-medium rounded-lg hover:bg-[#a00d24] transition-colors"
              >
                Create Video
              </Link>
            )}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredJobs.map((job) => (
            <JobCard key={job.id} job={job} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  );
}
