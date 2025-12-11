import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchTeacherDashboard } from "./teacher-dashboard";
import { apiClient } from "@/lib/api-client";
import { TeacherDashboardResponseSchema } from "@/schemas/teacher-dashboard";

// Mock the API client
vi.mock("@/lib/api-client", () => ({
  apiClient: {
    getWithValidation: vi.fn(),
  },
}));

describe("Teacher Dashboard Service", () => {
  const mockResponse = {
    batches: [
      {
        batch_id: "123e4567-e89b-12d3-a456-426614174000",
        title: "Test Batch",
        class_name: "Class 9A",
        status: "processing",
        total_essays: 10,
        completed_essays: 5,
        created_at: "2025-12-09T12:00:00Z",
      },
    ],
    total_count: 1,
    limit: 20,
    offset: 0,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.getWithValidation).mockResolvedValue(mockResponse);
  });

  it("should call endpoint without query params when no params provided", async () => {
    const result = await fetchTeacherDashboard();

    expect(apiClient.getWithValidation).toHaveBeenCalledWith(
      "/bff/v1/teacher/dashboard",
      TeacherDashboardResponseSchema,
    );
    expect(result).toEqual(mockResponse);
  });

  it("should include pagination params in URL", async () => {
    await fetchTeacherDashboard({ limit: 10, offset: 20 });

    expect(apiClient.getWithValidation).toHaveBeenCalledWith(
      "/bff/v1/teacher/dashboard?limit=10&offset=20",
      TeacherDashboardResponseSchema,
    );
  });

  it("should include status filter in URL", async () => {
    await fetchTeacherDashboard({ status: "processing" });

    expect(apiClient.getWithValidation).toHaveBeenCalledWith(
      "/bff/v1/teacher/dashboard?status=processing",
      TeacherDashboardResponseSchema,
    );
  });

  it("should combine all params in URL", async () => {
    await fetchTeacherDashboard({
      limit: 15,
      offset: 30,
      status: "completed_successfully",
    });

    expect(apiClient.getWithValidation).toHaveBeenCalledWith(
      "/bff/v1/teacher/dashboard?limit=15&offset=30&status=completed_successfully",
      TeacherDashboardResponseSchema,
    );
  });

  it("should handle limit=0 by not including it in query", async () => {
    await fetchTeacherDashboard({ offset: 10 });

    expect(apiClient.getWithValidation).toHaveBeenCalledWith(
      "/bff/v1/teacher/dashboard?offset=10",
      TeacherDashboardResponseSchema,
    );
  });
});
