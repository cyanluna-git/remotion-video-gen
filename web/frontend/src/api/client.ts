import type { Job, JobSummary } from '../types/scenario';

const API_URL = 'http://localhost:8010';

export type CreateJobRequest =
  | {
      mode: 'manual';
      scenario: object;
    }
  | {
      mode: 'auto';
      title?: string;
      language?: string;
    };

export async function createJob(
  video: File,
  request: CreateJobRequest,
): Promise<{ id: string }> {
  const formData = new FormData();
  formData.append('video', video);

  if (request.mode === 'manual') {
    formData.append('scenario', JSON.stringify(request.scenario));
  } else {
    formData.append('autoScenario', 'true');
    if (request.title?.trim()) {
      formData.append('title', request.title.trim());
    }
    if (request.language?.trim()) {
      formData.append('language', request.language.trim());
    }
  }

  const res = await fetch(`${API_URL}/api/jobs`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status}`);
  }

  return res.json() as Promise<{ id: string }>;
}

export async function getJobs(): Promise<JobSummary[]> {
  const res = await fetch(`${API_URL}/api/jobs`);

  if (!res.ok) {
    throw new Error(`Failed to fetch jobs: ${res.status}`);
  }

  return res.json() as Promise<JobSummary[]>;
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`${API_URL}/api/jobs/${id}`);

  if (!res.ok) {
    throw new Error(`Failed to fetch job: ${res.status}`);
  }

  return res.json() as Promise<Job>;
}

export function getVideoUrl(id: string): string {
  return `${API_URL}/api/jobs/${id}/video`;
}

export function getThumbnailUrl(id: string): string {
  return `${API_URL}/api/jobs/${id}/thumbnail`;
}

export async function getEditJson(id: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_URL}/api/jobs/${id}/edit`);

  if (!res.ok) {
    throw new Error(`Failed to fetch edit JSON: ${res.status}`);
  }

  return res.json() as Promise<Record<string, unknown>>;
}

export async function rerender(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/jobs/${id}/rerender`, {
    method: 'POST',
  });

  if (!res.ok) {
    throw new Error(`Failed to rerender: ${res.status}`);
  }
}

export async function deleteJob(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/jobs/${id}`, {
    method: 'DELETE',
  });

  if (!res.ok) {
    throw new Error(`Failed to delete job: ${res.status}`);
  }
}
