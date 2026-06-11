const BASE = '/api';

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(await apiErrorMessage(res));
  return res.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await apiErrorMessage(res));
  return res.json();
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await apiErrorMessage(res));
  return res.json();
}

export async function apiDelete(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await apiErrorMessage(res));
}

async function apiErrorMessage(res: Response): Promise<string> {
  const prefix = `API ${res.status}`;
  try {
    const data = await res.json();
    return `${prefix}: ${JSON.stringify(data, null, 2)}`;
  } catch {
    try {
      return `${prefix}: ${await res.text()}`;
    } catch {
      return prefix;
    }
  }
}
