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

export type JobStatus = 'queued' | 'running' | 'done' | 'failed';

export interface JobSummary {
  id: string;
  title: string;
  status: JobStatus;
  createdAt: string;
  completedAt: string | null;
  duration: number | null;
  fileSize: number;
}

export interface Job {
  id: string;
  title: string;
  status: JobStatus;
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
  scenario?: ScenarioForm;
}
