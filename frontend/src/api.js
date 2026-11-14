const API_URL = import.meta.env.VITE_API_URL || '';

export async function apiFetch(path, options = {}) {
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const headers = {
    ...(options.body && !isFormData ? { 'Content-Type': 'application/json' } : {}),
    ...(options.headers || {}),
  };
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers,
    body: isFormData
      ? options.body
      : options.body && typeof options.body !== 'string'
        ? JSON.stringify(options.body)
        : options.body,
  });
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail = typeof payload === 'object' ? payload.detail : payload;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || String(item)).join(' · ')
      : detail;
    throw new Error(message || `Requête impossible (${response.status})`);
  }
  return payload;
}

export async function downloadFile(path, filename) {
  const response = await fetch(`${API_URL}${path}`, { credentials: 'include' });
  if (!response.ok) {
    let message = 'Téléchargement impossible.';
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      // Keep the generic message when the response is not JSON.
    }
    throw new Error(message);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

