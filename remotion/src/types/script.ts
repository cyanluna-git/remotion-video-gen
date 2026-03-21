export interface EditScript {
  version: "1.0";
  fps: number;
  resolution: { width: number; height: number };
  sources: Record<string, string>;
  timeline: TimelineEntry[];
  captions?: Caption[];
  audio?: AudioConfig;
}

export type TimelineEntry = ClipEntry | TitleCardEntry;

export interface ClipEntry {
  type: "clip";
  source: string;
  startSec: number;
  endSec: number;
  speed?: number;
  transition?: Transition;
  overlays?: Overlay[];
}

export interface TitleCardEntry {
  type: "title-card";
  text: string;
  subtitle?: string;
  durationSec: number;
  background?: string;
  transition?: Transition;
}

export interface Transition {
  type: "fade" | "slide-left" | "slide-right" | "wipe" | "none";
  durationSec: number;
}

export interface Overlay {
  type: "caption" | "highlight" | "arrow" | "zoom";
  startSec: number;
  durationSec: number;
  text?: string;
  position?: "top" | "bottom" | "center";
  region?: { x: number; y: number; width: number; height: number };
  color?: string;
  zoomFactor?: number;
  zoomCenter?: { x: number; y: number };
}

export interface Caption {
  startSec: number;
  endSec: number;
  text: string;
  speaker?: string;
}

export interface AudioConfig {
  backgroundMusic?: {
    src: string;
    volume: number;
    fadeIn?: number;
    fadeOut?: number;
  };
  voiceover?: { src: string; volume: number };
}
