import type { Job } from '../types/scenario';

const API_URL = 'http://localhost:8010';

export async function createJob(
  video: File,
  scenario: object,
): Promise<{ id: string }> {
  const formData = new FormData();
  formData.append('video', video);
  formData.append('scenario', JSON.stringify(scenario));

  const res = await fetch(`${API_URL}/api/jobs`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status}`);
  }

  return res.json() as Promise<{ id: string }>;
}

export async function getJobs(): Promise<Job[]> {
  const res = await fetch(`${API_URL}/api/jobs`);

  if (!res.ok) {
    throw new Error(`Failed to fetch jobs: ${res.status}`);
  }

  return res.json() as Promise<Job[]>;
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
