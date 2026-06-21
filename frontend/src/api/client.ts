import axios, { AxiosError } from "axios";
import { useAuth } from "@/store/auth";
import type {
  DocumentResponse,
  DocumentStatusResponse,
  GraphResponse,
  Page,
  SearchResponse,
  SymbolResponse,
  TokenResponse,
} from "@/types/api";

// In dev the Vite proxy serves "/api" from the local backend; in production set
// VITE_API_BASE_URL to the deployed API origin (e.g. https://docai-api.onrender.com).
const baseURL = import.meta.env.VITE_API_BASE_URL ?? "/";
export const http = axios.create({ baseURL });

// Attach the bearer token to every request.
http.interceptors.request.use((config) => {
  const token = useAuth.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// On 401, attempt a single refresh, then retry; otherwise clear the session.
let refreshing: Promise<string | null> | null = null;
http.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config!;
    const { refreshToken, setTokens, clear } = useAuth.getState();
    if (error.response?.status === 401 && refreshToken && !(original as any)._retry) {
      (original as any)._retry = true;
      refreshing ??= http
        .post<TokenResponse>("/api/v1/auth/refresh", { refresh_token: refreshToken })
        .then((res) => {
          setTokens(res.data.access_token, res.data.refresh_token);
          return res.data.access_token;
        })
        .catch(() => {
          clear();
          return null;
        })
        .finally(() => (refreshing = null));
      const token = await refreshing;
      if (token) {
        original.headers!.Authorization = `Bearer ${token}`;
        return http(original);
      }
    }
    return Promise.reject(error);
  },
);

const V1 = "/api/v1";

export const api = {
  async login(email: string, password: string): Promise<TokenResponse> {
    return (await http.post<TokenResponse>(`${V1}/auth/login`, { email, password })).data;
  },
  async register(email: string, password: string): Promise<void> {
    await http.post(`${V1}/auth/register`, { email, password });
  },
  async uploadDocument(file: File): Promise<{ id: string; status: string; status_url: string }> {
    const form = new FormData();
    form.append("file", file);
    return (await http.post(`${V1}/documents`, form)).data;
  },
  async listDocuments(limit = 50, offset = 0): Promise<Page<DocumentResponse>> {
    return (await http.get(`${V1}/documents`, { params: { limit, offset } })).data;
  },
  async documentStatus(id: string): Promise<DocumentStatusResponse> {
    return (await http.get(`${V1}/documents/${id}/status`)).data;
  },
  async listSymbols(documentId: string, page?: number): Promise<SymbolResponse[]> {
    return (await http.get(`${V1}/documents/${documentId}/symbols`, { params: { page } })).data;
  },
  async editSymbol(id: string, patch: Record<string, unknown>): Promise<SymbolResponse> {
    return (await http.patch(`${V1}/symbols/${id}`, patch)).data;
  },
  async upsertProperties(
    id: string,
    properties: { key: string; value_type: string; value: unknown }[],
  ): Promise<SymbolResponse> {
    return (await http.put(`${V1}/symbols/${id}/properties`, { properties })).data;
  },
  async graph(documentId: string): Promise<GraphResponse> {
    return (await http.get(`${V1}/documents/${documentId}/graph`)).data;
  },
  async searchSimilar(body: Record<string, unknown>): Promise<SearchResponse> {
    return (await http.post(`${V1}/search/similar`, body)).data;
  },
};
