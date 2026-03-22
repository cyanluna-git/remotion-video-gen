import { useState, useRef, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createJob } from '../api/client';
import type { InputMode, ScenarioForm, ScenarioSection } from '../types/scenario';

const ACCEPTED_TYPES = '.mp4,.mov,.webm';
const ACCEPTED_MIME = ['video/mp4', 'video/quicktime', 'video/webm'];

function createEmptySection(): ScenarioSection {
  return {
    title: '',
    description: '',
    timeRange: { startSec: 0, endSec: 0 },
  };
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadPage(): React.JSX.Element {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [mode, setMode] = useState<InputMode>('auto');

  const [form, setForm] = useState<ScenarioForm>({
      title: '',
      subtitle: '',
      language: 'auto',
      sections: [createEmptySection()],
      style: {
        transition: 'fade',
        captionPosition: 'bottom',
      },
      options: {
        removeSilence: true,
        autoCaption: true,
        correctCaptions: true,
      },
    });

  const handleFile = useCallback((selectedFile: File) => {
    if (!ACCEPTED_MIME.includes(selectedFile.type)) {
      return;
    }
    setFile(selectedFile);

    if (videoPreviewUrl) {
      URL.revokeObjectURL(videoPreviewUrl);
    }
    setVideoPreviewUrl(URL.createObjectURL(selectedFile));
  }, [videoPreviewUrl]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile) {
        handleFile(droppedFile);
      }
    },
    [handleFile],
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selectedFile = e.target.files?.[0];
      if (selectedFile) {
        handleFile(selectedFile);
      }
    },
    [handleFile],
  );

  const updateSection = useCallback(
    (
      index: number,
      field: 'title' | 'description' | 'startSec' | 'endSec',
      value: string | number,
    ) => {
      setForm((prev) => {
        const sections = [...prev.sections];
        if (field === 'startSec' || field === 'endSec') {
          sections[index] = {
            ...sections[index],
            timeRange: {
              ...sections[index].timeRange,
              [field]: Number(value),
            },
          };
        } else {
          sections[index] = { ...sections[index], [field]: value };
        }
        return { ...prev, sections };
      });
    },
    [],
  );

  const addSection = useCallback(() => {
    setForm((prev) => ({
      ...prev,
      sections: [...prev.sections, createEmptySection()],
    }));
  }, []);

  const removeSection = useCallback((index: number) => {
    setForm((prev) => ({
      ...prev,
      sections: prev.sections.filter((_, i) => i !== index),
    }));
  }, []);

  const hasValidManualSections = form.sections.every(
    (section) =>
      section.title.trim().length > 0 &&
      section.description.trim().length > 0 &&
      section.timeRange.endSec > section.timeRange.startSec,
  );
  const canSubmit =
    file !== null &&
    !isSubmitting &&
    (mode === 'auto' || (form.title.trim().length > 0 && hasValidManualSections));

  const handleSubmit = useCallback(async () => {
    if (!file || !canSubmit) return;

    setIsSubmitting(true);
    try {
      const result = await createJob(
        file,
        mode === 'auto'
          ? {
              mode: 'auto',
              title: form.title,
              language: form.language === 'auto' ? undefined : form.language,
            }
          : {
              mode: 'manual',
              scenario: form,
            },
      );
      navigate(`/jobs/${result.id}`);
    } catch (err) {
      console.error('Failed to create job:', err);
      setIsSubmitting(false);
    }
  }, [file, form, mode, canSubmit, navigate]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-800">
          Create New Video
        </h1>
        <p className="text-gray-500 mt-1">
          Upload a video and configure your scenario to generate an edited
          version.
        </p>
        <Link
          to="/how-it-works"
          className="inline-flex items-center gap-2 mt-3 text-sm font-medium text-[#1a1a2e] hover:text-[#c8102e] transition-colors"
        >
          How the pipeline works
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 5l7 7-7 7" />
          </svg>
        </Link>
      </div>

      {/* Video Upload Zone */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-medium text-gray-800 mb-4">
          Video Upload
        </h2>

        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`relative border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
            isDragging
              ? 'border-blue-400 bg-blue-50'
              : file
                ? 'border-green-300 bg-green-50'
                : 'border-gray-300 bg-gray-50 hover:border-gray-400 hover:bg-gray-100'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={handleFileInput}
            className="hidden"
          />

          {file ? (
            <div className="space-y-3">
              {videoPreviewUrl && (
                <video
                  src={videoPreviewUrl}
                  className="mx-auto max-h-48 rounded-lg"
                  muted
                  playsInline
                />
              )}
              <div>
                <p className="text-sm font-medium text-gray-700">
                  {file.name}
                </p>
                <p className="text-xs text-gray-500">
                  {formatFileSize(file.size)}
                </p>
              </div>
              <p className="text-xs text-gray-400">
                Click or drag to replace
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <svg
                className="mx-auto w-12 h-12 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </svg>
              <p className="text-sm text-gray-600">
                <span className="font-medium text-[#c8102e]">
                  Click to upload
                </span>{' '}
                or drag and drop
              </p>
              <p className="text-xs text-gray-400">MP4, MOV, or WebM</p>
            </div>
          )}
        </div>
      </div>

      {/* Scenario Form */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-medium text-gray-800 mb-4">Input Mode</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
          <button
            type="button"
            onClick={() => setMode('auto')}
            className={`rounded-xl border px-4 py-4 text-left transition-colors ${
              mode === 'auto'
                ? 'border-[#c8102e] bg-red-50'
                : 'border-gray-200 bg-white hover:border-gray-300'
            }`}
          >
            <p className="text-sm font-semibold text-gray-800">AI-assisted</p>
            <p className="mt-1 text-sm text-gray-500">
              Upload only the video, then let AI derive the scenario from analysis.
            </p>
          </button>
          <button
            type="button"
            onClick={() => setMode('manual')}
            className={`rounded-xl border px-4 py-4 text-left transition-colors ${
              mode === 'manual'
                ? 'border-[#c8102e] bg-red-50'
                : 'border-gray-200 bg-white hover:border-gray-300'
            }`}
          >
            <p className="text-sm font-semibold text-gray-800">Manual scenario</p>
            <p className="mt-1 text-sm text-gray-500">
              Define sections yourself for full control over titles, descriptions, and ranges.
            </p>
          </button>
        </div>

        <div className="space-y-4">
          {/* Title */}
          <div>
            <label
              htmlFor="scenario-title"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              {mode === 'manual' ? (
                <>
                  Title <span className="text-red-500">*</span>
                </>
              ) : (
                'Title Hint'
              )}
            </label>
            <input
              id="scenario-title"
              type="text"
              value={form.title}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, title: e.target.value }))
              }
              placeholder={mode === 'auto' ? 'Optional title for AI guidance' : 'Enter video title'}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Subtitle */}
            <div className={mode === 'auto' ? 'hidden' : ''}>
              <label
                htmlFor="scenario-subtitle"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Subtitle
              </label>
              <input
                id="scenario-subtitle"
                type="text"
                value={form.subtitle}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, subtitle: e.target.value }))
                }
                placeholder="Enter subtitle (optional)"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div className={mode === 'auto' ? 'md:col-span-2' : ''}>
              <label
                htmlFor="scenario-language"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                {mode === 'auto' ? 'Language Hint' : 'Language'}
              </label>
              <select
                id="scenario-language"
                value={form.language}
                onChange={(e) =>
                  setForm((prev) => ({ ...prev, language: e.target.value }))
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
              >
                <option value="auto">Auto Detect</option>
                <option value="ko">Korean</option>
                <option value="en">English</option>
                <option value="ja">Japanese</option>
              </select>
            </div>
          </div>

          {/* Sections */}
          {mode === 'manual' ? (
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700">
                Sections
              </label>
              <button
                type="button"
                onClick={addSection}
                className="text-sm text-[#c8102e] hover:text-[#a00d24] font-medium"
              >
                + Add Section
              </button>
            </div>

            <div className="space-y-3">
              {form.sections.map((section, index) => (
                <div
                  key={index}
                  className="border border-gray-200 rounded-lg p-4 bg-gray-50"
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                      Section {index + 1}
                    </span>
                    {form.sections.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeSection(index)}
                        className="text-xs text-red-500 hover:text-red-700"
                      >
                        Remove
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label
                        htmlFor={`section-title-${index}`}
                        className="block text-xs text-gray-500 mb-1"
                      >
                        Title
                      </label>
                      <input
                        id={`section-title-${index}`}
                        type="text"
                        value={section.title}
                        onChange={(e) =>
                          updateSection(index, 'title', e.target.value)
                        }
                        placeholder="Section title"
                        className="w-full px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    </div>
                    <div>
                      <label
                        htmlFor={`section-desc-${index}`}
                        className="block text-xs text-gray-500 mb-1"
                      >
                        Description
                      </label>
                      <input
                        id={`section-desc-${index}`}
                        type="text"
                        value={section.description}
                        onChange={(e) =>
                          updateSection(index, 'description', e.target.value)
                        }
                        placeholder="Section description"
                        className="w-full px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    </div>
                    <div>
                      <label
                        htmlFor={`section-start-${index}`}
                        className="block text-xs text-gray-500 mb-1"
                      >
                        Start (sec)
                      </label>
                      <input
                        id={`section-start-${index}`}
                        type="number"
                        min={0}
                        value={section.timeRange.startSec}
                        onChange={(e) =>
                          updateSection(index, 'startSec', Number(e.target.value))
                        }
                        className="w-full px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    </div>
                    <div>
                      <label
                        htmlFor={`section-end-${index}`}
                        className="block text-xs text-gray-500 mb-1"
                      >
                        End (sec)
                      </label>
                      <input
                        id={`section-end-${index}`}
                        type="number"
                        min={0}
                        value={section.timeRange.endSec}
                        onChange={(e) =>
                          updateSection(index, 'endSec', Number(e.target.value))
                        }
                        className="w-full px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          ) : (
            <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 px-4 py-5 text-sm text-gray-600">
              <p>
                AI-assisted mode will infer section titles, descriptions, and time ranges from transcript, scene, silence, and clip-ranking analysis.
                Language and title above are optional hints only.
              </p>
              <p className="mt-2 text-xs text-gray-500">
                Narration generation and vision QA remain server-managed stages when those providers are enabled.
              </p>
            </div>
          )}

          {/* Advanced Options (Collapsible) */}
          {mode === 'manual' && (
          <div className="border border-gray-200 rounded-lg">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 rounded-lg"
            >
              <span>Advanced Options</span>
              <svg
                className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </button>

            {showAdvanced && (
              <div className="px-4 pb-4 space-y-4 border-t border-gray-200 pt-4">
                {/* Style Options */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label
                      htmlFor="transition-type"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      Transition Type
                    </label>
                    <select
                      id="transition-type"
                      value={form.style.transition}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          style: {
                            ...prev.style,
                            transition: e.target.value as ScenarioForm['style']['transition'],
                          },
                        }))
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
                    >
                      <option value="fade">Fade</option>
                      <option value="slide-left">Slide Left</option>
                      <option value="slide-right">Slide Right</option>
                      <option value="wipe">Wipe</option>
                    </select>
                  </div>
                  <div>
                    <label
                      htmlFor="caption-position"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      Caption Position
                    </label>
                    <select
                      id="caption-position"
                      value={form.style.captionPosition}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          style: {
                            ...prev.style,
                            captionPosition:
                              e.target.value as ScenarioForm['style']['captionPosition'],
                          },
                        }))
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
                    >
                      <option value="bottom">Bottom</option>
                      <option value="top">Top</option>
                      <option value="center">Center</option>
                    </select>
                  </div>
                </div>

                {/* Checkboxes */}
                <div className="space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.options.removeSilence}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          options: {
                            ...prev.options,
                            removeSilence: e.target.checked,
                          },
                        }))
                      }
                      className="w-4 h-4 rounded border-gray-300 text-[#c8102e] focus:ring-[#c8102e]"
                    />
                    <span className="text-sm text-gray-700">
                      Remove silence
                    </span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.options.autoCaption}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          options: {
                            ...prev.options,
                            autoCaption: e.target.checked,
                          },
                        }))
                      }
                      className="w-4 h-4 rounded border-gray-300 text-[#c8102e] focus:ring-[#c8102e]"
                    />
                    <span className="text-sm text-gray-700">
                      Auto captions
                    </span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.options.correctCaptions}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          options: {
                            ...prev.options,
                            correctCaptions: e.target.checked,
                          },
                        }))
                      }
                      className="w-4 h-4 rounded border-gray-300 text-[#c8102e] focus:ring-[#c8102e]"
                    />
                    <span className="text-sm text-gray-700">
                      Correct captions with AI
                    </span>
                  </label>
                </div>
              </div>
            )}
          </div>
          )}
        </div>
      </div>

      {/* Generate Button */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!canSubmit}
          className={`w-full py-3 px-6 rounded-lg text-white font-medium text-sm transition-colors ${
            canSubmit
              ? 'bg-[#c8102e] hover:bg-[#a00d24] active:bg-[#8a0b1f] cursor-pointer'
              : 'bg-gray-300 cursor-not-allowed'
          }`}
        >
          {isSubmitting ? (
            <span className="flex items-center justify-center gap-2">
              <svg
                className="animate-spin w-4 h-4"
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
              Uploading...
            </span>
          ) : (
            'Generate Video'
          )}
        </button>

        {!file && (
          <p className="text-xs text-gray-400 text-center mt-2">
            Upload a video file to enable generation
          </p>
        )}
        {file && mode === 'manual' && form.title.trim().length === 0 && (
          <p className="text-xs text-gray-400 text-center mt-2">
            Enter a title to enable generation
          </p>
        )}
        {file && mode === 'manual' && !hasValidManualSections && (
          <p className="text-xs text-gray-400 text-center mt-2">
            Fill each section title, description, and valid time range to enable generation
          </p>
        )}
      </div>
    </div>
  );
}
