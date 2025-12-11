export class ApiError extends Error {
  constructor(
    public statusCode: number,
    public errorCode: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  static fromResponse(response: Response, body?: string): ApiError {
    return new ApiError(
      response.status,
      `HTTP_${response.status}`,
      body ?? response.statusText,
    );
  }
}
