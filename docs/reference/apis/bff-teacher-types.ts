/**
 * BFF Teacher Service API Types
 *
 * TypeScript types for the Teacher Dashboard BFF API.
 * Corresponds to OpenAPI schema at /openapi.json (port 4101).
 *
 * Regenerate OpenAPI: pdm run bff-openapi
 * Update this file manually after schema changes.
 */

/**
 * Client-facing batch status enum.
 * Matches BatchClientStatus from common_core.status_enums.
 */
export type BatchClientStatus =
  | "pending_content"
  | "ready"
  | "processing"
  | "completed_successfully"
  | "completed_with_failures"
  | "failed"
  | "cancelled";

/**
 * Single batch item for the teacher dashboard list.
 * Aggregates data from RAS (status, counts) and CMS (class_name).
 */
export interface TeacherBatchItemV1 {
  batch_id: string;
  title: string;
  class_name: string | null;
  status: BatchClientStatus;
  total_essays: number;
  completed_essays: number;
  created_at: string; // ISO 8601 datetime
}

/**
 * Dashboard response with batch list and pagination metadata.
 */
export interface TeacherDashboardResponseV1 {
  batches: TeacherBatchItemV1[];
  total_count: number;
  limit: number;
  offset: number;
}

/**
 * Query parameters for GET /bff/v1/teacher/dashboard.
 */
export interface TeacherDashboardQueryParams {
  /** Maximum batches to return (1-100, default 20) */
  limit?: number;
  /** Number of batches to skip (>= 0, default 0) */
  offset?: number;
  /** Filter by client status */
  status?: BatchClientStatus;
}

/**
 * Error response format from BFF Teacher Service.
 */
export interface BFFTeacherErrorResponse {
  error: {
    code: string;
    message: string;
    correlation_id: string;
    service: string;
    operation: string;
  };
}
