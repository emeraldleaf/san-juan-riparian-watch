using System.Diagnostics;
using Npgsql;
using RiparianPoc.Api.Models;

namespace RiparianPoc.Api.Middleware;

/// <summary>
/// Global exception handling middleware that catches unhandled exceptions,
/// logs them with structured context, and returns a consistent
/// <see cref="ApiErrorResponse"/> JSON body.
/// </summary>
public sealed class ExceptionHandlingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<ExceptionHandlingMiddleware> _logger;
    private readonly IHostEnvironment _environment;

    public ExceptionHandlingMiddleware(
        RequestDelegate next,
        ILogger<ExceptionHandlingMiddleware> logger,
        IHostEnvironment environment)
    {
        _next = next ?? throw new ArgumentNullException(nameof(next));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _environment = environment ?? throw new ArgumentNullException(nameof(environment));
    }

    /// <summary>
    /// Invokes the next middleware, catching any unhandled exceptions.
    /// Client-disconnected cancellations are not caught.
    /// </summary>
    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await _next(context);
        }
        catch (OperationCanceledException ex) when (context.RequestAborted.IsCancellationRequested)
        {
            // Client disconnected — nothing to send back
            _logger.LogDebug(ex, "Request cancelled by client: {Method} {Path}",
                context.Request.Method, context.Request.Path);
        }
        catch (Exception ex)
        {
            await HandleExceptionAsync(context, ex);
        }
    }

    private async Task HandleExceptionAsync(HttpContext context, Exception exception)
    {
        // For 4xx client errors, expose the exception message (it's meant to be user-facing).
        // For 5xx server errors, use a generic message to avoid leaking internals.
        // Check InnerException for NpgsqlException (wrapped by repository layer).
        var (statusCode, message) = exception switch
        {
            NpgsqlException => (StatusCodes.Status503ServiceUnavailable,
                                "Database temporarily unavailable"),
            _ when exception.InnerException is NpgsqlException
                => (StatusCodes.Status503ServiceUnavailable,
                    "Database temporarily unavailable"),
            ArgumentException ex => (StatusCodes.Status400BadRequest,
                                     ex.Message),
            KeyNotFoundException ex => (StatusCodes.Status404NotFound,
                                        ex.Message),
            OperationCanceledException => (StatusCodes.Status504GatewayTimeout,
                                           "Request timed out"),
            _ => (StatusCodes.Status500InternalServerError,
                  "An unexpected error occurred"),
        };

        var correlationId = Activity.Current?.TraceId.ToString()
                            ?? context.Response.Headers["X-Correlation-Id"].FirstOrDefault()
                            ?? "unknown";

        if (statusCode >= 500)
        {
            _logger.LogError(exception,
                "Unhandled exception: {ErrorMessage} | StatusCode={StatusCode}",
                exception.Message, statusCode);
        }
        else
        {
            _logger.LogWarning(exception,
                "Request error: {ErrorMessage} | StatusCode={StatusCode}",
                exception.Message, statusCode);
        }

        Activity.Current?.SetTag("error", true);
        Activity.Current?.SetTag("error.type", exception.GetType().Name);
        Activity.Current?.SetStatus(ActivityStatusCode.Error, exception.Message);

        var detail = _environment.IsDevelopment() ? exception.ToString() : null;
        var errorResponse = new ApiErrorResponse(message, correlationId, statusCode, detail);

        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/json";
        await context.Response.WriteAsJsonAsync(errorResponse);
    }
}
