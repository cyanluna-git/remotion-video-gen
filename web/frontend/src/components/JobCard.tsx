import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import type { JobSummary, JobStatus } from '../types/scenario';
import { getThumbnailUrl } from '../api/client';
import { formatRelativeTime, formatFileSize, formatDuration } from '../utils/time';

interface JobCardProps {
  job: JobSummary;
  onDelete: (id: string) => void;
}

const STATUS_STYLES: Record<JobStatus, string> = {
  done: 'bg-green-100 text-green-800',
  running: 'bg-blue-100 text-blue-800',
  queued: 'bg-blue-100 text-blue-800',
  failed: 'bg-red-100 text-red-800',
};

const STATUS_DOT: Record<JobStatus, string> = {
  done: 'bg-green-500',
  running: 'bg-blue-500',
  queued: 'bg-blue-500',
  failed: 'bg-red-500',
};

const STATUS_LABEL: Record<JobStatus, string> = {
  done: 'Done',
  running: 'Running',
  queued: 'Queued',
  failed: 'Failed',
};

function isActiveStatus(status: JobStatus): boolean {
  return status === 'running' || status === 'queued';
}

export function JobCard({ job, onDelete }: JobCardProps): React.JSX.Element {
  const navigate = useNavigate();
  const [thumbError, setThumbError] = useState(false);

  const handleCardClick = useCallback(() => {
    navigate(`/jobs/${job.id}`);
  }, [navigate, job.id]);

  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (window.confirm(`Delete "${job.title || 'Untitled'}"? This cannot be undone.`)) {
        onDelete(job.id);
      }
    },
    [onDelete, job.id, job.title],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        navigate(`/jobs/${job.id}`);
      }
    },
    [navigate, job.id],
  );

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleCardClick}
      onKeyDown={handleKeyDown}
      className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden cursor-pointer transition-all hover:shadow-md hover:border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {/* Thumbnail */}
      <div className="aspect-video bg-gray-100 relative">
        {job.status === 'done' && !thumbError ? (
          <img
            src={getThumbnailUrl(job.id)}
            alt={`Thumbnail for ${job.title}`}
            className="w-full h-full object-cover"
            onError={() => setThumbError(true)}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <svg
              className="w-10 h-10 text-gray-300"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
              />
            </svg>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-2">
        <h3 className="text-sm font-semibold text-gray-800 truncate">
          {job.title || 'Untitled'}
        </h3>

        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLES[job.status]}`}
          >
            {isActiveStatus(job.status) ? (
              <svg
                className="w-3 h-3 animate-spin"
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
            ) : (
              <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[job.status]}`} />
            )}
            {STATUS_LABEL[job.status]}
          </span>
          <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
            {job.inputMode === 'auto' ? 'AI-assisted' : 'Manual'}
          </span>
          {job.hasQa && (
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
              job.qaStatus === 'pass'
                ? 'bg-emerald-50 text-emerald-700'
                : job.qaStatus === 'fail'
                  ? 'bg-red-50 text-red-700'
                  : 'bg-amber-50 text-amber-700'
            }`}>
              {job.qaStatus === 'pass'
                ? 'QA pass'
                : `QA ${job.qaWarningCount ?? 0} issue${(job.qaWarningCount ?? 0) === 1 ? '' : 's'}`}
            </span>
          )}
        </div>

        {(job.ttsStatus && job.ttsStatus !== 'skipped') || job.hasClipRanking || job.hasVisionQa ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {job.ttsStatus && job.ttsStatus !== 'skipped' && (
              <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                TTS {job.ttsTrackCount ?? 0}
              </span>
            )}
            {job.hasClipRanking && (
              <span className="inline-flex items-center rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700">
                Ranked {job.clipRankingCandidateCount ?? 0}
              </span>
            )}
            {job.hasVisionQa && (
              <span className="inline-flex items-center rounded-full bg-purple-50 px-2 py-0.5 text-[11px] font-medium text-purple-700">
                Vision QA
              </span>
            )}
          </div>
        ) : null}

        <p className="text-xs text-gray-400">
          {formatRelativeTime(job.createdAt)}
        </p>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 text-xs text-gray-500">
            {job.duration != null && (
              <span>{formatDuration(job.duration)}</span>
            )}
            {job.fileSize > 0 && (
              <span>{formatFileSize(job.fileSize)}</span>
            )}
          </div>

          <button
            type="button"
            onClick={handleDelete}
            title="Delete job"
            className="p-1.5 rounded-md text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
