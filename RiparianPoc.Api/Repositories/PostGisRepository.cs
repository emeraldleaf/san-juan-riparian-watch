using System.Diagnostics;
using System.Text.Json;
using Dapper;
using NetTopologySuite.Features;
using NetTopologySuite.Geometries;
using NetTopologySuite.IO.Converters;
using Npgsql;

namespace RiparianPoc.Api.Repositories;

/// <summary>
/// Dapper-based PostGIS repository that manages NpgsqlConnection lifetime
/// and GeoJSON deserialization.
/// </summary>
public sealed class PostGisRepository : IPostGisRepository
{
    private const string DurationTag = "db.duration_ms";
    private static readonly ActivitySource Source = new("RiparianPoc.Api.Repository");

    private static readonly JsonSerializerOptions GeoJsonOptions = new()
    {
        Converters = { new GeoJsonConverterFactory() }
    };

    private readonly NpgsqlDataSource _db;
    private readonly ILogger<PostGisRepository> _logger;

    public PostGisRepository(NpgsqlDataSource db, ILogger<PostGisRepository> logger)
    {
        _db = db ?? throw new ArgumentNullException(nameof(db));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    /// <inheritdoc />
    public async Task<FeatureCollection> QueryGeoJsonAsync(
        string sql, object? parameters, CancellationToken ct)
    {
        using var activity = Source.StartActivity("PostGis.QueryGeoJson");
        var sw = Stopwatch.StartNew();

        try
        {
            _logger.LogDebug("Executing spatial query");

            await using var conn = await _db.OpenConnectionAsync(ct);
            var rows = await conn.QueryAsync(
                new CommandDefinition(sql, parameters, cancellationToken: ct));

            var fc = new FeatureCollection();
            foreach (var row in rows)
            {
                var dict = (IDictionary<string, object?>)row;
                var geojson = (string)dict["geojson"]!;
                dict.Remove("geojson");
                var geometry = JsonSerializer.Deserialize<Geometry>(geojson, GeoJsonOptions);
                fc.Add(new Feature(geometry, new AttributesTable(
                    dict.ToDictionary(kv => kv.Key, kv => kv.Value))));
            }

            sw.Stop();
            activity?.SetTag("db.feature_count", fc.Count);
            activity?.SetTag(DurationTag, sw.ElapsedMilliseconds);
            _logger.LogDebug(
                "Spatial query returned {FeatureCount} features in {ElapsedMs}ms",
                fc.Count, sw.ElapsedMilliseconds);

            return fc;
        }
        catch (NpgsqlException ex)
        {
            sw.Stop();
            activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
            activity?.SetTag("error", true);
            activity?.SetTag(DurationTag, sw.ElapsedMilliseconds);
            throw new InvalidOperationException(
                $"PostGIS spatial query failed after {sw.ElapsedMilliseconds}ms", ex);
        }
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<T>> QueryAsync<T>(
        string sql, object? parameters, CancellationToken ct)
    {
        using var activity = Source.StartActivity("PostGis.QueryTyped");
        activity?.SetTag("db.result_type", typeof(T).Name);
        var sw = Stopwatch.StartNew();

        try
        {
            _logger.LogDebug("Executing typed query for {Type}", typeof(T).Name);

            await using var conn = await _db.OpenConnectionAsync(ct);
            var results = (await conn.QueryAsync<T>(
                new CommandDefinition(sql, parameters, cancellationToken: ct))).AsList();

            sw.Stop();
            activity?.SetTag("db.row_count", results.Count);
            activity?.SetTag(DurationTag, sw.ElapsedMilliseconds);
            _logger.LogDebug(
                "Typed query returned {Count} rows in {ElapsedMs}ms",
                results.Count, sw.ElapsedMilliseconds);

            return results;
        }
        catch (NpgsqlException ex)
        {
            sw.Stop();
            activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
            activity?.SetTag("error", true);
            activity?.SetTag(DurationTag, sw.ElapsedMilliseconds);
            throw new InvalidOperationException(
                $"Typed query for {typeof(T).Name} failed after {sw.ElapsedMilliseconds}ms", ex);
        }
    }
}
