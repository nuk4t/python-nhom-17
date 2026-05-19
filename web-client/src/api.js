const DEFAULT_SERVER_URL = "http://127.0.0.1:8000";

export function normalizeServerUrl(url) {
  return (url || DEFAULT_SERVER_URL).trim().replace(/\/+$/, "");
}

export async function loadRuntimeSettings() {
  let configuredUrl = DEFAULT_SERVER_URL;

  try {
    const response = await fetch("/settings.json", { cache: "no-store" });
    if (response.ok) {
      const settings = await response.json();
      configuredUrl = settings.serverUrl || configuredUrl;
    }
  } catch {
    configuredUrl = DEFAULT_SERVER_URL;
  }

  return normalizeServerUrl(localStorage.getItem("hotel.serverUrl") || configuredUrl);
}

export function createApiClient({ serverUrl, token, onUnauthorized }) {
  const baseUrl = normalizeServerUrl(serverUrl);

  async function request(path, options = {}) {
    const { method = "GET", body, headers = {} } = options;
    const requestHeaders = {
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    };

    const response = await fetch(`${baseUrl}${path}`, {
      method,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      if (response.status === 401 && onUnauthorized) {
        onUnauthorized();
      }
      throw new Error(data?.error || data || `Request failed with status ${response.status}`);
    }

    return data;
  }

  async function blob(path) {
    const response = await fetch(`${baseUrl}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });

    if (!response.ok) {
      if (response.status === 401 && onUnauthorized) {
        onUnauthorized();
      }
      throw new Error(`Image request failed with status ${response.status}`);
    }

    return response.blob();
  }

  function imageUrl(path) {
    if (!path) {
      return "";
    }
    if (/^https?:\/\//i.test(path)) {
      return path;
    }
    return `${baseUrl}${path}`;
  }

  return { request, blob, imageUrl, baseUrl };
}

export function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
