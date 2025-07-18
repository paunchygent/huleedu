# HuleEdu Frontend MVP: Product Requirements and Implementation Plan

---
**ID**: `FE-MVP-001`  
**Status**: `Ready for Development`  
**Author**: `CTO`  
**Created**: `2025-07-18`  
**Updated**: `2025-07-18`  
---

## 1. Overview

This document provides the Product Requirements (PRD) and a phased technical implementation plan for the HuleEdu Frontend MVP. It translates the user journey into a concrete architectural and feature roadmap, designed to integrate seamlessly with the HuleEdu microservices ecosystem.

### 1.1. Critical Prerequisite

- **Backend Services**: This plan assumes all backend services, including the `api_gateway_service` and the newly independent `websocket_service`, are implemented and operational.

## 2. Part 1: Product Requirements (The "Why")

### 2.1. User Journey

1.  **Authentication**: A teacher registers for an account, confirms their email, and logs in using either a password or a magic link.
2.  **Dashboard & Upload**: The teacher lands on a dashboard showing past essay batches. They initiate a new batch upload, providing metadata (class, course, instructions) and uploading essay files via drag-and-drop.
3.  **Processing**: The teacher monitors the batch processing in real-time. The system provides live updates on the status of each essay.
4.  **Retry & Correction**: If a processing step fails for a retryable reason, the teacher can initiate a retry for specific essays. They can also correct student-essay associations.
5.  **Results**: The teacher views the results, including AI-generated feedback and NLP statistics.
6.  **Management**: The teacher manages their classes, students, and account settings.

### 2.2. Core Features

- **Secure Authentication**: JWT-based login with email confirmation.
- **Batch Management**: Create, view, and manage essay batches.
- **File Handling**: Drag-and-drop file uploads with pre-submission validation.
- **Real-Time Updates**: WebSocket-driven dashboard for live processing status.
- **Client-Initiated Retries**: A cost-aware, user-friendly retry mechanism for failed processing steps.
- **Class & Student Management**: UI for managing classes and student rosters.
- **Results Visualization**: Clear presentation of AI feedback and analytics.

## 3. Part 2: Technical Implementation Plan (The "How")

### Phase 1: Foundation & Project Setup

**Objective**: Establish a modern, scalable, and maintainable Vite + React + TypeScript project within the monorepo.

**Task 1.1: Scaffold Project**
- Create a `frontend` directory in the monorepo root.
- Use `pnpm create vite . --template react-ts` to initialize the project.
- Configure `pnpm-workspace.yaml` in the root to include the `frontend` package.

**Task 1.2: Install Core Dependencies**
- **Routing**: `react-router-dom`
- **State Management**: `@tanstack/react-query` (server state), `zustand` (client state)
- **API Client**: `axios`
- **Styling**: `tailwindcss`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`
- **File Handling**: `react-dropzone`
- **Authentication**: `js-cookie`
- **Error Handling**: `react-error-boundary`

**Task 1.3: Configure Tooling**
- Initialize Tailwind CSS and configure `tailwind.config.js` and `postcss.config.js`.
- Create a `.env.local` file with the following variables:
  ```
  VITE_API_BASE_URL=http://localhost:4001
  VITE_WEBSOCKET_URL=ws://localhost:4002/ws
  ```

**Definition of Done:**
- ✅ A functional Vite + React + TS project exists in the `frontend` directory.
- ✅ All dependencies are installed and configured.
- ✅ The Vite development server runs successfully.
- ✅ The API Gateway and WebSocket service URLs are correctly configured.

### Phase 2: Authentication & Layout

**Objective**: Implement the application's authentication flow and the main authenticated layout.

**Task 2.1: Create Typed API Client**
- Create an `apiClient` using `axios`.
- Implement an interceptor to automatically attach the JWT from `js-cookie` to all outgoing requests.
- Implement an interceptor to handle 401 Unauthorized responses by logging the user out.

**Task 2.2: Implement Authentication State**
- Create a `useAuthStore` with `zustand` to manage the user's authentication state, user object, and JWT.
- The store must handle login, logout, and initialization from the cookie.

**Task 2.3: Build Authentication Pages and Layouts**
- Create `LoginPage.tsx` and `RegisterPage.tsx`.
- Create an `AuthLayout.tsx` for public-facing forms.
- Create a `DashboardLayout.tsx` for the main authenticated application shell, including a sidebar and header.
- Implement a `ProtectedRoute.tsx` component that redirects unauthenticated users to `/login`.

**Definition of Done:**
- ✅ Users can register, log in, and log out.
- ✅ JWTs are securely stored in cookies and managed by the `useAuthStore`.
- ✅ Protected routes are inaccessible to unauthenticated users.
- ✅ The main application layout is in place.

### Phase 3: Core Feature Implementation

**Objective**: Implement the core user journey, from file upload to real-time processing.

**Task 3.1: Implement Teacher Dashboard and File Upload**
- Create a `TeacherDashboardPage.tsx` that displays a list of previous batches and a CTA to upload a new one.
- Create a `FileUploadPage.tsx` with:
  - A metadata form for batch details.
  - A `react-dropzone` component for file uploads.
  - Logic to first register the batch with the API Gateway and then upload the files to the returned `batch_id`.

**Task 3.2: Implement Real-Time Processing Dashboard**
- Create a `ProcessingDashboardPage.tsx`.
- **Hydrate Data**: Use `useQuery` to fetch the initial batch status from the API Gateway.
- **Real-Time Updates**: Create a `useWebSocketUpdates` hook that:
  - Connects to the `websocket_service` using the URL from `.env.local`.
  - Passes the JWT as a query parameter (`?token=...`).
  - Listens for incoming messages and updates the React Query cache accordingly.
- **Component Structure**:
  - `FileList.tsx`: Displays the status of each essay in real-time.
  - `PipelinePanel.tsx`: Allows the user to initiate processing pipelines.

**Task 3.3: Implement Client-Initiated Retry**
- Create a `RetryButton.tsx` component that:
  - Only appears for essays with a retryable failure status.
  - Uses `useMutation` to send a retry request to the API Gateway.
  - Displays a cost-aware confirmation modal before retrying.

**Definition of Done:**
- ✅ Teachers can create new essay batches and upload files.
- ✅ The processing dashboard displays real-time status updates via WebSockets.
- ✅ The client-initiated retry mechanism is fully functional.

### Phase 4: Finalization & Type Safety

**Objective**: Ensure end-to-end type safety between the frontend and backend.

**Task 4.1: Automate API Type Generation**
- Add the `openapi-typescript` package.
- Create a `pnpm` script (`generate-types`) to fetch the OpenAPI specification from the `api_gateway_service` and generate a `schema.ts` file.
- This script should be integrated into the CI/CD pipeline.

**Task 4.2: Integrate Generated Types**
- Refactor the `apiClient` and all related components to use the auto-generated types from `schema.ts` for all requests, responses, and data models.

**Task 4.3: Implement Global Error Handling**
- Implement a top-level `ErrorBoundary` component to catch and gracefully handle unexpected application errors.

**Definition of Done:**
- ✅ The `generate-types` script successfully generates a complete and accurate type definition file.
- ✅ The entire application is type-safe, using the generated types for all API interactions.
- ✅ A global error boundary is in place to prevent application crashes.