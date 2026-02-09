using System.Diagnostics;
using NetTopologySuite.Features;
using RiparianPoc.Api.Endpoints;
using RiparianPoc.Api.Repositories;

namespace RiparianPoc.Api.Services;

/// <summary>
/// Provides spatial GeoJSON queries by delegating to <see cref="IPostGisRepository"/>.
/// Owns all SQL for spatial map layer endpoints.
/// </summary>
public sealed class SpatialQueryService : ISpatialQueryService
{
    private const string FeatureCountTag = "result.feature_count";
    private static readonly ActivitySource Source = new("RiparianPoc.Api.SpatialQuery");

    private readonly IPostGisRepository _repository;
    private readonly ILogger<SpatialQueryService> _logger;

    public SpatialQueryService(
        IPostGisRepository repository, ILogger<SpatialQueryService> logger)
    {
        _repository = repository ?? throw new ArgumentNullException(nameof(repository));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    /// <inheritdoc />
    public async Task<FeatureCollection> GetStreamsAsync(CancellationToken ct)
    {
        using var activity = Source.StartActivity("SpatialQuery.GetStreams");

        _logger.LogInformation("Fetching stream centerlines from bronze schema");

        const string sql = """
            SELECT comid, gnis_name, reach_code, ftype, fcode,
                   stream_order, length_km,
                   ST_AsGeoJSON(geom) AS geojson
            FROM bronze.streams
            """;

        var fc = await _repository.QueryGeoJsonAsync(sql, null, ct);

        activity?.SetTag(FeatureCountTag, fc.Count);
        _logger.LogInformation("Stream centerlines fetched: {FeatureCount} features", fc.Count);

        return fc;
    }

    /// <inheritdoc />
    public async Task<FeatureCollection> GetBuffersAsync(CancellationToken ct)
    {
        using var activity = Source.StartActivity("SpatialQuery.GetBuffers");

        _logger.LogInformation("Fetching riparian buffers from silver schema");

        const string sql = """
            SELECT rb.id, rb.stream_id, rb.buffer_distance_m, rb.area_sq_m,
                   s.gnis_name AS stream_name,
                   ST_AsGeoJSON(rb.geom) AS geojson
            FROM silver.riparian_buffers rb
            JOIN bronze.streams s ON s.id = rb.stream_id
            """;

        var fc = await _repository.QueryGeoJsonAsync(sql, null, ct);

        activity?.SetTag(FeatureCountTag, fc.Count);
        _logger.LogInformation("Riparian buffers fetched: {FeatureCount} features", fc.Count);

        return fc;
    }

    /// <inheritdoc />
    public async Task<FeatureCollection> GetParcelsAsync(CancellationToken ct)
    {
        using var activity = Source.StartActivity("SpatialQuery.GetParcels");

        _logger.LogInformation("Fetching parcels with compliance status");

        const string sql = """
            SELECT p.id, p.parcel_id, p.land_use_desc, p.land_use_code,
                   p.zoning_desc, p.owner_name, p.land_acres,
                   pc.is_focus_area, pc.overlap_pct, pc.focus_area_reason,
                   ST_AsGeoJSON(p.geom) AS geojson
            FROM bronze.parcels p
            LEFT JOIN silver.parcel_compliance pc ON pc.parcel_id = p.id
            """;

        var fc = await _repository.QueryGeoJsonAsync(sql, null, ct);

        activity?.SetTag(FeatureCountTag, fc.Count);
        _logger.LogInformation("Parcels fetched: {FeatureCount} features", fc.Count);

        return fc;
    }

    /// <inheritdoc />
    public async Task<FeatureCollection> GetFocusAreasAsync(CancellationToken ct)
    {
        using var activity = Source.StartActivity("SpatialQuery.GetFocusAreas");

        _logger.LogInformation("Fetching focus-area parcels");

        const string sql = """
            SELECT p.id, p.parcel_id, p.land_use_desc, p.land_use_code,
                   p.zoning_desc, p.owner_name, p.land_acres,
                   pc.overlap_pct, pc.overlap_area_sq_m, pc.focus_area_reason,
                   ST_AsGeoJSON(p.geom) AS geojson
            FROM bronze.parcels p
            INNER JOIN silver.parcel_compliance pc ON pc.parcel_id = p.id
            WHERE pc.is_focus_area = TRUE
            """;

        var fc = await _repository.QueryGeoJsonAsync(sql, null, ct);

        activity?.SetTag(FeatureCountTag, fc.Count);
        _logger.LogInformation("Focus-area parcels fetched: {FeatureCount} features", fc.Count);

        return fc;
    }
}

/// <summary>
/// Provides non-spatial compliance data queries by delegating to <see cref="IPostGisRepository"/>.
/// Owns all SQL for vegetation health and compliance summary endpoints.
/// </summary>
public sealed class ComplianceDataService : IComplianceDataService
{
    private static readonly ActivitySource Source = new("RiparianPoc.Api.ComplianceData");

    private readonly IPostGisRepository _repository;
    private readonly ILogger<ComplianceDataService> _logger;

    public ComplianceDataService(
        IPostGisRepository repository, ILogger<ComplianceDataService> logger)
    {
        _repository = repository ?? throw new ArgumentNullException(nameof(repository));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<VegetationReading>> GetVegetationByBufferAsync(
        int bufferId, CancellationToken ct)
    {
        using var activity = Source.StartActivity("ComplianceData.GetVegetationByBuffer");
        activity?.SetTag("buffer.id", bufferId);

        if (bufferId <= 0)
        {
            throw new ArgumentException(
                $"Buffer ID must be positive, got {bufferId}", nameof(bufferId));
        }

        _logger.LogInformation("Fetching vegetation readings for buffer {BufferId}", bufferId);

        const string sql = """
            SELECT id, buffer_id, acquisition_date, mean_ndvi, min_ndvi, max_ndvi,
                   health_category, season_context, satellite, processed_at
            FROM silver.vegetation_health
            WHERE buffer_id = @bufferId
            ORDER BY acquisition_date
            """;

        var readings = await _repository.QueryAsync<VegetationReading>(sql, new { bufferId }, ct);

        _logger.LogInformation(
            "Vegetation readings fetched for buffer {BufferId}: {Count} readings",
            bufferId, readings.Count);

        return readings;
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<ComplianceSummary>> GetSummaryAsync(CancellationToken ct)
    {
        using var activity = Source.StartActivity("ComplianceData.GetSummary");

        _logger.LogInformation("Fetching compliance summary from gold schema");

        const string sql = """
            SELECT id, watershed_id, huc8, total_stream_length_m, total_buffer_area_sq_m,
                   total_parcels, compliant_parcels, focus_area_parcels, compliance_pct,
                   avg_ndvi, healthy_buffer_pct, degraded_buffer_pct, bare_buffer_pct,
                   created_at
            FROM gold.riparian_summary
            """;

        var summaries = await _repository.QueryAsync<ComplianceSummary>(sql, null, ct);

        _logger.LogInformation("Compliance summary fetched: {Count} watersheds", summaries.Count);

        return summaries;
    }
}
