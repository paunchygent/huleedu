import { apiClient } from '@/lib/api-client'
import {
  TeacherDashboardResponseSchema,
  type TeacherDashboardResponse,
  type BatchClientStatus,
} from '@/schemas/teacher-dashboard'

/**
 * Service for interacting with the Teacher Dashboard BFF endpoints.
 */

/**
 * Parameters for fetching teacher dashboard data.
 */
export interface TeacherDashboardParams {
  /** Maximum batches to return (1-100, default 20) */
  limit?: number
  /** Number of batches to skip (default 0) */
  offset?: number
  /** Filter by batch status */
  status?: BatchClientStatus
}

/**
 * Fetches the teacher dashboard data (batch list) with pagination and filtering.
 * Validates the response against the Zod schema at runtime.
 *
 * @param params - Optional pagination and filter parameters
 * @returns Promise<TeacherDashboardResponse>
 * @throws ApiError if the request fails
 * @throws ZodError if the response schema is invalid
 */
export async function fetchTeacherDashboard(
  params: TeacherDashboardParams = {}
): Promise<TeacherDashboardResponse> {
  const searchParams = new URLSearchParams()

  if (params.limit !== undefined) {
    searchParams.set('limit', params.limit.toString())
  }
  if (params.offset !== undefined) {
    searchParams.set('offset', params.offset.toString())
  }
  if (params.status) {
    searchParams.set('status', params.status)
  }

  const query = searchParams.toString()
  const endpoint = query ? `/bff/v1/teacher/dashboard?${query}` : '/bff/v1/teacher/dashboard'

  return apiClient.getWithValidation(endpoint, TeacherDashboardResponseSchema)
}
