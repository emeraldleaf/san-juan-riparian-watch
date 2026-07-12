using System.Diagnostics;
using System.Text.RegularExpressions;

namespace RiparianPoc.Api.Middleware;

/// <summary>
/// Extracts or generates correlation and session identifiers from request headers,
/// enriches the current <see cref="Activity"/> with tags, and establishes a logging
/// scope so all downstream log entries include these identifiers.
/// </summary>
public sealed partial class CorrelationMiddleware
{
    private const string CorrelationIdHeader = "X-Correlation-Id";
    private const string SessionIdHeader = "X-Session-Id";

    /// <summary>Maximum accepted identifier length. A correlation ID is a GUID, not an essay.</summary>
    private const int MaxIdLength = 64;

    /// <summary>
    /// The only characters an identifier may contain. Anything else — above all CR and LF — is
    /// rejected.
    /// </summary>
    [GeneratedRegex(@"\A[A-Za-z0-9._-]{1,64}\z")]
    private static partial Regex SafeId();

    /// <summary>
    /// Sanitise a client-supplied identifier before it reaches a log or a response header.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <c>X-Correlation-Id</c> and <c>X-Session-Id</c> arrive from the client. Writing them to the
    /// log unvalidated is <b>log forging</b> (CodeQL <c>cs/log-forging</c>): a CR/LF in the header
    /// lets an attacker inject whole fabricated log lines — which is how you hide an intrusion from
    /// the audit trail that is supposed to reveal it. The correlation ID is <i>also</i> echoed back
    /// into a response header, so the same value is a response-splitting vector.
    /// </para>
    /// <para>
    /// So the identifier is accepted only if it is a short, plain token. Anything else is
    /// <b>replaced</b>, not escaped — a request that supplies a hostile correlation ID has no
    /// legitimate claim to have it preserved, and a fresh GUID keeps the trace usable.
    /// </para>
    /// </remarks>
    private static string SanitizeId(string? value, string fallback) =>
        !string.IsNullOrEmpty(value) && value.Length <= MaxIdLength && SafeId().IsMatch(value)
            ? value
            : fallback;

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
        // Both identifiers are CLIENT-SUPPLIED and end up in the logs — and the correlation ID is
        // echoed back in a response header. Unsanitised, a CR/LF in either forges log entries
        // (CodeQL cs/log-forging) and splits the response. Sanitise at the boundary, once.
        var correlationId = SanitizeId(
            context.Request.Headers[CorrelationIdHeader].FirstOrDefault(),
            Activity.Current?.TraceId.ToString() ?? Guid.NewGuid().ToString("N"));

        var sessionId = SanitizeId(
            context.Request.Headers[SessionIdHeader].FirstOrDefault(), "unknown");

        // Not client-supplied — this is the socket's remote address, not a header.
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
