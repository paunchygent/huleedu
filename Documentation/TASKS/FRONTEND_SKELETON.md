# REVISED: HuleEdu Frontend MVP - SvelteKit Implementation Plan

---

**ID**: `FE-MVP-004`  
**Status**: `Final`  
**Author**: `CTO`  
**Revision Date**: `2025-07-18`
---

This document outlines the Product Requirements Document (PRD) and a phased implementation plan for the HuleEdu Frontend MVP. It has been **completely rewritten with full detail** to reflect the strategic architectural decision to build the frontend on **SvelteKit** instead of React.

## ⚠️ CRITICAL PREREQUISITES

**IMPLEMENTATION DEPENDENCY**: This plan requires the completion of the API Gateway and WebSocket services and alignment with the Client Retry Framework.

**Sequence**: 1. ✅ Backend Services Complete → 2. ✅ Endpoints Verified → 3. ✅ CORS Updated → 4. 🔄 **START HERE**

---

## Part 1: Project Setup & Foundation (The "Bulletproof" SvelteKit Base)

### Objective

To establish a modern, stable, and scalable SvelteKit project within the existing PDM monorepo, ensuring maintainability and a smooth development experience.

### Checkpoint 1.1: Monorepo Integration & SvelteKit Scaffolding

#### Objective

Correctly scaffold a new SvelteKit project and integrate it into the monorepo structure using pnpm.

#### Implementation Steps

##### 1. Create Frontend Directory

In the monorepo root, create a new `frontend` directory.

```bash
# Run from the root of the huledu-reboot repository
mkdir frontend
cd frontend
```

##### 2. Initialize with pnpm

Use `pnpm` for its superior performance in monorepo environments.

```bash
npm install -g pnpm
```

##### 3. Scaffold the SvelteKit Project

Use Svelte's official scaffolding tool.

```bash
# Run this inside the 'frontend' directory
pnpm create svelte@latest .
```

When prompted, select the following options:

- **App template**: Skeleton project
- **Add type checking with**: TypeScript
- **Select additional options**: ESLint, Prettier, Playwright for browser testing, Vitest for unit testing

##### 4. Configure Monorepo Workspaces

Create a `pnpm-workspace.yaml` file in the repository root.

```yaml
# file: pnpm-workspace.yaml
packages:
  - 'frontend'
  - 'services/**'
  - 'libs/**'
```

##### 5. Update API Gateway CORS Configuration

Update `services/api_gateway_service/config.py`.

```python
CORS_ORIGINS: list[str] = Field(
    default=["http://localhost:5173"], # Vite default
    description="Allowed CORS origins for SvelteKit frontend",
)
```

#### Done When

✅ The `frontend` directory contains a functional SvelteKit project.
✅ `pnpm install` inside `frontend` directory succeeds.
✅ `pnpm dev` starts the SvelteKit development server.
✅ API Gateway CORS is updated.

---

### Checkpoint 1.2: Core Dependencies & Configuration

#### Objective

Install and configure the core libraries for styling, state, and API communication.

#### Implementation Steps

##### 1. Install Core Libraries

```bash
cd frontend
pnpm add @tanstack/svelte-query axios
npx svelte-add@latest tailwindcss
pnpm add class-variance-authority clsx tailwind-merge lucide-svelte
pnpm add svelte-file-dropzone js-cookie
pnpm add -D @types/js-cookie
```

##### 2. Configure Environment Variables

Create a `.env` file in the `frontend` directory.

```env
# API Gateway and WebSocket Service configuration
VITE_API_BASE_URL=http://localhost:4001
VITE_WEBSOCKET_URL=ws://localhost:4002/ws
```

#### Rationale for Library Choices (SvelteKit Aligned)

- **SvelteKit Router (Built-in)**: Replaces `react-router-dom`. File-based routing is more intuitive.
- **Svelte Stores (Built-in)**: Replaces `zustand`. `writable` and `derived` stores are the idiomatic solution.
- **`@tanstack/svelte-query`**: The official Svelte adapter for powerful server-state management.
- **`axios`**: Kept for its excellent interceptor support for JWT handling.
- **`svelte-file-dropzone`**: A direct Svelte equivalent for `react-dropzone`.
- **SvelteKit Error Handling (Built-in)**: `+error.svelte` replaces `react-error-boundary`.

#### Done When

✅ All dependencies are in `frontend/package.json`.
✅ A Tailwind class in a `.svelte` file correctly applies styles.
✅ Environment variables are properly configured.

---

## Part 2: Feature Implementation Plan (The PRD)

### Checkpoint 2.1: Authentication & Application Layout

#### Objective

Implement public pages and the main authenticated layout using SvelteKit's secure, server-side capabilities.

#### Implementation Plan

##### 1. API Client with JWT Integration (`src/lib/api/client.ts`)

```typescript
import axios, { type AxiosInstance } from 'axios';
import Cookies from 'js-cookie';
import { goto } from '$app/navigation';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:4001';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 10000,
    });

    this.client.interceptors.request.use((config) => {
      const token = Cookies.get('auth_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          Cookies.remove('auth_token');
          // Use SvelteKit's navigation for client-side redirect
          if (typeof window !== 'undefined') {
            goto('/login');
          }
        }
        return Promise.reject(error);
      }
    );
  }
  // ... API methods will be added here
}

export const apiClient = new ApiClient();
```

##### 2. Server-Side Route Protection

```typescript
// File: src/routes/dashboard/+layout.server.ts
import { redirect } from '@sveltejs/kit';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ cookies }) => {
    const token = cookies.get('auth_token');
    if (!token) {
        // Secure, server-side redirect before page renders.
        throw redirect(303, '/login');
    }
    // TODO: Verify token with API gateway and return user data.
    return { user: { /* user data from token */ } };
};
```

##### 3. Client-Side State with Svelte Stores

```typescript
// File: src/lib/stores/authStore.ts
import { writable } from 'svelte/store';
import Cookies from 'js-cookie';

interface User { id: string; email: string; name: string; }
interface AuthState { user: User | null; isAuthenticated: boolean; token: string | null; }

function createAuthStore() {
    const { subscribe, set } = writable<AuthState>({ user: null, isAuthenticated: false, token: null });

    return {
        subscribe,
        login: (token: string, user: User) => {
            Cookies.set('auth_token', token, { secure: true, sameSite: 'strict', expires: 1 });
            set({ user, isAuthenticated: true, token });
        },
        logout: () => {
            Cookies.remove('auth_token');
            set({ user: null, isAuthenticated: false, token: null });
        },
        initialize: () => {
            const token = Cookies.get('auth_token');
            if (token) {
                // TODO: Decode token to get user data for initial state.
                set({ user: { /* decoded user */ }, isAuthenticated: true, token });
            }
        }
    };
}
export const authStore = createAuthStore();
```

#### Done When

✅ Server-side redirects protect `/dashboard`.
✅ Login sets the cookie and updates the `authStore`.
✅ The `apiClient` correctly handles JWTs and 401 errors.

---

### Checkpoint 2.2: Processing Dashboard with Enhanced Retry Framework

#### Objective

Implement the real-time processing dashboard with comprehensive retry functionality.

#### Implementation Plan

##### 1. Type Definitions (`src/lib/types/retry.ts`)

*The detailed TypeScript interfaces (`RetryMetadata`, `Essay`, `BatchStatus`, `RetryableErrorCategory`, etc.) from the original React plan are preserved here, as they are framework-agnostic.*

```typescript
export interface RetryMetadata {
  retry_count: number;
  first_attempt_at: string;
  last_attempt_at?: string;
  is_retryable: boolean;
  retry_reason?: string;
  max_retries_exceeded: boolean;
}

export enum RetryableErrorCategory {
  TRANSIENT_NETWORK = "transient_network",
  EXTERNAL_SERVICE = "external_service", 
  VALIDATION_ERROR = "validation_error",
  PROCESSING_ERROR = "processing_error",
  UNKNOWN = "unknown"
}

export interface Essay {
  essay_id: string;
  filename: string;
  status: string; // Should be a more specific enum
  metadata?: {
    is_retryable?: boolean;
    retry_metadata?: RetryMetadata;
    error_category?: RetryableErrorCategory;
    failure_reason?: string;
  };
}

export interface BatchStatus {
  batch_id: string;
  pipeline_state: any;
  last_updated: string;
  essays: Essay[];
}
```

##### 2. WebSocket Integration

```typescript
// File: src/lib/websockets.ts
import { type QueryClient } from '@tanstack/svelte-query';
import { get } from 'svelte/store';
import { authStore } from '$lib/stores/authStore';
import type { Essay, BatchStatus } from '$lib/types/retry'; // Assuming types are defined

const WEBSOCKET_URL = import.meta.env.VITE_WEBSOCKET_URL;

export function connectToBatchUpdates(batchId: string, queryClient: QueryClient) {
    const token = get(authStore).token;

    if (!token || !batchId) return () => {};

    const ws = new WebSocket(`${WEBSOCKET_URL}?token=${token}`);

    ws.onmessage = (event) => {
        const update = JSON.parse(event.data);

        switch (update.event) {
          case 'batch_phase_concluded':
            queryClient.setQueryData(['batch', batchId], (oldData: BatchStatus | undefined) => {
              if (!oldData) return oldData;
              return {
                ...oldData,
                pipeline_state: { ...oldData.pipeline_state, [update.phase]: update.status },
                last_updated: update.timestamp,
              };
            });
            break;
          case 'essay_status_updated':
            queryClient.setQueryData(['batch', batchId], (oldData: BatchStatus | undefined) => {
              if (!oldData) return oldData;
              return {
                ...oldData,
                essays: oldData.essays.map((essay: Essay) =>
                  essay.essay_id === update.essay_id
                    ? { ...essay, status: update.status, metadata: update.metadata }
                    : essay
                ),
                last_updated: update.timestamp,
              };
            });
            break;
        }
    };

    ws.onopen = () => console.log('WebSocket connected for batch:', batchId);
    ws.onerror = (error) => console.error('WebSocket error:', error);
    ws.onclose = () => console.log('WebSocket disconnected');

    return () => ws.close(); // Return cleanup function
}
```

##### 3. Processing Dashboard Component (`src/routes/dashboard/processing/[batchId]/+page.svelte`)

```html
<script lang="ts">
    import { onMount } from 'svelte';
    import { createQuery, useQueryClient } from '@tanstack/svelte-query';
    import { connectToBatchUpdates } from '$lib/websockets';
    import { page } from '$app/stores';
    import { apiClient } from '$lib/api/client';
    import RetryButton from '$lib/components/RetryButton.svelte';

    const batchId = $page.params.batchId;
    const queryClient = useQueryClient();

    const query = createQuery({
        queryKey: ['batch', batchId],
        queryFn: () => apiClient.getBatchStatus(batchId),
    });

    onMount(() => {
        const cleanup = connectToBatchUpdates(batchId, queryClient);
        return () => cleanup();
    });
</script>

{#if $query.isLoading}
    <p>Loading batch details...</p>
{:else if $query.isError}
    <p class="text-red-500">Error loading batch data.</p>
{:else if $query.data}
    <h1>Processing Dashboard for Batch: {batchId}</h1>
    <!-- Render FileList, PipelinePanel, etc. -->
    <table>
        <thead>
            <tr><th>Filename</th><th>Status</th><th>Actions</th></tr>
        </thead>
        <tbody>
            {#each $query.data.essays as essay}
                <tr>
                    <td>{essay.filename}</td>
                    <td>{essay.status}</td>
                    <td>
                        <RetryButton {essay} {batchId} pipeline={"SOME_PIPELINE"} />
                    </td>
                </tr>
            {/each}
        </tbody>
    </table>
{/if}
```

##### 4. Detailed Retry Logic Component

```html
<!-- src/lib/components/RetryButton.svelte -->
<script lang="ts">
    import { createMutation, useQueryClient } from '@tanstack/svelte-query';
    import { apiClient } from '$lib/api/client';
    import type { Essay } from '$lib/types/retry';

    export let essay: Essay;
    export let batchId: string;
    export let pipeline: string;

    let showConfirmation = false;
    const queryClient = useQueryClient();

    const isRetryable = essay.status?.includes('FAILED');
    const isCJAssessment = pipeline === 'CJ_ASSESSMENT';

    const retryMutation = createMutation({
        mutationFn: (retryData: { requested_pipeline: string; is_retry: boolean; retry_reason: string; }) => 
            apiClient.requestPipelineExecution(batchId, retryData), // This method needs to be added to apiClient
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['batch', batchId] });
            showConfirmation = false;
        },
    });

    function handleRetry() {
        $retryMutation.mutate({
            requested_pipeline: pipeline.toLowerCase(),
            is_retry: true,
            retry_reason: "User initiated retry from UI",
        });
    }

    function getConfirmationMessage() {
        if (essay.metadata?.error_category === 'TRANSIENT_NETWORK') {
            return "A network error occurred. Would you like to retry? (No additional cost)";
        }
        return "Retrying this pipeline may incur additional processing costs. Are you sure?";
    }
</script>

{#if isRetryable && !isCJAssessment}
    <button on:click={() => showConfirmation = true} class="px-3 py-1 text-sm bg-yellow-500 text-white rounded hover:bg-yellow-600">
        Retry
    </button>
{/if}

{#if showConfirmation}
    <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div class="bg-white p-6 rounded-lg max-w-md shadow-xl">
            <h3 class="text-lg font-semibold mb-4">Confirm Retry</h3>
            <p class="mb-4">{getConfirmationMessage()}</p>
            <div class="flex justify-end gap-2">
                <button on:click={() => showConfirmation = false} class="px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400">
                    Cancel
                </button>
                <button on:click={handleRetry} disabled={$retryMutation.isPending} class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50">
                    {#if $retryMutation.isPending} Retrying... {:else} Confirm Retry {/if}
                </button>
            </div>
        </div>
    </div>
{/if}
```

#### Done When

✅ Dashboard displays real-time status via WebSockets.
✅ The detailed retry logic, including cost-aware modals and CJ Assessment restrictions, is fully functional in Svelte.

---

### Checkpoint 2.6: Enhanced Features (Student & Class Management)

#### Objective

Implement the remaining user journey features using SvelteKit patterns, preserving all original detail.

#### Implementation

##### 1. Student Parsing Results Component (`src/lib/components/StudentParsingResults.svelte`)

*This component will translate the detailed JSX from the original plan into Svelte syntax. It will display confidence scores, allow selection via checkboxes bound to a local `Set`, and trigger a `createMutation` to confirm parsing results.*

```html
<!-- src/lib/components/StudentParsingResults.svelte -->
<script lang="ts">
    // ... imports for types and mutations
    export let parsingResults: StudentParsingResult[];
    export let batchId: string;

    let selectedResults = new Set<string>();

    const confirmParsingMutation = createMutation({ /* ... */ });

    function toggleSelection(essayId: string) {
        if (selectedResults.has(essayId)) {
            selectedResults.delete(essayId);
        } else {
            selectedResults.add(essayId);
        }
        selectedResults = selectedResults; // Force Svelte reactivity
    }
</script>

<div class="space-y-4">
    <!-- ... header with high-confidence count -->
    <div class="space-y-2">
        {#each parsingResults as result (result.essay_id)}
            <!-- ParsingResultCard.svelte component here -->
            <div class="border rounded-md p-3 {selectedResults.has(result.essay_id) ? 'border-blue-500 bg-blue-50' : 'border-gray-200'}">
                <input type="checkbox" checked={selectedResults.has(result.essay_id)} on:change={() => toggleSelection(result.essay_id)} />
                <!-- ... rest of the card details from original plan -->
            </div>
        {/each}
    </div>
    <button on:click={() => $confirmParsingMutation.mutate([...selectedResults])}>
        Confirm Selected ({selectedResults.size})
    </button>
</div>
```

##### 2. File Management Panel (`src/lib/components/FileManagementPanel.svelte`)

*This component will check the batch state to see if the panel should be locked. It will use two separate `createMutation` instances for adding and removing files, and the UI will be disabled based on their pending states.*

```html
<script lang="ts">
    // ... imports
    export let batchState: BatchStatus;
    export let batchId: string;

    const isLocked = batchState.pipeline_state?.SPELLCHECK?.status === 'COMPLETED' || batchState.pipeline_state?.SPELLCHECK?.status === 'IN_PROGRESS';

    const addFilesMutation = createMutation({ /* ... */ });
    const removeFileMutation = createMutation({ /* ... */ });
</script>

{#if isLocked}
    <div class="bg-yellow-50 border border-yellow-200 rounded-md p-4">
        <p class="text-yellow-800">Batch is locked for modifications.</p>
    </div>
{:else}
    <div class="space-y-4">
        <!-- FileDropzone component, disabled based on $addFilesMutation.isPending -->
        <!-- FileList component, with remove buttons disabled based on $removeFileMutation.isPending -->
    </div>
{/if}
```

##### 3. Real-time Updates for Management

*The `connectToBatchUpdates` function in `websockets.ts` will be expanded to handle events like `class.created`, `student.created`, `batch_file_added`, and `essay.student.association.updated`. These events will trigger `queryClient.invalidateQueries({ queryKey: ['user-classes'] })` or `queryClient.setQueryData(...)` to ensure all relevant parts of the UI are updated automatically.*

#### Done When

✅ All management UIs are functional and integrated with the API.
✅ Real-time events correctly invalidate and refresh data across the application.

---

### Checkpoint 2.7: Type Safety & Finalization

#### Objective

Ensure robust, type-safe communication and graceful error handling.

#### Implementation

##### 1. Automated Type Generation

*The `pnpm run generate-types` script using `openapi-typescript` remains unchanged.*

##### 2. Fully Typed API Client

*The `apiClient` in `src/lib/api/client.ts` will be updated to import and use the auto-generated types from `schema.ts` for all method signatures and return types, just as in the detailed React plan.*

```typescript
// src/lib/api/client.ts (Enhanced)
import type { components, paths } from './schema'; // Auto-generated types

type BatchStatus = components['schemas']['BatchStatusResponse'];
type PipelineRequest = components['schemas']['PipelineExecutionRequest'];
// ... and so on for all required types.

class ApiClient {
    // ...
    async getBatchStatus(batchId: string): Promise<BatchStatus> {
        const response = await this.client.get(`/v1/batches/${batchId}/status`);
        return response.data;
    }
    // ... other typed methods
}
```

##### 3. SvelteKit Error Handling

*A global `src/routes/+error.svelte` file will be created to catch all unhandled exceptions.*

```html
<!-- src/routes/+error.svelte -->
<script lang="ts">
    import { page } from '$app/stores';
</script>

<div class="text-center p-10">
    <h1 class="text-4xl font-bold text-red-600">{$page.status}</h1>
    <p class="mt-4 text-lg">{$page.error?.message}</p>
    <a href="/" class="mt-6 inline-block px-4 py-2 bg-blue-500 text-white rounded">Go Home</a>
</div>
```

#### Done When

✅ `generate-types` script works.
✅ API client is fully typed.
✅ A global `+error.svelte` page is implemented.
