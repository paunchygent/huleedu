# HuleEdu Frontend MVP: Implementation Plan & PRD

This document outlines the Product Requirements Document (PRD) and a phased implementation plan for the HuleEdu Frontend MVP. It translates the user journey into a concrete architectural and feature roadmap, building upon the established backend services.

## ⚠️ **CRITICAL PREREQUISITES**

**IMPLEMENTATION DEPENDENCY**: This frontend implementation requires the completion of the API Gateway implementation (API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_1.md, _2.md,_3.md) and should align with the Client Retry Framework (CLIENT_RETRY_FRAMEWORK_IMPLEMENTATION.md).

**Implementation Sequence**:

1. ✅ Complete API Gateway Service implementation (Tickets 1-3)
2. ✅ Verify API Gateway endpoints are functional
3. ✅ Update API Gateway CORS configuration for Vite
4. 🔄 **START HERE**: Frontend implementation

## Part 1: Project Setup & Foundation (The "Bulletproof" Base)

### Objective

To establish a modern, stable, and scalable frontend project within the existing PDM monorepo. This deliberate setup ensures maintainability and a smooth development experience by using industry-standard tooling and practices from the outset. This phase is about building a strong foundation to prevent technical debt.

### Checkpoint 4.1: Monorepo Integration & Tooling

#### Objective

Correctly scaffold a new Vite + React + TypeScript project and integrate it into the monorepo structure using pnpm, a modern and efficient JavaScript package manager.

#### Implementation Steps

##### 1. Create Frontend Directory

In the monorepo root, create a new `frontend` directory. This isolates the Node.js/JavaScript ecosystem from the Python-based backend services, which is a clean and standard practice in polyglot monorepos.

```bash
# Run from the root of the huledu-reboot repository
mkdir frontend
cd frontend
```

##### 2. Initialize with pnpm

We will use `pnpm` as our package manager. It is explicitly chosen over older managers like `npm` or `yarn` for its superior performance in monorepo environments. `pnpm` avoids duplicating dependencies by using a content-addressable store and symlinks, which saves significant disk space and speeds up installation times. This solves the "phantom dependency" and "doppelganger" issues common in complex `node_modules` structures.

First, install pnpm globally using npm (which comes with Node.js):

```bash
npm install -g pnpm
```

##### 3. Scaffold the Vite Project

Use pnpm to create a new Vite project. Vite is a next-generation frontend tooling that provides an extremely fast development server with Hot Module Replacement (HMR) and optimized production builds. The `react-ts` template gives us a TypeScript-ready React setup out of the box.

```bash
# Run this inside the 'frontend' directory
pnpm create vite . --template react-ts
```

When prompted, name the package `huledu-frontend` to give it a clear identifier within the monorepo.

##### 4. Configure Monorepo Workspaces

To enable pnpm to manage the entire monorepo, create a `pnpm-workspace.yaml` file in the root of your `huledu-reboot` repository. This file declares which directories contain manageable packages.

File: `pnpm-workspace.yaml` (in the repository root)

```yaml
packages:
  # Include the new frontend package
  - 'frontend'
  # You can also make pnpm aware of your Python packages if you wish,
  # though it will not manage their dependencies.
  - 'services/**'
  - 'common_core'
```

This configuration is the key to treating the repository as a cohesive whole, allowing you to run scripts across different packages from the root in the future.

##### 5. Update API Gateway CORS Configuration

**CRITICAL**: Update the API Gateway CORS configuration to include Vite's default port.

File: `services/api_gateway_service/config.py`

```python
CORS_ORIGINS: list[str] = Field(
    default=[
        "http://localhost:3000",  # Create React App default
        "http://localhost:3001",  # Alternative React port
        "http://localhost:5173",  # Vite default - ADD THIS
    ],
    description="Allowed CORS origins for React frontend",
)
```

#### Done When

✅ The `frontend` directory exists and contains a functional Vite + React + TS project.
✅ You can run `pnpm install` inside the `frontend` directory, and it successfully creates a `node_modules` folder and a `pnpm-lock.yaml` file.
✅ You can run `pnpm dev` inside the `frontend` directory, which starts the Vite development server, and you can access the default React application in your browser.
✅ API Gateway CORS is updated to allow Vite development server connections.

### Checkpoint 4.2: Core Dependencies & Configuration (Enhanced)

#### Objective

Install and configure the core libraries for routing, styling, state management, API communication, and real-time updates. The selection is based on modern best practices that prioritize developer experience, performance, and long-term maintainability.

#### Implementation Steps

##### 1. Install Core Libraries

Navigate into the `frontend` directory and add the following dependencies using pnpm. We will install them in logical groups.

```bash
# Ensure you are inside the 'frontend' directory
cd frontend
```

**Routing**: The standard for navigation in React SPAs

```bash
pnpm add react-router-dom
```

**State Management**: A powerful combination for server and client state

```bash
pnpm add @tanstack/react-query zustand
```

**API Communication**: A reliable HTTP client

```bash
pnpm add axios
```

**UI Components & Styling**: Install Tailwind CSS and its dependencies as development tools

```bash
pnpm add -D tailwindcss postcss autoprefixer
```

**Utility libraries** for styling and icons

```bash
pnpm add class-variance-authority clsx tailwind-merge lucide-react
```

**Enhanced Dependencies for Real-time & File Handling**

```bash
# File upload with drag-and-drop
pnpm add react-dropzone

# Enhanced TypeScript support
pnpm add -D @types/react @types/node

# JWT handling
pnpm add js-cookie
pnpm add -D @types/js-cookie

# Error boundary support
pnpm add react-error-boundary
```

##### 2. Configure Tailwind CSS

Initialize Tailwind CSS to enable its utility-first styling workflow.

Run the initialization command:

```bash
pnpm exec tailwindcss init -p
```

This creates `tailwind.config.js` and `postcss.config.js`.

Modify `tailwind.config.js` to tell Tailwind which files to scan for utility classes:

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}", // Scan all relevant files in the src directory
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

Finally, add the Tailwind directives to the top of your main CSS file, `src/index.css`, to inject its base, component, and utility styles into your application:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

##### 3. Configure Environment Variables

Create a `.env.local` file for development configuration:

```bash
# API Gateway configuration
VITE_API_BASE_URL=http://localhost:4001
VITE_WS_BASE_URL=ws://localhost:4001

# Development settings
VITE_ENV=development
```

#### Rationale for Library Choices (Enhanced)

**`react-router-dom`**: Chosen because it is the de-facto standard for building single-page applications in React. Its component-based approach to routing integrates seamlessly with React's philosophy.

**`tailwindcss`**: We are choosing Tailwind over component libraries like Bootstrap or Material-UI to avoid being locked into a specific visual design. Tailwind provides low-level utility classes (flex, pt-4, text-center) that let you build completely custom designs without writing a single line of custom CSS, ensuring a professional and unique look that is also incredibly fast and maintainable.

**`@tanstack/react-query`**: This is not just a data-fetching library; it's a server state management tool. It replaces hand-rolled `useEffect` and `useState` hooks for API calls. It automatically handles caching, background refetching, and request deduplication, which will make your application feel much faster and more responsive to the user, while simplifying your code.

**`zustand`**: For client-side state (like "is the sidebar open?" or "what is the logged-in user's name?"), we need a global store. Redux is often overkill. Zustand provides a minimal, hook-based API that is extremely fast and easy to understand, making it a perfect lightweight choice.

**`axios`**: While `fetch` is built-in, `axios` offers a more ergonomic API with features like automatic JSON transformation, better error handling, and the ability to set up "interceptors"—code that runs on every request or response, which is perfect for automatically attaching the JWT authentication token to outgoing API calls.

**`react-dropzone`**: Provides accessible, polished drag-and-drop file upload functionality that integrates well with React's component model.

**`react-error-boundary`**: Essential for handling retry scenarios and providing graceful error recovery in the UI.

**`js-cookie`**: Secure JWT token storage and management with proper httpOnly cookie support.

#### Done When

✅ All specified dependencies are listed in `frontend/package.json`.
✅ You can apply a Tailwind class like `<div className="bg-blue-500 text-white p-4">Hello World</div>` in `App.tsx` and see the styled output in your browser, confirming the CSS pipeline is working.
✅ Environment variables are properly configured for API Gateway integration.

## Part 2: Feature Implementation Plan (The PRD)

### Objective

To implement the user journey feature by feature, building upon the solid foundation from Part 1. Each checkpoint represents a vertical slice of functionality that delivers tangible value and moves us closer to the MVP.

### Checkpoint 4.3: Authentication & Application Layout (API Gateway Aligned)

#### Objective

Implement the public-facing pages (Login, Register) and the main authenticated application layout aligned with the API Gateway's JWT authentication requirements. This creates the secure shell within which the rest of the application will live.

#### User Journey

"Register... email confirmation... Log in... email link option and normal username password."

#### Implementation Plan

##### 1. Create API Client with JWT Integration

Create a typed API client that integrates with the API Gateway's authentication requirements.

File: `src/api/client.ts`

```typescript
import axios, { AxiosInstance, AxiosResponse } from 'axios';
import Cookies from 'js-cookie';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:4001';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 10000, // Match API Gateway timeout configuration
    });

    // Add JWT token to all requests
    this.client.interceptors.request.use((config) => {
      const token = Cookies.get('auth_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Handle token expiry
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          Cookies.remove('auth_token');
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  // API Gateway aligned methods
  async requestPipelineExecution(batchId: string, pipeline: string) {
    return this.client.post(`/v1/batches/${batchId}/pipelines`, {
      batch_id: batchId,
      requested_pipeline: pipeline,
    });
  }

  async getBatchStatus(batchId: string) {
    return this.client.get(`/v1/batches/${batchId}/status`);
  }

  async retryBatch(batchId: string, retryData: {
    phase?: string;
    reason: string;
    essay_ids?: string[];
  }) {
    return this.client.post(`/v1/batches/${batchId}/retry`, retryData);
  }
}

export const apiClient = new ApiClient();
```

##### 2. Create Layout Components

* `AuthLayout.tsx`: A simple, reusable component that provides a consistent centered layout for all authentication-related forms (Login, Register, Forgot Password).
* `DashboardLayout.tsx`: The main application shell for authenticated users. This will contain a persistent `Sidebar` component for navigation (e.g., links to Dashboard, Classes, Account) and a `Header` component showing the user's name and a logout button. This ensures a consistent user experience across all internal pages.

##### 3. Create Auth Pages & Components

* `LoginPage.tsx`: A form with two tabs or sections: one for traditional email/password login, and another for a "magic link" login that just takes an email address.
* `RegisterPage.tsx`: A standard registration form collecting name, email, and password. It should include client-side validation for password strength and email format before submission.
* `EmailConfirmationPage.tsx`: A simple page that captures a token from the URL, sends it to a verification endpoint on the API Gateway, and displays a success or failure message to the user.

##### 4. Implement Routing & Protection

In `App.tsx`, define the routes for these pages. Create a `ProtectedRoute` component that checks the Zustand auth store for a valid token. If no token exists, it redirects the user to the `/login` page. The entire `/dashboard` route and its children will be wrapped in this `ProtectedRoute`.

##### 5. API Integration

Use `@tanstack/react-query`'s `useMutation` hook within the form components. This hook simplifies handling the API request lifecycle:

* It provides an `isPending` state to disable the submit button and show a spinner.
* It provides an `isError` state to display API-level error messages (e.g., "Invalid credentials").
* It provides an `onSuccess` callback to handle post-login logic.

##### 6. State Management with JWT Handling

Create a `useAuthStore` using `zustand` with proper JWT token management:

File: `src/stores/authStore.ts`

```typescript
import { create } from 'zustand';
import Cookies from 'js-cookie';

interface User {
  id: string;
  email: string;
  name: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
  initializeAuth: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: null,
  isAuthenticated: false,

  login: (token: string, user: User) => {
    Cookies.set('auth_token', token, { 
      secure: true, 
      sameSite: 'strict',
      expires: 1 // 1 day, align with API Gateway JWT expiry
    });
    set({ token, user, isAuthenticated: true });
  },

  logout: () => {
    Cookies.remove('auth_token');
    set({ token: null, user: null, isAuthenticated: false });
  },

  initializeAuth: () => {
    const token = Cookies.get('auth_token');
    if (token) {
      // Validate token and get user info
      // This should call the API Gateway to verify the token
      set({ token, isAuthenticated: true });
    }
  },
}));
```

#### Done When

✅ A user can navigate to `/login` and `/register`, and the forms are functional.
✅ Attempting to access `/dashboard` without being logged in redirects the user to `/login`.
✅ Upon successful login, the user is redirected to `/dashboard`, their token and user info are stored in the Zustand store, and the `DashboardLayout` is visible.
✅ JWT tokens are properly managed with secure cookies and automatic refresh handling.
✅ API client automatically attaches JWT tokens to requests and handles 401 responses.

### Checkpoint 4.4: Teacher Dashboard & File Upload

#### Objective

Create the main dashboard view and the complete file upload workflow, which is the primary entry point for a teacher's core task.

#### User Journey

"A dashboard with... a very clear path to file upload view, where you can drag and drop batches... enter or select already created class designations... select course... enter essay instructions... select if teacher name should be included..."

#### Implementation Plan

##### 1. `TeacherDashboardPage.tsx`

This is the homepage for a logged-in teacher.

* It will feature a prominent, clear "Upload New Essay Batch" CTA (Call To Action) button that navigates to `/dashboard/upload`.
* Below the CTA, it will display a table or a grid of the teacher's previously uploaded batches. This data will be fetched using `useQuery` targeting the API Gateway endpoint `GET /v1/batches`. Each item in the list will link to its respective `ProcessingDashboardPage`.

##### 2. `FileUploadPage.tsx`

This page will guide the user through the batch creation and file upload process.

**Component Structure**: The page will be composed of smaller, reusable components:

* `BatchMetadataForm.tsx`: A form section for "Class Designation," "Course," and "Essay Instructions." The dropdowns for Course and Class will be populated via API calls using `useQuery`, but will also include an option to create a new entry.
* `AIOptions.tsx`: A simple component with a checkbox for "Include teacher name in AI-generated response."
* `FileUploadZone.tsx`: This will use the `react-dropzone` library to provide a polished, accessible drag-and-drop area. It will show a list of staged files (the files the user has selected) with the ability to remove a file before uploading.

**API Call Logic**: The submission process will be a two-step sequence handled by a single "Submit" button:

* **Register Batch**: First, the component sends only the batch metadata (`BatchMetadataForm`) to the API Gateway. The UI will show a "Registering batch..." state.
* **Upload Files**: Once the API returns a success response with the new `batch_id`, the component will then begin uploading the files one by one to the File Service endpoint, including the `batch_id` in each request. The UI will show an upload progress bar.

#### Done When

✅ A teacher can see a list of their past batches on the main dashboard.
✅ A teacher can fill out the batch details form and stage files for upload.
✅ Clicking "Submit" successfully registers the batch and then uploads the files.
✅ The application correctly navigates the user to `/dashboard/processing/{new_batch_id}` upon completion.

### Checkpoint 4.5: Processing Dashboard with Enhanced Retry Framework

#### Objective

Implement the real-time processing dashboard, including the comprehensive client-initiated retry functionality from the CLIENT_RETRY_FRAMEWORK_IMPLEMENTATION. This is the most complex and interactive part of the MVP.

#### User Journey

"track the file uploads using the hydrate once and then Websocket connection kicks in... each file can be viewed and deleted/replaced... a processing panel becomes accessible for pipeline choices... user selects the processing... transitions into live updates... a user initiated retry button..."

#### Implementation Plan

##### 1. Enhanced Type Definitions

Create comprehensive types for the retry framework:

File: `src/types/retry.ts`

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
  status: EssayStatus;
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

##### 2. WebSocket Integration with React Query

Create a custom hook that syncs WebSocket updates with React Query cache:

File: `src/hooks/useWebSocketUpdates.ts`

```typescript
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../stores/authStore';

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:4001';

export function useWebSocketUpdates(batchId: string) {
  const queryClient = useQueryClient();
  const { token } = useAuthStore();

  useEffect(() => {
    if (!token || !batchId) return;

    const ws = new WebSocket(`${WS_BASE_URL}/ws?token=${token}`);
    
    ws.onopen = () => {
      console.log('WebSocket connected for batch:', batchId);
    };

    ws.onmessage = (event) => {
      try {
        const update = JSON.parse(event.data);
        
        // Handle different event types
        switch (update.event) {
          case 'batch_phase_concluded':
            if (update.batch_id === batchId) {
              queryClient.setQueryData(['batch', batchId], (old: any) => ({
                ...old,
                pipeline_state: {
                  ...old?.pipeline_state,
                  [update.phase]: update.status,
                },
                last_updated: update.timestamp,
              }));
            }
            break;
            
          case 'essay_status_updated':
            if (update.batch_id === batchId) {
              queryClient.setQueryData(['batch', batchId], (old: any) => ({
                ...old,
                essays: old?.essays?.map((essay: Essay) => 
                  essay.essay_id === update.essay_id 
                    ? { ...essay, status: update.status, metadata: update.metadata }
                    : essay
                ),
                last_updated: update.timestamp,
              }));
            }
            break;
            
          case 'ping':
            // Heartbeat - no action needed
            break;
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
    };

    return () => {
      ws.close();
    };
  }, [batchId, token, queryClient]);
}
```

##### 3. Enhanced Retry Logic Components

Create sophisticated retry handling components aligned with **simplified retry approach** (see `045-retry-logic.mdc`):

**Note**: HuleEdu implements **natural retry** through the idempotency system. User-initiated retries leverage existing `ClientBatchPipelineRequestV1` with `is_retry` flag rather than complex retry command infrastructure.

File: `src/components/RetryButton.tsx`

```typescript
import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';

interface RetryButtonProps {
  essay: Essay;
  batchId: string;
  pipeline: string;
  onRetrySuccess?: () => void;
}

export function RetryButton({ essay, batchId, pipeline, onRetrySuccess }: RetryButtonProps) {
  const [showConfirmation, setShowConfirmation] = useState(false);
  const queryClient = useQueryClient();

  // Check if essay is retryable based on failure status
  const isRetryable = essay.status.includes('FAILED');
  
  // Special handling for CJ Assessment - no individual essay retries
  const isCJAssessment = pipeline === 'CJ_ASSESSMENT';
  
  if (!isRetryable || isCJAssessment) {
    return null;
  }

  // Use existing pipeline request pattern with is_retry flag
  const retryMutation = useMutation({
    mutationFn: (retryData: { 
      requested_pipeline: string; 
      is_retry: boolean; 
      retry_reason: string;
    }) => apiClient.requestPipelineExecution(batchId, retryData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batch', batchId] });
      setShowConfirmation(false);
      onRetrySuccess?.();
    },
  });

  const handleRetry = () => {
    retryMutation.mutate({
      requested_pipeline: pipeline.toLowerCase(),
      is_retry: true,
      retry_reason: "User initiated retry from UI",
    });
  };

  const getConfirmationMessage = () => {
    if (essay.metadata?.error_category === 'TRANSIENT_NETWORK') {
      return "A network error occurred. Would you like to retry? (No additional cost)";
    }
    
    return "Retrying this pipeline may incur additional processing costs. Are you sure you want to proceed?";
  };

  if (showConfirmation) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white p-6 rounded-lg max-w-md">
          <h3 className="text-lg font-semibold mb-4">Confirm Retry</h3>
          <p className="mb-4">{getConfirmationMessage()}</p>
          <div className="flex gap-2">
            <button
              onClick={handleRetry}
              disabled={retryMutation.isPending}
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
            >
              {retryMutation.isPending ? 'Retrying...' : 'Confirm Retry'}
            </button>
            <button
              onClick={() => setShowConfirmation(false)}
              className="px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <button
      onClick={() => setShowConfirmation(true)}
      className="px-3 py-1 text-sm bg-yellow-500 text-white rounded hover:bg-yellow-600"
    >
      Retry
    </button>
  );
}
```

##### 4. `ProcessingDashboardPage.tsx` Logic

Enhanced with WebSocket integration and comprehensive retry handling:

* Use `useParams` from `react-router-dom` to extract the `batchId` from the URL.
* **Hydrate**: Use `useQuery({ queryKey: ['batch', batchId], ... })` to make the initial API Gateway status call.
* **Update**: Use the `useWebSocketUpdates` hook for real-time synchronization.
* **Retry Management**: Integrate the enhanced retry framework with proper error categorization.

##### 5. Component Structure

* `BatchInfoPanel.tsx`: A component that displays the batch's metadata (course, instructions). An "Edit" button can make these fields editable, triggering a `useMutation` to update the data.
* `FileList.tsx`: Renders a detailed table of the essays in the batch with enhanced retry capabilities. Each row represents a file and displays columns for Filename, Status, Actions, and Retry Count. The Status cell will be a badge whose color and text changes based on the real-time data from the query cache.
* `PipelinePanel.tsx`: This panel is initially disabled. It becomes active once the batch status is `READY_FOR_PIPELINE_EXECUTION`. It will contain buttons for each available pipeline (e.g., "Start AI Feedback"). Clicking a button will trigger a `useMutation` to the pipeline initiation endpoint.
* `BatchRetryPanel.tsx`: Special component for CJ Assessment that only allows full batch retries with cost warnings.

#### Done When

✅ The dashboard correctly displays the initial state of an uploaded batch fetched from the API Gateway.
✅ The UI status for individual essays updates in real-time as WebSocket events are received, without a full page reload.
✅ The "Retry" button only appears for essays that have failed in a retryable way.
✅ CJ Assessment enforces batch-only retry with appropriate UI restrictions.
✅ The cost-aware confirmation modal displays the correct message based on the failure type and error category.
✅ A user can successfully initiate a retry, and the essay's status optimistically updates to "PENDING" or "RETRYING" in the UI.
✅ WebSocket updates are properly synchronized with React Query cache without causing UI flicker.
✅ Retry count and metadata are displayed in the UI for transparency.

### Checkpoint 4.6 - 4.8: Remaining Dashboards (Stubs & Final Implementation)

#### Objective

Build out the remaining user journey views to complete the MVP functionality.

#### Implementation Plan

##### 1. Results Dashboards (`/results/:batchId/...`)

The parent route `/results/:batchId` will have a `ResultsLayout` component that includes tabs for "AI Feedback," "NLP Stats," and "CJ Assessment."
Each tab will link to a sub-route (e.g., `/results/:batchId/nlp-stats`).
Each child page (`AIFeedbackPage`, etc.) will use `useQuery` to fetch its specific data from the API Gateway. This keeps the data fetching isolated and efficient.

##### 2. Class & Student Management (`/classes`)

This page will feature a two-panel layout. On the left, a list of the teacher's classes. Clicking a class populates the right panel with a table of students in that class.
The page will use `useQuery` to fetch classes and students, and `useMutation` hooks tied to buttons for "Add Class," "Add Student," "Edit," and "Delete" actions. These actions will be wrapped in confirmation modals.

##### 3. Account Page (`/account`)

This will be a simple settings page with distinct sections:

* A form to update user profile information (name).
* A form to change the password.
* A section displaying API usage and rate limit information (fetched from the API).
* A link to the off-site Stripe portal for subscription management.
* A "Delete Account" button within a "Danger Zone" section that requires password re-entry for confirmation.

##### 4. Admin Dashboard (`/admin`)

This route will be protected by an additional role-based check (`if (user.role !== 'admin') redirect`).
It will primarily consist of a table of registered users with columns for Email, Status (Pending, Active, Banned), and Actions.
The "Actions" column will contain buttons ("Approve", "Ban") that trigger `useMutation` hooks to call the corresponding admin API endpoints.

#### Done When

✅ All primary views from the user journey are created and navigable via the sidebar.
✅ The core functionality for each view (displaying data, basic forms) is implemented and connected to API Gateway endpoints.

## Part 3: Finalizing the Foundation

### Objective

Ensure robust, type-safe communication between the frontend and the API Gateway, fulfilling your key requirement for type safety mirroring the backend.

### Checkpoint 4.9: API Client & Type Generation (Enhanced)

#### Implementation Plan

##### 1. Finalize OpenAPI Spec Integration

Once the API Gateway's OpenAPI documentation at `/docs` is complete, integrate it with the frontend type generation workflow.

##### 2. Automate Type Generation

Implement the `pnpm run generate-frontend-types` script with fallback support:

File: `frontend/package.json`

```json
{
  "scripts": {
    "generate-types": "openapi-typescript http://localhost:4001/openapi.json -o src/api/schema.ts",
    "generate-types-file": "openapi-typescript ../services/api_gateway_service/openapi.json -o src/api/schema.ts",
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  }
}
```

**Workflow Integration**: This script should become part of the CI/CD pipeline. If a backend developer changes a Pydantic model that affects an API endpoint, the CI process should fail until the `generate-frontend-types` script is run and the updated `schema.ts` is committed.

##### 3. Enhanced Typed API Client

Enhance the API client with full type safety:

File: `src/api/client.ts` (Enhanced)

```typescript
import axios, { AxiosInstance } from 'axios';
import Cookies from 'js-cookie';
import { components, paths } from './schema'; // Auto-generated types

type BatchStatus = components['schemas']['BatchStatusResponse'];
type PipelineRequest = components['schemas']['PipelineExecutionRequest'];
type RetryRequest = components['schemas']['BatchRetryRequest'];

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:4001',
      timeout: 10000, // Match API Gateway timeout configuration
    });

    // Add JWT token to all requests
    this.client.interceptors.request.use((config) => {
      const token = Cookies.get('auth_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Handle token expiry
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          Cookies.remove('auth_token');
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  async requestPipelineExecution(
    batchId: string, 
    request: PipelineRequest
  ): Promise<components['schemas']['PipelineExecutionResponse']> {
    const response = await this.client.post(`/v1/batches/${batchId}/pipelines`, request);
    return response.data;
  }

  async getBatchStatus(batchId: string): Promise<BatchStatus> {
    const response = await this.client.get(`/v1/batches/${batchId}/status`);
    return response.data;
  }

  async retryBatch(
    batchId: string, 
    retryData: RetryRequest
  ): Promise<components['schemas']['RetryResponse']> {
    const response = await this.client.post(`/v1/batches/${batchId}/retry`, retryData);
    return response.data;
  }
}

export const apiClient = new ApiClient();
```

##### 4. Error Boundary Integration

Add comprehensive error handling:

File: `src/components/ErrorBoundary.tsx`

```typescript
import React from 'react';
import { ErrorBoundary } from 'react-error-boundary';

function ErrorFallback({ error, resetErrorBoundary }: any) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-6">
        <div className="flex items-center">
          <div className="flex-shrink-0">
            <svg className="h-8 w-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-gray-800">Application Error</h3>
            <div className="mt-2 text-sm text-gray-500">
              <p>Something went wrong. Please try again.</p>
            </div>
          </div>
        </div>
        <div className="mt-4">
          <button
            onClick={resetErrorBoundary}
            className="w-full bg-red-600 text-white py-2 px-4 rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500"
          >
            Try Again
          </button>
        </div>
      </div>
    </div>
  );
}

export function AppErrorBoundary({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary
      FallbackComponent={ErrorFallback}
      onError={(error, errorInfo) => {
        console.error('Application error:', error, errorInfo);
        // Send to error reporting service
      }}
    >
      {children}
    </ErrorBoundary>
  );
}
```

#### Done When

✅ Running `pnpm run generate-types` successfully generates a comprehensive `frontend/src/api/schema.ts` file.
✅ All API calls throughout the application are made through the typed API client wrapper.
✅ There is a clear, documented process for developers to update the types when the backend API changes.
✅ Error boundaries provide graceful error recovery throughout the application.
✅ WebSocket integration is robust and handles connection failures gracefully.

## 🚀 **Implementation Summary**

This enhanced frontend plan provides:

1. **Perfect API Gateway Alignment**: All endpoints, authentication, and WebSocket integration match the backend implementation
2. **Comprehensive Retry Framework**: Full support for the complex retry requirements including CJ Assessment batch-only retries
3. **Modern, Lightweight Tech Stack**: Vite, React, TypeScript, TanStack Query, Zustand - optimal for performance and DX
4. **Real-time Synchronization**: Sophisticated WebSocket integration with React Query cache
5. **Type Safety**: Complete OpenAPI integration for end-to-end type safety
6. **Production Ready**: Error boundaries, proper JWT handling, and graceful degradation

The plan maintains backwards compatibility while adding the sophisticated features required by the HuleEdu platform's advanced backend architecture.

---

## 📋 **Enhanced Features Implementation Plan**

### **Connection to API Gateway User ID Propagation (Checkpoint 1.4)**

The following enhanced features should be implemented as connected tasks to the User ID Propagation checkpoint, providing a comprehensive file and batch management system.

### **Phase 1: Enhanced Batch & File Management (Connected to Checkpoint 1.4)**

#### **Task 1.4.1: Enhanced Batch Registration**

**Objective**: Extend batch registration to support class/course validation and student management.

**Frontend Changes**:

```typescript
// Enhanced batch registration form
interface EnhancedBatchRegistrationRequest {
  expected_essay_count: number;
  course_code: 'ENG5' | 'ENG6' | 'ENG7' | 'SV1' | 'SV2' | 'SV3';
  class_id?: string; // Optional existing class
  class_designation: string;
  teacher_name: string;
  essay_instructions: string;
  enable_student_parsing: boolean;
}

// Course selection with language inference
const CourseSelector = () => {
  const courses = [
    { code: 'ENG5', name: 'English 5', language: 'en', level: 5 },
    { code: 'ENG6', name: 'English 6', language: 'en', level: 6 },
    { code: 'ENG7', name: 'English 7', language: 'en', level: 7 },
    { code: 'SV1', name: 'Svenska 1', language: 'sv', level: 1 },
    { code: 'SV2', name: 'Svenska 2', language: 'sv', level: 2 },
    { code: 'SV3', name: 'Svenska 3', language: 'sv', level: 3 },
  ];
  
  return (
    <select name="course_code" required>
      {courses.map(course => (
        <option key={course.code} value={course.code}>
          {course.name} ({course.language.toUpperCase()})
        </option>
      ))}
    </select>
  );
};
```

#### **Task 1.4.2: File Management Post-Upload**

**Objective**: Allow teachers to add/remove files before spellcheck begins.

**Frontend Components**:

```typescript
// File management component with batch state validation
const FileManagementPanel = ({ batchId, batchState }: {
  batchId: string;
  batchState: BatchStatus;
}) => {
  const isLocked = batchState.pipeline_state?.SPELLCHECK?.status === 'COMPLETED' ||
                   batchState.pipeline_state?.SPELLCHECK?.status === 'IN_PROGRESS';

  const addFilesMutation = useMutation({
    mutationFn: (files: File[]) => apiClient.addFilesToBatch(batchId, files),
    enabled: !isLocked,
  });

  const removeFileMutation = useMutation({
    mutationFn: (essayId: string) => apiClient.removeFileFromBatch(batchId, essayId),
    enabled: !isLocked,
  });

  if (isLocked) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4">
        <p className="text-yellow-800">
          <LockIcon className="inline w-4 h-4 mr-2" />
          Batch is locked for modifications. Spellcheck has started.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <FileDropzone 
        onFilesAdded={(files) => addFilesMutation.mutate(files)}
        disabled={addFilesMutation.isPending}
      />
      <FileList 
        files={batchState.essays}
        onFileRemove={(essayId) => removeFileMutation.mutate(essayId)}
        removeDisabled={removeFileMutation.isPending}
      />
    </div>
  );
};
```

**Real-time Updates**:

```typescript
// Enhanced WebSocket integration for file management
const useFileManagementUpdates = (batchId: string) => {
  const queryClient = useQueryClient();

  useWebSocketUpdates(batchId, {
    onMessage: (event) => {
      switch (event.event) {
        case 'batch_file_added':
          queryClient.setQueryData(['batch', batchId], (old: BatchStatus) => ({
            ...old,
            essays: [...(old?.essays || []), {
              essay_id: event.essay_id,
              filename: event.filename,
              status: 'UPLOADED',
            }],
          }));
          break;
          
        case 'batch_file_removed':
          queryClient.setQueryData(['batch', batchId], (old: BatchStatus) => ({
            ...old,
            essays: old?.essays?.filter(essay => essay.essay_id !== event.essay_id) || [],
          }));
          break;
          
        case 'batch_locked_for_processing':
          queryClient.setQueryData(['batch', batchId], (old: BatchStatus) => ({
            ...old,
            is_locked: true,
            locked_at: event.locked_at,
          }));
          break;
      }
    }
  });
};
```

### **Phase 2: Class Management Service Integration**

#### **Task 2.1: Class & Student Management UI**

**Objective**: Provide comprehensive class and student management capabilities.

**Frontend Implementation**:

```typescript
// Class management page with student associations
const ClassManagementPage = () => {
  const { data: classes } = useQuery({
    queryKey: ['user-classes'],
    queryFn: () => apiClient.getUserClasses(),
  });

  const { data: students } = useQuery({
    queryKey: ['user-students'],
    queryFn: () => apiClient.getUserStudents(),
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <ClassPanel 
        classes={classes}
        onClassCreate={handleClassCreate}
        onClassUpdate={handleClassUpdate}
      />
      <StudentPanel 
        students={students}
        classes={classes}
        onStudentCreate={handleStudentCreate}
        onStudentAssign={handleStudentAssign}
      />
    </div>
  );
};

// Student-essay association interface
const StudentEssayAssociationPanel = ({ 
  batchId, 
  essays, 
  students 
}: {
  batchId: string;
  essays: Essay[];
  students: Student[];
}) => {
  const associationMutation = useMutation({
    mutationFn: ({ essayId, studentId }: { essayId: string; studentId: string }) =>
      apiClient.associateEssayWithStudent(batchId, essayId, studentId),
  });

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold">Student-Essay Associations</h3>
      {essays.map(essay => (
        <div key={essay.essay_id} className="flex items-center space-x-4 p-3 border rounded">
          <span className="flex-1">{essay.filename}</span>
          {essay.parsed_student_name && (
            <span className="text-sm text-green-600">
              Parsed: {essay.parsed_student_name}
            </span>
          )}
          <select
            value={essay.associated_student_id || ''}
            onChange={(e) => associationMutation.mutate({
              essayId: essay.essay_id,
              studentId: e.target.value,
            })}
            className="border rounded px-2 py-1"
          >
            <option value="">Select Student</option>
            {students.map(student => (
              <option key={student.id} value={student.id}>
                {student.name} ({student.email})
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
};
```

#### **Task 2.2: Enhanced Student Parsing Integration**

**Objective**: Integrate automatic student parsing with manual override capabilities following thin event patterns.

**Frontend Components**:

```typescript
// Student parsing results display - aligned with thin event structure
const StudentParsingResults = ({ 
  batchId, 
  parsingResults 
}: {
  batchId: string;
  parsingResults: StudentParsingResult[];
}) => {
  const [selectedResults, setSelectedResults] = useState<Set<string>>(new Set());

  const confirmParsingMutation = useMutation({
    mutationFn: (confirmedResults: StudentParsingResult[]) =>
      apiClient.confirmStudentParsing(batchId, confirmedResults),
  });

  return (
    <div className="space-y-4">
      <div className="bg-blue-50 border border-blue-200 rounded-md p-4">
        <h4 className="font-semibold text-blue-800">Automatic Student Parsing Results</h4>
        <p className="text-blue-600 text-sm">
          {parsingResults.filter(r => r.confidence_score > 0.8).length} high-confidence matches found
        </p>
      </div>

      <div className="space-y-2">
        {parsingResults.map(result => (
          <ParsingResultCard
            key={result.essay_id}
            result={result}
            selected={selectedResults.has(result.essay_id)}
            onToggle={(essayId) => {
              const newSelected = new Set(selectedResults);
              if (newSelected.has(essayId)) {
                newSelected.delete(essayId);
              } else {
                newSelected.add(essayId);
              }
              setSelectedResults(newSelected);
            }}
          />
        ))}
      </div>

      <div className="flex space-x-2">
        <button
          onClick={() => confirmParsingMutation.mutate(
            parsingResults.filter(r => selectedResults.has(r.essay_id))
          )}
          disabled={selectedResults.size === 0 || confirmParsingMutation.isPending}
          className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 disabled:opacity-50"
        >
          Confirm Selected ({selectedResults.size})
        </button>
        <button
          onClick={() => setSelectedResults(new Set())}
          className="px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400"
        >
          Clear Selection
        </button>
      </div>
    </div>
  );
};

const ParsingResultCard = ({ 
  result, 
  selected, 
  onToggle 
}: {
  result: StudentParsingResult;
  selected: boolean;
  onToggle: (essayId: string) => void;
}) => {
  const confidenceColor = result.confidence_score > 0.8 ? 'green' : 
                         result.confidence_score > 0.5 ? 'yellow' : 'red';

  return (
    <div className={`border rounded-md p-3 ${selected ? 'border-blue-500 bg-blue-50' : 'border-gray-200'}`}>
      <div className="flex items-center space-x-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggle(result.essay_id)}
          className="w-4 h-4"
        />
        <div className="flex-1">
          <div className="font-medium">{result.filename}</div>
          <div className="text-sm text-gray-600">
            {result.student_name && (
              <span>Name: <strong>{result.student_name}</strong></span>
            )}
            {result.student_email && (
              <span className="ml-4">Email: <strong>{result.student_email}</strong></span>
            )}
          </div>
        </div>
        <div className={`px-2 py-1 rounded text-xs font-medium text-${confidenceColor}-800 bg-${confidenceColor}-100`}>
          {Math.round(result.confidence_score * 100)}% confidence
        </div>
      </div>
    </div>
  );
};

// Enhanced WebSocket integration aligned with thin events
const useStudentParsingUpdates = (batchId: string) => {
  const queryClient = useQueryClient();

  useWebSocketUpdates(batchId, {
    onMessage: (event) => {
      switch (event.event) {
        case 'student.parsing.completed':
          // Handle StudentParsingCompletedV1 event
          queryClient.setQueryData(['batch', batchId, 'parsing-results'], event.parsing_results);
          
          // Show notification
          showNotification({
            type: 'success',
            title: 'Student Parsing Complete',
            message: `Found ${event.parsed_count} of ${event.total_count} student names`,
          });
          break;
          
        case 'essay.student.association.updated':
          // Handle EssayStudentAssociationUpdatedV1 event
          queryClient.setQueryData(['batch', batchId], (old: BatchStatus) => ({
            ...old,
            essays: old?.essays?.map(essay => 
              essay.essay_id === event.essay_id 
                ? { 
                    ...essay, 
                    associated_student_id: event.student_id,
                    associated_student_name: event.student_name,
                    association_method: event.association_method,
                    confidence_score: event.confidence_score
                  }
                : essay
            ) || [],
          }));
          break;
          
        case 'class.created':
          // Handle ClassCreatedV1 event
          queryClient.invalidateQueries(['user-classes']);
          showNotification({
            type: 'success',
            title: 'Class Created',
            message: `Class "${event.class_designation}" created successfully`,
          });
          break;
          
        case 'student.created':
          // Handle StudentCreatedV1 event
          queryClient.invalidateQueries(['user-students']);
          showNotification({
            type: 'success',
            title: 'Student Added',
            message: `Student "${event.student_name}" added successfully`,
          });
          break;
      }
    }
  });
};
```

### **Phase 3: Enhanced Results & Analytics**

#### **Task 3.1: Student-Centric Results Views**

**Objective**: Provide results organized by student and class for better insights.

**Frontend Implementation**:

```typescript
// Student progress dashboard
const StudentProgressDashboard = ({ classId }: { classId: string }) => {
  const { data: classData } = useQuery({
    queryKey: ['class', classId],
    queryFn: () => apiClient.getClassDetails(classId),
  });

  const { data: studentResults } = useQuery({
    queryKey: ['class', classId, 'student-results'],
    queryFn: () => apiClient.getClassStudentResults(classId),
  });

  return (
    <div className="space-y-6">
      <div className="bg-white border rounded-lg p-6">
        <h2 className="text-xl font-semibold">{classData?.class_designation}</h2>
        <p className="text-gray-600">
          {classData?.courses?.map(c => c.name).join(', ')} • 
          {studentResults?.length || 0} students
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {studentResults?.map(student => (
          <StudentResultCard 
            key={student.student_id}
            student={student}
            onViewDetails={() => navigateToStudentDetails(student.student_id)}
          />
        ))}
      </div>
    </div>
  );
};

const StudentResultCard = ({ 
  student, 
  onViewDetails 
}: {
  student: StudentResult;
  onViewDetails: () => void;
}) => {
  const completedEssays = student.essays.filter(e => e.status === 'COMPLETED').length;
  const totalEssays = student.essays.length;

  return (
    <div className="bg-white border rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">{student.name}</h3>
        <span className="text-sm text-gray-500">{student.email}</span>
      </div>

      <div className="space-y-2 mb-4">
        <div className="flex justify-between text-sm">
          <span>Essays Completed:</span>
          <span className="font-medium">{completedEssays}/{totalEssays}</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div 
            className="bg-blue-500 h-2 rounded-full transition-all"
            style={{ width: `${(completedEssays / totalEssays) * 100}%` }}
          />
        </div>
      </div>

      <button
        onClick={onViewDetails}
        className="w-full px-3 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm"
      >
        View Details
      </button>
    </div>
  );
};
```

### **Implementation Timeline & Dependencies**

**Phase 1 (Immediate - with User ID Propagation):**

* ✅ Enhanced batch registration with course validation
* ✅ File management with batch state validation  
* ✅ Real-time file operation updates

**Phase 2 (Post API Gateway completion):**

* ✅ Class Management Service implementation
* ✅ Student parsing integration
* ✅ Student-essay association UI

**Phase 3 (Enhanced analytics):**

* ✅ Student-centric results views
* ✅ Class progress dashboards
* ✅ Multi-batch student tracking

**Key Benefits:**

1. **Seamless User Experience**: Teachers can manage files, classes, and students in one interface
2. **Intelligent Automation**: Automatic student parsing with manual override capabilities
3. **Real-time Feedback**: WebSocket updates for all file and class management operations
4. **Flexible Associations**: Support for complex class/student relationships
5. **Comprehensive Analytics**: Student progress tracking across multiple batches and courses

This enhanced implementation provides a complete educational management platform while maintaining the architectural integrity and event-driven patterns of the HuleEdu system.
