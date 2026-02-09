using System.Diagnostics;

namespace RiparianPoc.Api.Middleware;

/// <summary>
/// Extracts or generates correlation and session identifiers from request headers,
/// enriches the current <see cref="Activity"/> with tags, and establishes a logging
/// scope so all downstream log entries include these identifiers.
/// </summary>
public sealed class CorrelationMiddleware
{
    private const string CorrelationIdHeader = "X-Correlation-Id";
    private const string SessionIdHeader = "X-Session-Id";

    private readonly RequestDelegate _next;
    private readonly ILogger<CorrelationMiddleware> _logger;

    public CorrelationMiddleware(RequestDelegate next, ILogger<CorrelationMiddleware> logger)
    {
        _next = next ?? throw new ArgumentNullException(nameof(next));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    /// <summary>
    /// Extracts correlation/session IDs, enriches Activity and logging scope,
    /// then passes control to the next middleware.
    /// </summary>
    public async Task InvokeAsync(HttpContext context)
    {
        var correlationId = context.Request.Headers[CorrelationIdHeader].FirstOrDefault()
                            ?? Activity.Current?.TraceId.ToString()
                            ?? Guid.NewGuid().ToString("N");

        var sessionId = context.Request.Headers[SessionIdHeader].FirstOrDefault() ?? "unknown";
        var clientIp = context.Connection.RemoteIpAddress?.ToString() ?? "unknown";

        var activity = Activity.Current;
        activity?.SetTag("correlation.id", correlationId);
        activity?.SetTag("session.id", sessionId);
        activity?.SetTag("client.ip", clientIp);

        context.Response.OnStarting(() =>
        {
            context.Response.Headers[CorrelationIdHeader] = correlationId;
            return Task.CompletedTask;
        });

        using (_logger.BeginScope(new Dictionary<string, object>
        {
            ["CorrelationId"] = correlationId,
            ["SessionId"] = sessionId,
            ["ClientIp"] = clientIp,
        }))
        {
            _logger.LogDebug(
                "Request started: {Method} {Path}",
                context.Request.Method,
                context.Request.Path);

            await _next(context);
        }
    }
}
