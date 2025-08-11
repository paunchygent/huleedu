# Frontend File Upload Integration Guide

Production-ready file upload patterns for HuleEdu batch processing with progress tracking, validation, and retry logic.

## Overview

The HuleEdu File Upload API (port 4001) handles batch file uploads with comprehensive validation, progress tracking, and error handling. This guide covers production-grade upload patterns and UI integration.

## Core Interfaces

```typescript
interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
  speed?: number; // bytes per second
  remainingTime?: number; // seconds
}

interface FileValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}

interface UploadOptions {
  maxRetries?: number;
  chunkSize?: number;
  timeout?: number;
  validateBeforeUpload?: boolean;
}

interface FileUploadResponse {
  batch_id: string;
  uploaded_files: Array<{
    filename: string;
    size: number;
    content_type: string;
    storage_path: string;
  }>;
  validation_results: FileValidationResult;
}
```

## File Upload Manager

Production file upload implementation with retry logic and progress tracking.

```typescript
class FileUploadManager {
  private readonly maxFileSize = 10 * 1024 * 1024; // 10MB
  private readonly allowedTypes = [
    'text/plain',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword'
  ];
  private readonly allowedExtensions = ['.txt', '.pdf', '.docx', '.doc'];
  private readonly maxFiles = 50;

  async uploadFiles(
    files: File[],
    batchId: string,
    onProgress?: (progress: UploadProgress) => void,
    options: UploadOptions = {}
  ): Promise<ApiResponse<FileUploadResponse>> {
    
    const {
      maxRetries = 3,
      timeout = 300000, // 5 minutes
      validateBeforeUpload = true
    } = options;

    // Pre-upload validation
    if (validateBeforeUpload) {
      const validation = this.validateFiles(files);
      if (!validation.isValid) {
        throw new Error(`File validation failed: ${validation.errors.join(', ')}`);
      }
    }

    let attempt = 0;
    let lastError: Error;

    while (attempt <= maxRetries) {
      try {
        return await this.performUpload(files, batchId, onProgress, timeout);
      } catch (error) {
        lastError = error as Error;
        attempt++;
        
        if (attempt <= maxRetries) {
          // Exponential backoff with jitter
          const baseDelay = 1000 * Math.pow(2, attempt - 1);
          const jitter = Math.random() * 1000;
          const delay = Math.min(baseDelay + jitter, 10000);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }

    throw lastError!;
  }

  private async performUpload(
    files: File[],
    batchId: string,
    onProgress?: (progress: UploadProgress) => void,
    timeout: number = 300000
  ): Promise<ApiResponse<FileUploadResponse>> {
    
    const formData = new FormData();
    formData.append('batch_id', batchId);
    
    files.forEach(file => {
      formData.append('files', file);
    });

    return new Promise(async (resolve, reject) => {
      const xhr = new XMLHttpRequest();
      let startTime = Date.now();
      let lastLoaded = 0;
      let lastTime = startTime;

      xhr.timeout = timeout;

      // Progress tracking with speed calculation
      if (onProgress) {
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            const now = Date.now();
            const timeDiff = (now - lastTime) / 1000; // seconds
            const loadedDiff = event.loaded - lastLoaded;
            
            const speed = timeDiff > 0 ? loadedDiff / timeDiff : 0;
            const remainingBytes = event.total - event.loaded;
            const remainingTime = speed > 0 ? remainingBytes / speed : 0;

            const progress: UploadProgress = {
              loaded: event.loaded,
              total: event.total,
              percentage: Math.round((event.loaded / event.total) * 100),
              speed,
              remainingTime
            };
            
            onProgress(progress);
            
            lastLoaded = event.loaded;
            lastTime = now;
          }
        });
      }

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText);
            resolve({ data: response, success: true });
          } catch {
            resolve({ data: null, success: true });
          }
        } else {
          let errorDetail = `Upload failed with status ${xhr.status}`;
          try {
            const errorResponse = JSON.parse(xhr.responseText);
            errorDetail = errorResponse.detail || errorDetail;
          } catch {
            // Use default error message
          }
          
          const error = {
            detail: errorDetail,
            status_code: xhr.status
          };
          resolve({ error, success: false });
        }
      });

      xhr.addEventListener('error', () => {
        reject(new Error('Upload failed due to network error'));
      });

      xhr.addEventListener('timeout', () => {
        reject(new Error('Upload timed out'));
      });

      xhr.addEventListener('abort', () => {
        reject(new Error('Upload was aborted'));
      });

      // Set headers with authentication
      try {
        const headers = await createAuthHeaders();
        Object.entries(headers).forEach(([key, value]) => {
          if (key !== 'Content-Type') { // Let browser set Content-Type for FormData
            xhr.setRequestHeader(key, value);
          }
        });
      } catch (error) {
        reject(error);
        return;
      }

      xhr.open('POST', 'http://localhost:4001/v1/files/batch');
      xhr.send(formData);
    });
  }

  validateFiles(files: File[]): FileValidationResult {
    const errors: string[] = [];
    const warnings: string[] = [];

    if (files.length === 0) {
      errors.push('No files selected');
      return { isValid: false, errors, warnings };
    }

    if (files.length > this.maxFiles) {
      errors.push(`Too many files. Maximum ${this.maxFiles} files allowed per batch`);
    }

    files.forEach((file, index) => {
      const fileNumber = index + 1;
      
      // Size validation
      if (file.size === 0) {
        errors.push(`File ${fileNumber} (${file.name}) is empty`);
      } else if (file.size > this.maxFileSize) {
        errors.push(`File ${fileNumber} (${file.name}) exceeds maximum size of ${this.formatFileSize(this.maxFileSize)}`);
      }

      // Type validation
      if (!this.allowedTypes.includes(file.type)) {
        errors.push(`File ${fileNumber} (${file.name}) has unsupported type: ${file.type}`);
      }

      // Extension validation
      const extension = this.getFileExtension(file.name);
      if (!this.allowedExtensions.includes(extension)) {
        errors.push(`File ${fileNumber} (${file.name}) has unsupported extension: ${extension}`);
      }

      // Name validation
      if (file.name.length > 255) {
        errors.push(`File ${fileNumber} name is too long (max 255 characters)`);
      }

      if (!/^[a-zA-Z0-9._-]+$/.test(file.name.replace(/\.[^.]+$/, ''))) {
        warnings.push(`File ${fileNumber} (${file.name}) contains special characters that may cause issues`);
      }
    });

    // Check for duplicates
    const fileNames = files.map(f => f.name);
    const duplicates = fileNames.filter((name, index) => fileNames.indexOf(name) !== index);
    if (duplicates.length > 0) {
      errors.push(`Duplicate file names found: ${[...new Set(duplicates)].join(', ')}`);
    }

    return {
      isValid: errors.length === 0,
      errors,
      warnings
    };
  }

  private getFileExtension(filename: string): string {
    return filename.toLowerCase().substring(filename.lastIndexOf('.'));
  }

  private formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  formatSpeed(bytesPerSecond: number): string {
    return this.formatFileSize(bytesPerSecond) + '/s';
  }

  formatTime(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`;
    return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
  }

  async generatePreview(file: File): Promise<string | null> {
    if (file.type.startsWith('image/')) {
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target?.result as string);
        reader.onerror = () => resolve(null);
        reader.readAsDataURL(file);
      });
    }

    if (file.type === 'text/plain' && file.size < 1024 * 1024) { // 1MB limit for text preview
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = (e) => {
          const text = e.target?.result as string;
          resolve(text.substring(0, 500) + (text.length > 500 ? '...' : ''));
        };
        reader.onerror = () => resolve(null);
        reader.readAsText(file);
      });
    }

    return null;
  }
}
```
