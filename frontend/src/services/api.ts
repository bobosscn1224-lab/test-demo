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
    body: body !== undefined ? JSON.stringify(body) : '{}',
  });
  if (!res.ok) throw new Error(await apiErrorMessage(res));
  return res.json();
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  const hasBody = body !== undefined && body !== null;
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: hasBody ? { 'Content-Type': 'application/json' } : undefined,
    body: hasBody ? JSON.stringify(body) : undefined,
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
    // FastAPI 422 format: { detail: [{ loc: [...], msg: "...", type: "..." }] }
    if (data.detail && Array.isArray(data.detail)) {
      const errors = data.detail.map((e: any) =>
        `${e.loc?.join('.') || '?'}: ${e.msg}`
      ).join('; ');
      return `${prefix}: ${errors}`;
    }
    if (data.detail && typeof data.detail === 'string') {
      return `${prefix}: ${data.detail}`;
    }
    return `${prefix}: ${JSON.stringify(data)}`;
  } catch {
    try {
      return `${prefix}: ${await res.text()}`;
    } catch {
      return prefix;
    }
  }
}
