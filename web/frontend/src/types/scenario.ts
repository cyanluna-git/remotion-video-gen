export interface TimeRange {
  startSec: number;
  endSec: number;
}

export interface ScenarioSection {
  title: string;
  description: string;
  timeRange: TimeRange;
}

export interface ScenarioStyle {
  titleCardBackground?: string;
  transition: 'fade' | 'slide-left' | 'slide-right' | 'wipe' | 'none';
  transitionDuration?: number;
  captionPosition: 'top' | 'bottom' | 'center';
}

export interface ScenarioOptions {
  removeSilence: boolean;
  silenceThreshold?: number;
  autoCaption: boolean;
  correctCaptions: boolean;
}

export interface ScenarioForm {
  title: string;
  subtitle: string;
  language: string;
  sections: ScenarioSection[];
  style: ScenarioStyle;
  options: ScenarioOptions;
}

export type InputMode = 'manual' | 'auto';
export type JobStatus = 'queued' | 'running' | 'done' | 'failed';

export interface JobSummary {
  id: string;
  title: string;
  status: JobStatus;
  inputMode: InputMode;
  hasQa?: boolean;
  qaStatus?: string | null;
  qaWarningCount?: number;
  createdAt: string;
  completedAt: string | null;
  duration: number | null;
  fileSize: number;
  ttsStatus?: string | null;
  ttsTrackCount?: number;
  hasVisionQa?: boolean;
  qaReviewMethods?: string[];
  hasClipRanking?: boolean;
  clipRankingCandidateCount?: number;
}

export interface Job {
  id: string;
  title: string;
  status: JobStatus;
  inputMode: InputMode;
  currentStep: number;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  fileSize: number;
  duration: number | null;
  log: string;
  hasVideo: boolean;
  hasThumbnail: boolean;
  hasEdit: boolean;
  hasQa?: boolean;
  qaStatus?: string | null;
  qaWarningCount?: number;
  qa?: Record<string, unknown>;
  hasScenario?: boolean;
  hasVoiceover?: boolean;
  hasVoiceoverArtifacts?: boolean;
  voiceoverTrackCount?: number;
  voiceoverArtifacts?: string[];
  voiceoverManifest?: Record<string, unknown>;
  ttsStatus?: string | null;
  ttsTrackCount?: number;
  ttsProvider?: string | null;
  ttsModel?: string | null;
  ttsVoice?: string | null;
  ttsError?: string | null;
  hasClipRanking?: boolean;
  clipRankingCandidateCount?: number;
  clipRankingTopCandidateIds?: string[];
  clipRanking?: Record<string, unknown>;
  qaReviewMethods?: string[];
  hasVisionQa?: boolean;
  titleHint?: string | null;
  languageHint?: string | null;
  scenario?: ScenarioForm;
}
