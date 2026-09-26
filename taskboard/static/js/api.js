/** HTTP client for /api: JSON in and out, CSRF header on writes, errors as ApiError. */

export class ApiError extends Error {
  constructor(status, code, message, body = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

const CSRF_COOKIE = "taskboard_csrf";

function csrfToken() {
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${CSRF_COOKIE}=`));
  return match ? decodeURIComponent(match.slice(CSRF_COOKIE.length + 1)) : "";
}

/** Relative to <base href>, so the app works when mounted under a sub-path. */
function apiUrl(path, params) {
  const url = new URL(`api${path}`, document.baseURI);
  for (const [name, value] of Object.entries(params ?? {})) {
    if (value === null || value === undefined || value === "") continue;
    for (const item of Array.isArray(value) ? value : [value]) url.searchParams.append(name, item);
  }
  return url;
}

function messageOf(body, status) {
  if (body?.message) return body.message;
  if (Array.isArray(body?.detail)) {
    return body.detail.map((d) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
  }
  if (status === 0) return "The server cannot be reached.";
  return `Request failed (${status}).`;
}

async function request(method, path, { body, params } = {}) {
  const headers = { Accept: "application/json" };
  const isForm = body instanceof FormData; // uploads: the browser sets the multipart header
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  let response;
  try {
    response = await fetch(apiUrl(path, params), {
      method,
      headers,
      body: body === undefined || isForm ? body : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "network", messageOf(null, 0));
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, data?.error ?? `http_${response.status}`, messageOf(data, response.status), data);
  }
  return data;
}

export const api = {
  get: (path, params) => request("GET", path, { params }),
  post: (path, body) => request("POST", path, { body }),
  put: (path, body) => request("PUT", path, { body }),
  patch: (path, body) => request("PATCH", path, { body }),
  delete: (path) => request("DELETE", path),
  /** POST a FormData (file upload). */
  upload: (path, form) => request("POST", path, { body: form }),
};
