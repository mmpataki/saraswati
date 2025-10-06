import axios, { AxiosHeaders, InternalAxiosRequestConfig } from "axios";

const API_BASE = "/knowledge/api";

export const api = axios.create({
  baseURL: API_BASE
});

export const authApi = axios.create({
  baseURL: `${API_BASE}/auth`
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem("saraswati_token");
  if (token) {
    const headers = config.headers ?? new AxiosHeaders();
    if (headers instanceof AxiosHeaders) {
      headers.set("Authorization", `Bearer ${token}`);
    } else {
      (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
    }
    config.headers = headers;
  }
  return config;
});
