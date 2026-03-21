import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test, type Page } from '@playwright/test';

const THIS_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(THIS_DIR, '../../..');
const SAMPLE_UPLOAD = resolve(
  REPO_ROOT,
  'remotion/public/recordings/test-10s.mp4',
);
const SAMPLE_RENDERED_VIDEO = readFileSync(
  resolve(REPO_ROOT, 'jobs/e33dd4b6-8a21-4960-8a18-63df30a8a49e/output/final.mp4'),
);
const SAMPLE_THUMBNAIL = readFileSync(
  resolve(
    REPO_ROOT,
    'jobs/e33dd4b6-8a21-4960-8a18-63df30a8a49e/output/thumbnail.jpg',
  ),
);

type InputMode = 'manual' | 'auto';
type JobStatus = 'queued' | 'running' | 'done';

interface ScenarioData {
  title: string;
  subtitle: string;
  language: string;
  sections: Array<{
    title: string;
    description: string;
    timeRange: { startSec: number; endSec: number };
  }>;
  style: {
    transition: 'fade' | 'slide-left' | 'slide-right' | 'wipe' | 'none';
    captionPosition: 'top' | 'bottom' | 'center';
  };
  options: {
    removeSilence: boolean;
    autoCaption: boolean;
    correctCaptions: boolean;
  };
}

interface JobSnapshot {
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
  hasQa: boolean;
  qaStatus: string;
  qaWarningCount: number;
  qa: Record<string, unknown>;
  scenario: ScenarioData;
}

interface MockJob {
  id: string;
  title: string;
  inputMode: InputMode;
  scenario: ScenarioData;
  createdAt: string;
  detailIndex: number;
  snapshots: JobSnapshot[];
}

function buildScenario(title: string, sectionTitle: string): ScenarioData {
  return {
    title,
    subtitle: '',
    language: 'en',
    sections: [
      {
        title: sectionTitle,
        description: `${sectionTitle} walkthrough`,
        timeRange: { startSec: 0, endSec: 8 },
      },
    ],
    style: {
      transition: 'fade',
      captionPosition: 'bottom',
    },
    options: {
      removeSilence: true,
      autoCaption: true,
      correctCaptions: true,
    },
  };
}

function buildSnapshots(job: {
  id: string;
  title: string;
  inputMode: InputMode;
  createdAt: string;
  scenario: ScenarioData;
}): JobSnapshot[] {
  const doneBase = {
    id: job.id,
    title: job.title,
    inputMode: job.inputMode,
    createdAt: job.createdAt,
    startedAt: '2026-03-21T04:00:02.000Z',
    completedAt: '2026-03-21T04:00:10.000Z',
    fileSize: SAMPLE_RENDERED_VIDEO.byteLength,
    duration: 8,
    hasVideo: true,
    hasThumbnail: true,
    hasEdit: true,
    hasQa: true,
    qaStatus: 'pass',
    qaWarningCount: 0,
    qa: {
      summary: {
        status: 'pass',
        warningCount: 0,
        failCount: 0,
      },
    },
    scenario: job.scenario,
  };

  return [
    {
      ...doneBase,
      status: 'queued',
      currentStep: 1,
      startedAt: null,
      completedAt: null,
      duration: null,
      fileSize: 0,
      hasVideo: false,
      hasThumbnail: false,
      hasEdit: false,
      hasQa: false,
      qaStatus: 'pass',
      qaWarningCount: 0,
      qa: {},
      log: 'Step 1: Preprocessing',
    },
    {
      ...doneBase,
      status: 'running',
      currentStep: 3,
      fileSize: 0,
      duration: null,
      hasVideo: false,
      hasThumbnail: false,
      hasEdit: false,
      hasQa: false,
      qa: {},
      log: ['Step 1: Preprocessing', 'Step 2: Analysis', 'Step 3: AI Edit'].join(
        '\n',
      ),
    },
    {
      ...doneBase,
      status: 'done',
      currentStep: 5,
      log: [
        'Step 1: Preprocessing',
        'Step 2: Analysis',
        'Step 3: AI Edit',
        'Step 4: Render',
        'Step 5: Loudnorm',
      ].join('\n'),
    },
  ];
}

function buildEditJson(job: MockJob): Record<string, unknown> {
  return {
    version: '1.0',
    fps: 30,
    resolution: { width: 1920, height: 1080 },
    sources: {
      main: 'recordings/test-10s.mp4',
    },
    timeline: [
      {
        type: 'title-card',
        text: job.title,
        durationSec: 2,
        background: '#1a1a2e',
      },
      {
        type: 'clip',
        source: 'main',
        startSec: 0,
        endSec: 8,
        overlays: [
          {
            type: 'caption',
            captionClass: 'announcement',
            startSec: 1,
            durationSec: 2,
            text: `${job.title} caption`,
          },
        ],
      },
    ],
  };
}

function buildSummary(job: MockJob) {
  const snapshot = job.snapshots[Math.min(job.detailIndex, job.snapshots.length - 1)];
  return {
    id: job.id,
    title: job.title,
    status: snapshot.status,
    inputMode: job.inputMode,
    hasQa: snapshot.hasQa,
    qaStatus: snapshot.hasQa ? snapshot.qaStatus : null,
    qaWarningCount: snapshot.hasQa ? snapshot.qaWarningCount : 0,
    createdAt: job.createdAt,
    completedAt: snapshot.completedAt,
    duration: snapshot.duration,
    fileSize: snapshot.fileSize,
  };
}

function jsonResponse(body: unknown) {
  return {
    status: 200,
    headers: {
      'access-control-allow-origin': '*',
      'content-type': 'application/json',
    },
    body: JSON.stringify(body),
  };
}

async function installMockApi(page: Page): Promise<void> {
  const jobs = new Map<string, MockJob>();
  let createCount = 0;

  await page.route('http://localhost:8010/api/jobs', async (route) => {
    const method = route.request().method();
    if (method === 'POST') {
      createCount += 1;
      const id = `job-${createCount}`;
      const title = `UI Flow Run ${createCount}`;
      const sectionTitle = `Section ${createCount}`;
      const body = route.request().postData() ?? '';

      expect(body).toContain(title);
      expect(body).toContain(sectionTitle);

      const scenario = buildScenario(title, sectionTitle);
      jobs.set(id, {
        id,
        title,
        inputMode: 'manual',
        scenario,
        createdAt: `2026-03-21T04:00:0${createCount}Z`,
        detailIndex: 0,
        snapshots: buildSnapshots({
          id,
          title,
          inputMode: 'manual',
          createdAt: `2026-03-21T04:00:0${createCount}Z`,
          scenario,
        }),
      });

      await route.fulfill({
        status: 201,
        headers: {
          'access-control-allow-origin': '*',
          'content-type': 'application/json',
        },
        body: JSON.stringify({ id, status: 'queued' }),
      });
      return;
    }

    const summaries = [...jobs.values()]
      .map(buildSummary)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));

    await route.fulfill(jsonResponse(summaries));
  });

  await page.route(/http:\/\/localhost:8010\/api\/jobs\/([^/]+)$/, async (route) => {
    const match = route.request().url().match(/\/api\/jobs\/([^/]+)$/);
    const job = match ? jobs.get(match[1]) : undefined;
    if (!job) {
      await route.fulfill({ status: 404, body: 'Not found' });
      return;
    }

    const snapshot = job.snapshots[Math.min(job.detailIndex, job.snapshots.length - 1)];
    if (job.detailIndex < job.snapshots.length - 1) {
      job.detailIndex += 1;
    }

    await route.fulfill(jsonResponse(snapshot));
  });

  await page.route(/http:\/\/localhost:8010\/api\/jobs\/([^/]+)\/edit$/, async (route) => {
    const match = route.request().url().match(/\/api\/jobs\/([^/]+)\/edit$/);
    const job = match ? jobs.get(match[1]) : undefined;
    if (!job) {
      await route.fulfill({ status: 404, body: 'Not found' });
      return;
    }

    await route.fulfill(jsonResponse(buildEditJson(job)));
  });

  await page.route(/http:\/\/localhost:8010\/api\/jobs\/([^/]+)\/thumbnail$/, async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        'access-control-allow-origin': '*',
        'content-type': 'image/jpeg',
      },
      body: SAMPLE_THUMBNAIL,
    });
  });

  await page.route(/http:\/\/localhost:8010\/api\/jobs\/([^/]+)\/video$/, async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        'access-control-allow-origin': '*',
        'content-type': 'video/mp4',
      },
      body: SAMPLE_RENDERED_VIDEO,
    });
  });
}

async function fillManualScenario(page: Page, title: string, sectionTitle: string) {
  await page.getByRole('button', { name: 'Manual scenario' }).click();
  await page.setInputFiles('input[type="file"]', SAMPLE_UPLOAD);
  await page.locator('#scenario-title').fill(title);
  await page.locator('#section-title-0').fill(sectionTitle);
  await page.locator('#section-desc-0').fill(`${sectionTitle} walkthrough`);
  await page.locator('#section-start-0').fill('0');
  await page.locator('#section-end-0').fill('8');
}

async function waitForJobCompletion(page: Page) {
  await expect(page.getByTestId('step-3')).toHaveAttribute('data-step-state', 'active', {
    timeout: 5_000,
  });
  await expect(page.getByTestId('step-5')).toHaveAttribute('data-step-state', 'completed', {
    timeout: 5_000,
  });
  await expect(page.getByRole('link', { name: 'Download Video' })).toBeVisible();
}

test('covers upload, progress, preview, edit view, download link, and history for two jobs', async ({
  page,
}) => {
    await installMockApi(page);

    await page.goto('/');

    await fillManualScenario(page, 'UI Flow Run 1', 'Section 1');
    await page.getByRole('button', { name: 'Generate Video' }).click();

    await expect(page).toHaveURL(/\/jobs\/job-1$/);
    await waitForJobCompletion(page);

    const previewVideo = page.locator('video[controls]');
    await expect(previewVideo).toBeVisible();
    await expect
      .poll(() => previewVideo.evaluate((node) => node.readyState), { timeout: 5_000 })
      .toBeGreaterThan(0);

    await page.getByRole('button', { name: 'Edit JSON' }).click();
    await expect(page.getByText('"timeline"')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Download Video' })).toHaveAttribute(
      'href',
      'http://localhost:8010/api/jobs/job-1/video',
    );

    await page.getByRole('link', { name: 'History', exact: true }).click();
    await expect(page).toHaveURL(/\/history$/);
    await expect(page.getByText('UI Flow Run 1')).toBeVisible();
    const firstThumb = page.locator('img[alt="Thumbnail for UI Flow Run 1"]');
    await expect(firstThumb).toBeVisible();
    await expect
      .poll(() => firstThumb.evaluate((img) => img.naturalWidth), { timeout: 5_000 })
      .toBeGreaterThan(0);

    await page.getByRole('link', { name: '+ New Video' }).click();
    await expect(page).toHaveURL(/\/$/);

    await fillManualScenario(page, 'UI Flow Run 2', 'Section 2');
    await page.getByRole('button', { name: 'Generate Video' }).click();

    await expect(page).toHaveURL(/\/jobs\/job-2$/);
    await waitForJobCompletion(page);

    await page.getByRole('link', { name: 'History', exact: true }).click();
    await expect(page.getByText('UI Flow Run 2')).toBeVisible();
    await expect(page.getByText('UI Flow Run 1')).toBeVisible();
    await expect(page.getByText(/^2 videos total$/)).toBeVisible();
  },
);
