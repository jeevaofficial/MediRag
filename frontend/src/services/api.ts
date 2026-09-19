const API_ROOT = (import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");
const API_URL = API_ROOT.endsWith("/api/v1") ? API_ROOT : `${API_ROOT}/api/v1`;
const CHAT_TIMEOUT_MS = 300_000;
export const AUTH_EXPIRED_EVENT = "medirag:auth-expired";

function handleUnauthorized(res: Response) {
  if (res.status === 401) {
    localStorage.removeItem("medirag_token");
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }
}

function getAuthHeaders(): HeadersInit {
  const token = localStorage.getItem("medirag_token");
  if (token) {
    return {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json"
    };
  }
  return {
    "Content-Type": "application/json"
  };
}

async function readErrorMessage(res: Response): Promise<string> {
  const text = await res.text();
  if (!text) {
    return `Request failed with status ${res.status}`;
  }

  try {
    const data = JSON.parse(text);
    if (typeof data.detail === "string") {
      return data.detail;
    }
    return JSON.stringify(data.detail || data);
  } catch {
    return text;
  }
}

async function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = CHAT_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } catch (err: any) {
    if (err?.name === "AbortError") {
      throw new Error("The AI service timed out while waiting for Groq to respond. Try again with a shorter question.");
    }
    throw err;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export const api = {
  async register(fullName: string, username: string, password: string) {
    const res = await fetch(`${API_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ full_name: fullName, username, password })
    });
    handleUnauthorized(res);
    if (!res.ok) throw new Error(await readErrorMessage(res));
    const data = await res.json();
    if (data.access_token) {
      localStorage.setItem("medirag_token", data.access_token);
    }
    return data;
  },

  async login(username: string, password: string) {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    const res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData
    });
    handleUnauthorized(res);
    if (!res.ok) throw new Error(await readErrorMessage(res));
    const data = await res.json();
    localStorage.setItem("medirag_token", data.access_token);
    return data;
  },

  logout() {
    localStorage.removeItem("medirag_token");
  },

  async getDocuments() {
    const res = await fetch(`${API_URL}/documents/`, {
      headers: getAuthHeaders()
    });
    handleUnauthorized(res);
    if (!res.ok) throw new Error(await readErrorMessage(res));
    return res.json();
  },

  async uploadDocument(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    
    const token = localStorage.getItem("medirag_token");
    const res = await fetch(`${API_URL}/documents/upload`, {
      method: 'POST',
      headers: token ? { "Authorization": `Bearer ${token}` } : {},
      body: formData
    });
    handleUnauthorized(res);
    if (!res.ok) throw new Error(await readErrorMessage(res));
    return res.json();
  },

  async deleteDocument(id: number) {
    const res = await fetch(`${API_URL}/documents/${id}`, {
      method: 'DELETE',
      headers: getAuthHeaders()
    });
    handleUnauthorized(res);
    if (!res.ok) throw new Error(await readErrorMessage(res));
    return res.json();
  },


  async getChatHistory() {
    const res = await fetch(`${API_URL}/chat/history`, {
      headers: getAuthHeaders()
    });
    handleUnauthorized(res);
    if (!res.ok) throw new Error(await readErrorMessage(res));
    return res.json();
  },

  async queryChat(query: string) {
    const res = await fetchWithTimeout(`${API_URL}/chat/query`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ query })
    });
    handleUnauthorized(res);
    if (!res.ok) throw new Error(await readErrorMessage(res));
    return res.json();
  }
};
