import { describe, it, expect, vi } from 'vitest'
import { fetchTeacherDashboard } from './teacher-dashboard'
import { apiClient } from '@/lib/api-client'
import { TeacherDashboardResponseSchema } from '@/schemas/teacher-dashboard'

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    getWithValidation: vi.fn(),
  },
}))

describe('Teacher Dashboard Service', () => {
  it('should call getWithValidation with correct endpoint and schema', async () => {
    // 1. Arrange: Mock the return value
    const mockResponse = {
      batches: [
        {
          batch_id: '123e4567-e89b-12d3-a456-426614174000',
          title: 'Test Batch',
          class_name: 'Class 9A',
          status: 'processing',
          total_essays: 10,
          completed_essays: 5,
          created_at: '2025-12-09T12:00:00Z',
        },
      ],
      total_count: 1,
    }

    vi.mocked(apiClient.getWithValidation).mockResolvedValue(mockResponse)

    // 2. Act: Call the service
    const result = await fetchTeacherDashboard()

    // 3. Assert: Verify the client was called correctly
    expect(apiClient.getWithValidation).toHaveBeenCalledWith(
      '/v1/teacher/dashboard',
      TeacherDashboardResponseSchema,
    )
    
    // 4. Assert: Verify the result is passed through
    expect(result).toEqual(mockResponse)
  })
})
