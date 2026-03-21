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

export interface Job {
  id: string;
  status: string;
  scenario: ScenarioForm;
  created_at: string;
  updated_at: string;
  output_url?: string;
  thumbnail_url?: string;
  error?: string;
}
