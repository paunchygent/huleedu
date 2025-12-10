import { z } from 'zod';

// Enum mirroring BatchClientStatus from backend
export const BatchClientStatusSchema = z.enum([
  'pending_content',
  'ready',
  'processing',
  'completed_successfully',
  'completed_with_failures',
  'failed',
  'cancelled',
]);

export type BatchClientStatus = z.infer<typeof BatchClientStatusSchema>;

// Schema for a single batch item
export const TeacherBatchItemSchema = z.object({
  batch_id: z.string().uuid(),
  title: z.string(),
  // Supports Guest Batches (null) and Regular Batches (string)
  class_name: z.string().nullable(),
  status: BatchClientStatusSchema,
  total_essays: z.number().int().nonnegative(),
  completed_essays: z.number().int().nonnegative(),
  // Zod handles ISO string dates from JSON automatically with coerce or string()
  // Using string() for now as APIs return ISO strings
  created_at: z.string().datetime(),
});

export type TeacherBatchItem = z.infer<typeof TeacherBatchItemSchema>;

// Schema for the dashboard response
export const TeacherDashboardResponseSchema = z.object({
  batches: z.array(TeacherBatchItemSchema),
  total_count: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});

export type TeacherDashboardResponse = z.infer<typeof TeacherDashboardResponseSchema>;
