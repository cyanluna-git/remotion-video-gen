export interface ScenarioSection {
  title: string;
  description: string;
  startSec: number;
  endSec: number;
}

export interface ScenarioStyle {
  transition: string;
  captionPosition: string;
}

export interface ScenarioOptions {
  removeSilence: boolean;
  autoCaption: boolean;
}

export interface ScenarioForm {
  title: string;
  subtitle: string;
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
