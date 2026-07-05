using NetTopologySuite.Features;

namespace RiparianPoc.Api.Repositories;

/// <summary>
/// Abstracts PostGIS data access via Dapper, providing GeoJSON-aware query execution.
/// </summary>
public interface IPostGisRepository
{
    /// <summary>
    /// Executes a spatial SQL query and builds a GeoJSON FeatureCollection.
    /// The query must include a <c>geojson</c> column (via ST_AsGeoJSON);
    /// all other columns become feature properties.
    /// </summary>
    Task<FeatureCollection> QueryGeoJsonAsync(string sql, object? parameters, CancellationToken ct);

    /// <summary>
    /// Executes a raw SQL query that returns a PostGIS MVT (Mapbox Vector Tile)
    /// binary blob. Uses ST_AsMVT aggregation.
    /// </summary>
    Task<byte[]> QueryMvtAsync(string sql, object? parameters, CancellationToken ct);

    /// <summary>
    /// Executes a SQL query and maps results to a list of <typeparamref name="T"/>.
    /// </summary>
    Task<IReadOnlyList<T>> QueryAsync<T>(string sql, object? parameters, CancellationToken ct);
}
