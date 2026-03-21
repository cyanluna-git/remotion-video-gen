import { useEffect, useRef } from 'react';

interface LogViewerProps {
  log: string;
  isOpen: boolean;
  onToggle: () => void;
}

export function LogViewer({ log, isOpen, onToggle }: LogViewerProps): React.JSX.Element {
  const scrollRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (isOpen && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [log, isOpen]);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
      >
        <span>{isOpen ? 'Hide Logs' : 'Show Logs'}</span>
        <svg
          className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <pre
          ref={scrollRef}
          className="px-4 py-3 text-sm text-white font-mono whitespace-pre-wrap break-words overflow-y-auto"
          style={{ backgroundColor: '#1a1a2e', maxHeight: '300px' }}
        >
          {log || 'No logs yet...'}
        </pre>
      )}
    </div>
  );
}
