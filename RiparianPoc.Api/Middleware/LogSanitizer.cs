namespace RiparianPoc.Api.Middleware;

/// <summary>
/// Strips client-controlled values of anything that could forge a log entry.
/// </summary>
/// <remarks>
/// <para>
/// <b>The request path is user input.</b> ASP.NET Core <i>decodes</i> <c>HttpRequest.Path</c>, so a
/// request to <c>/foo%0AFATAL+intrusion+cleared</c> arrives as <c>"/foo\nFATAL intrusion cleared"</c>
/// — and logging it unaltered writes an attacker-authored line into the audit trail that is supposed
/// to reveal them. CodeQL calls this <c>cs/log-forging</c> (error severity); it flagged both
/// middlewares in this folder.
/// </para>
/// <para>
/// Worth being precise about how this was found, because it is instructive: the first attempt at a
/// fix sanitised the <c>X-Correlation-Id</c> / <c>X-Session-Id</c> headers. That was a real bug
/// (the correlation ID is echoed back into a response header, so it was also a response-splitting
/// vector) — but it was <i>not</i> what the scanner was pointing at, and the alert stayed open. The
/// tainted value was <c>Request.Path</c> all along. A scanner that keeps complaining after you have
/// "fixed" something is usually right.
/// </para>
/// </remarks>
internal static class LogSanitizer
{
    /// <summary>A path or method long enough to be a payload rather than a route.</summary>
    private const int MaxLength = 256;

    /// <summary>
    /// Make a client-supplied value safe to write to a log: no CR, no LF, no other control
    /// characters, bounded length.
    /// </summary>
    /// <param name="value">The untrusted value (a request path, method, or similar).</param>
    /// <returns>
    /// The value with control characters removed and truncated to <see cref="MaxLength"/>.
    /// Never null.
    /// </returns>
    /// <remarks>
    /// Control characters are <b>removed rather than escaped</b>. Escaping preserves an attacker's
    /// payload in a form a downstream log viewer might re-interpret; removal does not. Truncation is
    /// marked with an ellipsis so a clipped path is not mistaken for the real one.
    /// </remarks>
    public static string Clean(string? value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return string.Empty;
        }

        var buffer = new System.Text.StringBuilder(Math.Min(value.Length, MaxLength));
        foreach (var c in value)
        {
            if (buffer.Length >= MaxLength)
            {
                buffer.Append('…');
                break;
            }

            // Drops CR and LF — the log-forging vector — along with every other control character
            // (NUL, ESC, backspace) that a terminal or log viewer might act on.
            if (!char.IsControl(c))
            {
                buffer.Append(c);
            }
        }

        return buffer.ToString();
    }
}
