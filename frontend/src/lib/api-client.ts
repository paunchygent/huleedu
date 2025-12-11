import { useAuthStore } from "@/stores/auth";
import { ApiError } from "./api-error";
import { type ZodSchema } from "zod";

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown
}

class ApiClient {
  private baseUrl = "/api";

  async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const authStore = useAuthStore();

    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    if (authStore.token) {
      ;(headers as Record<string, string>)["Authorization"] = `Bearer ${authStore.token}`;
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });

    if (!response.ok) {
      const text = await response.text();
      throw ApiError.fromResponse(response, text);
    }

    return response.json() as Promise<T>;
  }

  async requestWithValidation<T>(
    endpoint: string,
    schema: ZodSchema<T>,
    options: RequestOptions = {},
  ): Promise<T> {
    const data = await this.request<unknown>(endpoint, options);
    return schema.parse(data);
  }

  async get<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: "GET" });
  }

  async getWithValidation<T>(
    endpoint: string,
    schema: ZodSchema<T>,
    options?: RequestOptions,
  ): Promise<T> {
    return this.requestWithValidation<T>(endpoint, schema, { ...options, method: "GET" });
  }

  async post<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: "POST", body });
  }

  async put<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: "PUT", body });
  }

  async delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: "DELETE" });
  }
}

export const apiClient = new ApiClient();
