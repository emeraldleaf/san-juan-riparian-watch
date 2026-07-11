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
    public async Task<FeatureCollection> GetRiparianExtentAsync(
        string? method, CancellationToken ct)
    {
        using var activity = Source.StartActivity("SpatialQuery.GetRiparianExtent");
        activity?.SetTag("filter.method", method ?? "all");

        _logger.LogInformation(
            "Fetching riparian extent from silver schema (method: {Method})",
            method ?? "all");

        const string sql = """
            SELECT id, method, model_version, is_riparian,
                   riparian_probability, cell_size_m,
                   ST_AsGeoJSON(geom) AS geojson
            FROM silver.riparian_extent
            WHERE (@method IS NULL OR method = @method)
            """;

        var fc = await _repository.QueryGeoJsonAsync(sql, new { method }, ct);

        activity?.SetTag(FeatureCountTag, fc.Count);
        _logger.LogInformation("Riparian extent fetched: {FeatureCount} features", fc.Count);

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
    /// <inheritdoc />
    public async Task<FeatureCollection> GetBuffersWithHealthAsync(CancellationToken ct)
    {
        using var activity = Source.StartActivity("SpatialQuery.GetBuffersWithHealth");

        _logger.LogInformation("Fetching riparian buffers with NDVI health data");

        const string sql = """
            SELECT rb.id, rb.stream_id, rb.buffer_distance_m, rb.area_sq_m,
                   s.gnis_name AS stream_name,
                   vh.mean_ndvi, vh.health_category, vh.acquisition_date,
                   ST_AsGeoJSON(rb.geom) AS geojson
            FROM silver.riparian_buffers rb
            JOIN bronze.streams s ON s.id = rb.stream_id
            LEFT JOIN LATERAL (
                SELECT mean_ndvi, health_category, acquisition_date
                FROM silver.vegetation_health
                WHERE buffer_id = rb.id AND season_context = 'peak_growing'
                ORDER BY acquisition_date DESC
                LIMIT 1
            ) vh ON TRUE
            """;

        var fc = await _repository.QueryGeoJsonAsync(sql, null, ct);

        activity?.SetTag(FeatureCountTag, fc.Count);
        _logger.LogInformation("Buffers with health fetched: {FeatureCount} features", fc.Count);

        return fc;
    }

    /// <inheritdoc />
    public async Task<FeatureCollection> GetBuffersWithHealthByDateAsync(
        DateOnly date, CancellationToken ct)
    {
        using var activity = Source.StartActivity("SpatialQuery.GetBuffersWithHealthByDate");
        activity?.SetTag("filter.date", date.ToString("yyyy-MM-dd"));

        _logger.LogInformation("Fetching buffers with NDVI health for date {Date}", date);

        const string sql = """
            SELECT rb.id, rb.stream_id, rb.buffer_distance_m, rb.area_sq_m,
                   s.gnis_name AS stream_name,
                   vh.mean_ndvi, vh.health_category, vh.acquisition_date,
                   ST_AsGeoJSON(rb.geom) AS geojson
            FROM silver.riparian_buffers rb
            JOIN bronze.streams s ON s.id = rb.stream_id
            LEFT JOIN silver.vegetation_health vh
                ON vh.buffer_id = rb.id
                AND vh.season_context = 'peak_growing'
                AND vh.acquisition_date = @date
            """;

        var fc = await _repository.QueryGeoJsonAsync(sql, new { date }, ct);

        activity?.SetTag(FeatureCountTag, fc.Count);
        _logger.LogInformation(
            "Buffers with health for {Date}: {FeatureCount} features", date, fc.Count);

        return fc;
    }

    /// <inheritdoc />
    public async Task<FeatureCollection> GetWetlandsAsync(CancellationToken ct)
    {
        using var activity = Source.StartActivity("SpatialQuery.GetWetlands");

        _logger.LogInformation("Fetching NWI wetland polygons from bronze schema");

        const string sql = """
            SELECT id, wetland_type, cowardin_code, acres,
                   ST_AsGeoJSON(geom) AS geojson
            FROM bronze.nwi_wetlands
            """;

        var fc = await _repository.QueryGeoJsonAsync(sql, null, ct);

        activity?.SetTag(FeatureCountTag, fc.Count);
        _logger.LogInformation("NWI wetlands fetched: {FeatureCount} features", fc.Count);

        return fc;
    }

    /// <inheritdoc />
    public async Task<FeatureCollection> GetBuffersWithScoresAsync(CancellationToken ct)
    {
        using var activity = Source.StartActivity("SpatialQuery.GetBuffersWithScores");

        _logger.LogInformation("Fetching riparian buffers with SMP composite scores");

        const string sql = """
            SELECT rb.id, rb.stream_id, rb.buffer_distance_m, rb.area_sq_m,
                   s.gnis_name AS stream_name,
                   hs.composite_score, hs.score_grade,
                   hs.vegetation_structure_score,
                   hs.connectivity_score,
                   hs.contributing_area_score,
                   ST_AsGeoJSON(rb.geom) AS geojson
            FROM silver.riparian_buffers rb
            JOIN bronze.streams s ON s.id = rb.stream_id
            LEFT JOIN gold.buffer_health_score hs ON hs.buffer_id = rb.id
            """;

        var fc = await _repository.QueryGeoJsonAsync(sql, null, ct);

        activity?.SetTag(FeatureCountTag, fc.Count);
        _logger.LogInformation("Buffers with scores fetched: {FeatureCount} features", fc.Count);

        return fc;
    }

    /// <inheritdoc />
    public async Task<FeatureCollection> GetSoilsAsync(CancellationToken ct)
    {
        using var activity = Source.StartActivity("SpatialQuery.GetSoils");

        _logger.LogInformation("Fetching SSURGO soil polygons from bronze schema");

        const string sql = """
            SELECT id, mukey, musym, muname, hydric_rating, hydric_pct,
                   ST_AsGeoJSON(geom) AS geojson
            FROM bronze.ssurgo_soils
            """;

        var fc = await _repository.QueryGeoJsonAsync(sql, null, ct);

        activity?.SetTag(FeatureCountTag, fc.Count);
        _logger.LogInformation("SSURGO soils fetched: {FeatureCount} features", fc.Count);

        return fc;
    }

    /// <summary>
    /// Shared execution path for every MVT tile endpoint: opens the SpatialQuery span,
    /// tags the tile coordinates, runs the query, and normalizes a null result to an
    /// empty tile. Only the SQL (built by <see cref="MvtTileSql"/>) and parameters vary.
    /// </summary>
    private async Task<byte[]> RenderTileAsync(
        string activityName, int z, int x, int y, string sql, object parameters,
        CancellationToken ct, (string Key, string Value)? extraTag = null)
    {
        using var activity = Source.StartActivity(activityName);
        activity?.SetTag("tile.z", z);
        activity?.SetTag("tile.x", x);
        activity?.SetTag("tile.y", y);
        if (extraTag is { } t)
        {
            activity?.SetTag(t.Key, t.Value);
        }

        var result = await _repository.QueryMvtAsync(sql, parameters, ct);
        activity?.SetTag("result.byte_count", result?.Length ?? 0);
        return result ?? [];
    }

    /// <inheritdoc />
    public Task<byte[]> GetBufferTilesAsync(int z, int x, int y, CancellationToken ct) =>
        RenderTileAsync("SpatialQuery.GetBufferTiles", z, x, y,
            MvtTileSql.Build(
                layer: "buffers",
                geom: "b.geom",
                columns: "b.id, b.buffer_distance_m, COALESCE(h.score_grade, 'Unknown') as grade, h.composite_score",
                from: "silver.riparian_buffers b",
                extraJoins: """
                    LEFT JOIN LATERAL (
                        SELECT score_grade, composite_score
                        FROM gold.buffer_health_score s
                        WHERE s.buffer_id = b.id
                        ORDER BY s.id DESC
                        LIMIT 1
                    ) h ON true
                    """),
            new { z, x, y }, ct);

    /// <inheritdoc />
    public Task<byte[]> GetVegetationTilesAsync(int z, int x, int y, CancellationToken ct) =>
        RenderTileAsync("SpatialQuery.GetVegetationTiles", z, x, y,
            MvtTileSql.Build(
                layer: "vegetation",
                geom: "b.geom",
                columns: "b.id, COALESCE(v.dominant_lifeform, 'Unknown') AS lifeform, COALESCE(v.evt_name, 'Unknown') AS evt_name",
                from: "silver.riparian_buffers b",
                extraJoins: "LEFT JOIN silver.buffer_vegetation_structure v ON b.id = v.buffer_id"),
            new { z, x, y }, ct);

    /// <inheritdoc />
    public Task<byte[]> GetWetlandTilesAsync(int z, int x, int y, CancellationToken ct) =>
        RenderTileAsync("SpatialQuery.GetWetlandTiles", z, x, y,
            MvtTileSql.Build(
                layer: "wetlands",
                geom: "w.geom",
                columns: "w.id, w.wetland_type",
                from: "bronze.nwi_wetlands w"),
            new { z, x, y }, ct);

    /// <inheritdoc />
    public Task<byte[]> GetSoilTilesAsync(int z, int x, int y, CancellationToken ct) =>
        RenderTileAsync("SpatialQuery.GetSoilTiles", z, x, y,
            MvtTileSql.Build(
                layer: "soils",
                geom: "s.geom",
                columns: "s.id, s.musym, s.hydric_rating",
                from: "bronze.ssurgo_soils s"),
            new { z, x, y }, ct);

    /// <inheritdoc />
    public Task<byte[]> GetStreamTilesAsync(int z, int x, int y, CancellationToken ct) =>
        RenderTileAsync("SpatialQuery.GetStreamTiles", z, x, y,
            MvtTileSql.Build(
                layer: "streams",
                geom: "s.geom",
                columns: "s.id, s.comid, s.gnis_name, s.stream_order, s.length_km",
                from: "bronze.streams s"),
            new { z, x, y }, ct);

    /// <inheritdoc />
    public Task<byte[]> GetParcelTilesAsync(int z, int x, int y, CancellationToken ct) =>
        RenderTileAsync("SpatialQuery.GetParcelTiles", z, x, y,
            MvtTileSql.Build(
                layer: "parcels",
                geom: "p.geom",
                columns: "p.id, p.parcel_id, p.land_use_desc, p.owner_name, p.land_acres, COALESCE(pc.is_focus_area, FALSE) AS is_focus_area, pc.overlap_pct, pc.focus_area_reason",
                from: "bronze.parcels p",
                extraJoins: "LEFT JOIN silver.parcel_compliance pc ON pc.parcel_id = p.id"),
            new { z, x, y }, ct);

    /// <inheritdoc />
    public Task<byte[]> GetBufferNdviTilesAsync(int z, int x, int y, CancellationToken ct) =>
        RenderTileAsync("SpatialQuery.GetBufferNdviTiles", z, x, y,
            MvtTileSql.Build(
                layer: "buffers",
                geom: "b.geom",
                columns: "b.id, b.buffer_distance_m, b.area_sq_m, COALESCE(s.gnis_name, 'Unknown') AS stream_name, vh.mean_ndvi, vh.health_category, vh.acquisition_date::text AS acquisition_date",
                from: "silver.riparian_buffers b",
                extraJoins: """
                    JOIN bronze.streams s ON s.id = b.stream_id
                    LEFT JOIN LATERAL (
                        SELECT mean_ndvi, health_category, acquisition_date
                        FROM silver.vegetation_health
                        WHERE buffer_id = b.id AND season_context = 'peak_growing'
                        ORDER BY acquisition_date DESC
                        LIMIT 1
                    ) vh ON TRUE
                    """),
            new { z, x, y }, ct);

    /// <inheritdoc />
    public Task<byte[]> GetBufferNdviTilesByDateAsync(
        int z, int x, int y, DateOnly date, CancellationToken ct)
    {
        var sql = MvtTileSql.Build(
            layer: "buffers",
            geom: "b.geom",
            columns: "b.id, b.buffer_distance_m, b.area_sq_m, COALESCE(s.gnis_name, 'Unknown') AS stream_name, vh.mean_ndvi, vh.health_category, vh.acquisition_date::text AS acquisition_date",
            from: "silver.riparian_buffers b",
            extraJoins: """
                JOIN bronze.streams s ON s.id = b.stream_id
                LEFT JOIN silver.vegetation_health vh
                    ON vh.buffer_id = b.id
                    AND vh.season_context = 'peak_growing'
                    AND vh.acquisition_date = @date
                """);

        return RenderTileAsync("SpatialQuery.GetBufferNdviTilesByDate", z, x, y,
            sql, new { z, x, y, date }, ct,
            extraTag: ("filter.date", date.ToString("yyyy-MM-dd")));
    }

    /// <inheritdoc />
    public Task<byte[]> GetBufferCentroidTilesAsync(int z, int x, int y, CancellationToken ct) =>
        RenderTileAsync("SpatialQuery.GetBufferCentroidTiles", z, x, y,
            MvtTileSql.Build(
                layer: "centroids",
                geom: "b.geom",
                renderGeom: "ST_Centroid(b.geom)",
                columns: "b.id, vh.mean_ndvi",
                from: "silver.riparian_buffers b",
                extraJoins: """
                    LEFT JOIN LATERAL (
                        SELECT mean_ndvi
                        FROM silver.vegetation_health
                        WHERE buffer_id = b.id AND season_context = 'peak_growing'
                        ORDER BY acquisition_date DESC
                        LIMIT 1
                    ) vh ON TRUE
                    """,
                where: "WHERE vh.mean_ndvi IS NOT NULL"),
            new { z, x, y }, ct);

    /// <inheritdoc />
    public async Task<FeatureCollection> GetBufferHealthCentroidsAsync(CancellationToken ct)
    {
        using var activity = Source.StartActivity("SpatialQuery.GetBufferHealthCentroids");

        _logger.LogInformation("Fetching buffer centroids with NDVI for heatmap");

        const string sql = """
            SELECT rb.id,
                   vh.mean_ndvi,
                   ST_AsGeoJSON(ST_Centroid(rb.geom)) AS geojson
            FROM silver.riparian_buffers rb
            LEFT JOIN LATERAL (
                SELECT mean_ndvi
                FROM silver.vegetation_health
                WHERE buffer_id = rb.id AND season_context = 'peak_growing'
                ORDER BY acquisition_date DESC
                LIMIT 1
            ) vh ON TRUE
            WHERE vh.mean_ndvi IS NOT NULL
            """;

        var fc = await _repository.QueryGeoJsonAsync(sql, null, ct);

        activity?.SetTag(FeatureCountTag, fc.Count);
        _logger.LogInformation("Buffer centroids fetched: {FeatureCount} features", fc.Count);

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
    public async Task<IReadOnlyList<DateOnly>> GetNdviDatesAsync(CancellationToken ct)
    {
        using var activity = Source.StartActivity("ComplianceData.GetNdviDates");

        _logger.LogInformation("Fetching distinct NDVI acquisition dates");

        const string sql = """
            SELECT DISTINCT acquisition_date
            FROM silver.vegetation_health
            WHERE season_context = 'peak_growing'
            ORDER BY acquisition_date
            """;

        var rows = await _repository.QueryAsync<NdviDateRow>(sql, null, ct);
        var dates = rows.Select(r => r.AcquisitionDate).ToList();

        activity?.SetTag("result.date_count", dates.Count);
        _logger.LogInformation("NDVI dates fetched: {Count} dates", dates.Count);

        return dates;
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<BufferWetland>> GetBufferWetlandsAsync(
        int bufferId, CancellationToken ct)
    {
        using var activity = Source.StartActivity("ComplianceData.GetBufferWetlands");
        activity?.SetTag("buffer.id", bufferId);

        if (bufferId <= 0)
        {
            throw new ArgumentException(
                $"Buffer ID must be positive, got {bufferId}", nameof(bufferId));
        }

        _logger.LogInformation("Fetching wetland overlaps for buffer {BufferId}", bufferId);

        const string sql = """
            SELECT bw.id, bw.buffer_id, bw.wetland_id,
                   bw.overlap_area_sq_m, bw.wetland_pct_of_buffer,
                   bw.wetland_type, bw.cowardin_code, bw.processed_at
            FROM silver.buffer_wetlands bw
            WHERE bw.buffer_id = @bufferId
            ORDER BY bw.overlap_area_sq_m DESC
            """;

        var results = await _repository.QueryAsync<BufferWetland>(sql, new { bufferId }, ct);

        _logger.LogInformation(
            "Wetland overlaps fetched for buffer {BufferId}: {Count} overlaps",
            bufferId, results.Count);

        return results;
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
                   avg_composite_score, grade_a_pct, grade_b_pct, grade_c_pct,
                   grade_d_pct, grade_f_pct,
                   created_at
            FROM gold.riparian_summary
            """;

        var summaries = await _repository.QueryAsync<ComplianceSummary>(sql, null, ct);

        _logger.LogInformation("Compliance summary fetched: {Count} watersheds", summaries.Count);

        return summaries;
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<BufferLandCover>> GetBufferLandCoverAsync(
        int bufferId, CancellationToken ct)
    {
        using var activity = Source.StartActivity("ComplianceData.GetBufferLandCover");
        activity?.SetTag("buffer.id", bufferId);

        if (bufferId <= 0)
        {
            throw new ArgumentException(
                $"Buffer ID must be positive, got {bufferId}", nameof(bufferId));
        }

        _logger.LogInformation("Fetching land cover for buffer {BufferId}", bufferId);

        const string sql = """
            SELECT lc.id, lc.buffer_id, lc.nlcd_class, lc.nlcd_description,
                   lc.pixel_count, lc.area_pct, lc.is_natural,
                   lc.acquisition_year, lc.processed_at
            FROM silver.buffer_land_cover lc
            WHERE lc.buffer_id = @bufferId
            ORDER BY lc.area_pct DESC
            """;

        var results = await _repository.QueryAsync<BufferLandCover>(sql, new { bufferId }, ct);

        _logger.LogInformation(
            "Land cover fetched for buffer {BufferId}: {Count} classes",
            bufferId, results.Count);

        return results;
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<BufferVegetationStructure>> GetBufferVegetationStructureAsync(
        int bufferId, CancellationToken ct)
    {
        using var activity = Source.StartActivity("ComplianceData.GetBufferVegetationStructure");
        activity?.SetTag("buffer.id", bufferId);

        if (bufferId <= 0)
        {
            throw new ArgumentException(
                $"Buffer ID must be positive, got {bufferId}", nameof(bufferId));
        }

        _logger.LogInformation("Fetching vegetation structure for buffer {BufferId}", bufferId);

        const string sql = """
            SELECT vs.id, vs.buffer_id, vs.evt_code, vs.evt_name,
                   vs.evh_class, vs.mean_height_m, vs.dominant_lifeform,
                   vs.pixel_count, vs.area_pct, vs.processed_at
            FROM silver.buffer_vegetation_structure vs
            WHERE vs.buffer_id = @bufferId
            ORDER BY vs.area_pct DESC
            """;

        var results = await _repository.QueryAsync<BufferVegetationStructure>(
            sql, new { bufferId }, ct);

        _logger.LogInformation(
            "Vegetation structure fetched for buffer {BufferId}: {Count} entries",
            bufferId, results.Count);

        return results;
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<BufferSoil>> GetBufferSoilsAsync(
        int bufferId, CancellationToken ct)
    {
        using var activity = Source.StartActivity("ComplianceData.GetBufferSoils");
        activity?.SetTag("buffer.id", bufferId);

        if (bufferId <= 0)
        {
            throw new ArgumentException(
                $"Buffer ID must be positive, got {bufferId}", nameof(bufferId));
        }

        _logger.LogInformation("Fetching soil overlaps for buffer {BufferId}", bufferId);

        const string sql = """
            SELECT bs.id, bs.buffer_id, bs.soil_id,
                   bs.overlap_area_sq_m, bs.soil_pct_of_buffer,
                   bs.hydric_rating, bs.hydric_pct, bs.muname,
                   bs.processed_at
            FROM silver.buffer_soils bs
            WHERE bs.buffer_id = @bufferId
            ORDER BY bs.overlap_area_sq_m DESC
            """;

        var results = await _repository.QueryAsync<BufferSoil>(sql, new { bufferId }, ct);

        _logger.LogInformation(
            "Soil overlaps fetched for buffer {BufferId}: {Count} overlaps",
            bufferId, results.Count);

        return results;
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<BufferHealthScore>> GetBufferHealthScoreAsync(
        int bufferId, CancellationToken ct)
    {
        using var activity = Source.StartActivity("ComplianceData.GetBufferHealthScore");
        activity?.SetTag("buffer.id", bufferId);

        if (bufferId <= 0)
        {
            throw new ArgumentException(
                $"Buffer ID must be positive, got {bufferId}", nameof(bufferId));
        }

        _logger.LogInformation("Fetching health score for buffer {BufferId}", bufferId);

        const string sql = """
            SELECT id, buffer_id,
                   ndvi_score, vertical_complexity_score, species_composition_score,
                   shrub_layer_score, patchiness_score, native_regeneration_score,
                   native_cover_score,
                   vegetation_structure_score, connectivity_score,
                   contributing_area_score,
                   composite_score, score_grade, scored_at
            FROM gold.buffer_health_score
            WHERE buffer_id = @bufferId
            ORDER BY scored_at DESC
            LIMIT 1
            """;

        var results = await _repository.QueryAsync<BufferHealthScore>(sql, new { bufferId }, ct);

        _logger.LogInformation(
            "Health score fetched for buffer {BufferId}: {Count} records",
            bufferId, results.Count);

        return results;
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<BufferCanopy>> GetBufferCanopyAsync(
        int bufferId, CancellationToken ct)
    {
        using var activity = Source.StartActivity("ComplianceData.GetBufferCanopy");
        activity?.SetTag("buffer.id", bufferId);

        if (bufferId <= 0)
        {
            throw new ArgumentException(
                $"Buffer ID must be positive, got {bufferId}", nameof(bufferId));
        }

        _logger.LogInformation("Fetching canopy data for buffer {BufferId}", bufferId);

        const string sql = """
            SELECT id, buffer_id,
                   mean_height_m, max_height_m, p95_height_m,
                   canopy_cover_pct, height_std_dev, processed_at
            FROM silver.buffer_canopy
            WHERE buffer_id = @bufferId
            ORDER BY processed_at DESC
            LIMIT 1
            """;

        var results = await _repository.QueryAsync<BufferCanopy>(sql, new { bufferId }, ct);

        _logger.LogInformation(
            "Canopy data fetched for buffer {BufferId}: {Count} records",
            bufferId, results.Count);

        return results;
    }

}