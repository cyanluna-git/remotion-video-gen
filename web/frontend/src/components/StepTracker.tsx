interface StepTrackerProps {
  currentStep: number;
  status: string;
}

const STEPS = [
  { num: 1, label: 'Preprocess' },
  { num: 2, label: 'Analysis' },
  { num: 3, label: 'AI Edit' },
  { num: 4, label: 'Render' },
  { num: 5, label: 'Loudnorm' },
];

function StepCircle({
  state,
}: {
  state: 'completed' | 'active' | 'failed' | 'pending';
}): React.JSX.Element {
  if (state === 'completed') {
    return (
      <div className="w-9 h-9 rounded-full bg-green-500 flex items-center justify-center shrink-0">
        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
        </svg>
      </div>
    );
  }

  if (state === 'active') {
    return (
      <div className="w-9 h-9 rounded-full bg-blue-500 flex items-center justify-center shrink-0 animate-pulse">
        <div className="w-3 h-3 rounded-full bg-white" />
      </div>
    );
  }

  if (state === 'failed') {
    return (
      <div className="w-9 h-9 rounded-full bg-red-500 flex items-center justify-center shrink-0">
        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </div>
    );
  }

  return (
    <div className="w-9 h-9 rounded-full bg-gray-200 flex items-center justify-center shrink-0">
      <div className="w-3 h-3 rounded-full bg-gray-400" />
    </div>
  );
}

function getStepState(
  stepNum: number,
  currentStep: number,
  status: string,
): 'completed' | 'active' | 'failed' | 'pending' {
  if (status === 'done') {
    return 'completed';
  }

  if (status === 'failed') {
    if (stepNum < currentStep) return 'completed';
    if (stepNum === currentStep) return 'failed';
    return 'pending';
  }

  if (stepNum < currentStep) return 'completed';
  if (stepNum === currentStep) return 'active';
  return 'pending';
}

export function StepTracker({ currentStep, status }: StepTrackerProps): React.JSX.Element {
  return (
    <div className="flex items-start justify-between w-full">
      {STEPS.map((step, idx) => {
        const state = getStepState(step.num, currentStep, status);
        const isLast = idx === STEPS.length - 1;
        const lineCompleted = step.num < currentStep || status === 'done';

        return (
          <div key={step.num} className="flex items-start flex-1 min-w-0">
            <div
              className="flex flex-col items-center"
              data-testid={`step-${step.num}`}
              data-step-state={state}
              aria-label={`Step ${step.num}: ${step.label} (${state})`}
            >
              <StepCircle state={state} />
              <span className="mt-2 text-xs font-medium text-gray-600 text-center whitespace-nowrap">
                {step.label}
              </span>
            </div>

            {!isLast && (
              <div className="flex-1 mt-4 mx-2">
                <div
                  className={`h-0.5 w-full ${
                    lineCompleted ? 'bg-green-500' : 'bg-gray-200'
                  }`}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
