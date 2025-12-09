import { apiClient } from '@/lib/api-client'
import {
  TeacherDashboardResponseSchema,
  type TeacherDashboardResponse,
} from '@/schemas/teacher-dashboard'

/**
 * Service for interacting with the Teacher Dashboard BFF endpoints.
 */

/**
 * Fetches the teacher dashboard data (batch list).
 * Validates the response against the Zod schema at runtime.
 *
 * @returns Promise<TeacherDashboardResponse>
 * @throws ApiError if the request fails
 * @throws ZodError if the response schema is invalid
 */
export async function fetchTeacherDashboard(): Promise<TeacherDashboardResponse> {
  return apiClient.getWithValidation(
    '/v1/teacher/dashboard',
    TeacherDashboardResponseSchema
  )
}
