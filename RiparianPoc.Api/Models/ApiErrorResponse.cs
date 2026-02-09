namespace RiparianPoc.Api.Models;

/// <summary>
/// Structured error response returned by the API when an unhandled exception occurs.
/// </summary>
/// <param name="Error">Human-readable error description.</param>
/// <param name="CorrelationId">The trace/correlation ID for this request.</param>
/// <param name="StatusCode">HTTP status code returned.</param>
/// <param name="Detail">
/// Additional detail (exception message). Only populated in Development environment.
/// </param>
public sealed record ApiErrorResponse(
    string Error,
    string CorrelationId,
    int StatusCode,
    string? Detail = null);
