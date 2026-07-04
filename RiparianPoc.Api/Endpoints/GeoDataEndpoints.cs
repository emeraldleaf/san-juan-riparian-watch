using RiparianPoc.Api.Services;

namespace RiparianPoc.Api.Endpoints;

/// <summary>
/// Maps all geospatial data endpoints for the Riparian Buffer Compliance API.
/// </summary>
public static class GeoDataEndpoints
{
    /// <summary>
    /// Registers all /api/* routes on the endpoint route builder.
    /// </summary>
    public static IEndpointRouteBuilder MapGeoDataEndpoints(this IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api");

        api.MapGet("/streams", GetStreams).WithName("GetStreams");
        api.MapGet("/buffers", GetBuffers).WithName("GetBuffers");
        api.MapGet("/riparian/extent", GetRiparianExtent).WithName("GetRiparianExtent");
        api.MapGet("/buffers/health", GetBuffersWithHealth).WithName("GetBuffersWithHealth");
        api.MapGet("/parcels", GetParcels).WithName("GetParcels");
        api.MapGet("/focus-areas", GetFocusAreas).WithName("GetFocusAreas");
        api.MapGet("/vegetation/buffers/{bufferId:int}", GetVegetationByBuffer)
            .WithName("GetVegetationByBuffer");
        api.MapGet("/summary", GetSummary).WithName("GetSummary");
        api.MapGet("/ndvi/dates", GetNdviDates).WithName("GetNdviDates");
        api.MapGet("/buffers/health/{date}", GetBuffersWithHealthByDate)
            .WithName("GetBuffersWithHealthByDate");
        api.MapGet("/wetlands", GetWetlands).WithName("GetWetlands");
        api.MapGet("/buffers/{bufferId:int}/wetlands", GetBufferWetlands)
            .WithName("GetBufferWetlands");
        api.MapGet("/buffers/{bufferId:int}/landcover", GetBufferLandCover)
            .WithName("GetBufferLandCover");
        api.MapGet("/buffers/{bufferId:int}/vegetation-structure", GetBufferVegetationStructure)
            .WithName("GetBufferVegetationStructure");
        api.MapGet("/soils", GetSoils).WithName("GetSoils");
        api.MapGet("/buffers/{bufferId:int}/soils", GetBufferSoils)
            .WithName("GetBufferSoils");
        api.MapGet("/buffers/scores", GetBuffersWithScores)
            .WithName("GetBuffersWithScores");
        api.MapGet("/buffers/{bufferId:int}/score", GetBufferHealthScore)
            .WithName("GetBufferHealthScore");
        api.MapGet("/buffers/{bufferId:int}/canopy", GetBufferCanopy)
            .WithName("GetBufferCanopy");
        api.MapGet("/tiles/{z}/{x}/{y}.pbf", GetBufferTiles)
            .WithName("GetBufferTiles");
        api.MapGet("/tiles/streams/{z}/{x}/{y}.pbf", GetStreamTiles)
            .WithName("GetStreamTiles");
        api.MapGet("/tiles/parcels/{z}/{x}/{y}.pbf", GetParcelTiles)
            .WithName("GetParcelTiles");
        api.MapGet("/tiles/buffers-ndvi/{z}/{x}/{y}.pbf", GetBufferNdviTiles)
            .WithName("GetBufferNdviTiles");
        api.MapGet("/tiles/buffers-ndvi/{date}/{z}/{x}/{y}.pbf", GetBufferNdviTilesByDate)
            .WithName("GetBufferNdviTilesByDate");
        api.MapGet("/tiles/vegetation/{z}/{x}/{y}.pbf", GetVegetationTiles)
            .WithName("GetVegetationTiles");
        api.MapGet("/tiles/wetlands/{z}/{x}/{y}.pbf", GetWetlandTiles)
            .WithName("GetWetlandTiles");
        api.MapGet("/tiles/soils/{z}/{x}/{y}.pbf", GetSoilTiles)
            .WithName("GetSoilTiles");
        api.MapGet("/tiles/centroids/{z}/{x}/{y}.pbf", GetBufferCentroidTiles)
            .WithName("GetBufferCentroidTiles");
        api.MapGet("/buffers/health/centroids", GetBufferHealthCentroids)
            .WithName("GetBufferHealthCentroids");

        return app;
    }

    /// <summary>
    /// GET /api/streams — stream centerlines from bronze schema (GeoJSON FeatureCollection).
    /// </summary>
    private static async Task<IResult> GetStreams(
        ISpatialQueryService spatialService, CancellationToken ct)
    {
        var fc = await spatialService.GetStreamsAsync(ct);
        return TypedResults.Ok(fc);
    }

    /// <summary>
    /// GET /api/buffers — riparian buffer polygons from silver schema (GeoJSON FeatureCollection).
    /// </summary>
    private static async Task<IResult> GetBuffers(
        ISpatialQueryService spatialService, CancellationToken ct)
    {
        var fc = await spatialService.GetBuffersAsync(ct);
        return TypedResults.Ok(fc);
    }

    /// <summary>
    /// GET /api/riparian/extent — Stage-1 riparian extent polygons from silver schema
    /// (GeoJSON FeatureCollection). Optional <c>?method=rf|olmoearth</c> filter.
    /// </summary>
    private static async Task<IResult> GetRiparianExtent(
        string? method, ISpatialQueryService spatialService, CancellationToken ct)
    {
        var fc = await spatialService.GetRiparianExtentAsync(method, ct);
        return TypedResults.Ok(fc);
    }

    /// <summary>
    /// GET /api/buffers/health — buffer polygons with latest NDVI health (GeoJSON FeatureCollection).
    /// </summary>
    private static async Task<IResult> GetBuffersWithHealth(
        ISpatialQueryService spatialService, CancellationToken ct)
    {
        var fc = await spatialService.GetBuffersWithHealthAsync(ct);
        return TypedResults.Ok(fc);
    }

    /// <summary>
    /// GET /api/parcels — parcels with compliance status (GeoJSON FeatureCollection).
    /// </summary>
    private static async Task<IResult> GetParcels(
        ISpatialQueryService spatialService, CancellationToken ct)
    {
        var fc = await spatialService.GetParcelsAsync(ct);
        return TypedResults.Ok(fc);
    }

    /// <summary>
    /// GET /api/focus-areas — only focus area parcels (GeoJSON FeatureCollection).
    /// </summary>
    private static async Task<IResult> GetFocusAreas(
        ISpatialQueryService spatialService, CancellationToken ct)
    {
        var fc = await spatialService.GetFocusAreasAsync(ct);
        return TypedResults.Ok(fc);
    }

    /// <summary>
    /// GET /api/vegetation/buffers/{bufferId} — NDVI time series for a buffer.
    /// </summary>
    private static async Task<IResult> GetVegetationByBuffer(
        int bufferId, IComplianceDataService complianceService, CancellationToken ct)
    {
        var readings = await complianceService.GetVegetationByBufferAsync(bufferId, ct);
        return TypedResults.Ok(readings);
    }

    /// <summary>
    /// GET /api/summary — gold layer compliance summary.
    /// </summary>
    private static async Task<IResult> GetSummary(
        IComplianceDataService complianceService, CancellationToken ct)
    {
        var summaries = await complianceService.GetSummaryAsync(ct);
        return TypedResults.Ok(summaries);
    }

    /// <summary>
    /// GET /api/ndvi/dates — distinct NDVI acquisition dates.
    /// </summary>
    private static async Task<IResult> GetNdviDates(
        IComplianceDataService complianceService, CancellationToken ct)
    {
        var dates = await complianceService.GetNdviDatesAsync(ct);
        return TypedResults.Ok(dates);
    }

    /// <summary>
    /// GET /api/buffers/health/{date} — buffer health for a specific acquisition date.
    /// </summary>
    private static async Task<IResult> GetBuffersWithHealthByDate(
        DateOnly date, ISpatialQueryService spatialService, CancellationToken ct)
    {
        var fc = await spatialService.GetBuffersWithHealthByDateAsync(date, ct);
        return TypedResults.Ok(fc);
    }

    /// <summary>
    /// GET /api/wetlands — NWI wetland polygons from bronze schema (GeoJSON FeatureCollection).
    /// </summary>
    private static async Task<IResult> GetWetlands(
        ISpatialQueryService spatialService, CancellationToken ct)
    {
        var fc = await spatialService.GetWetlandsAsync(ct);
        return TypedResults.Ok(fc);
    }

    /// <summary>
    /// GET /api/buffers/{bufferId}/wetlands — NWI wetland overlaps for a specific buffer.
    /// </summary>
    private static async Task<IResult> GetBufferWetlands(
        int bufferId, IComplianceDataService complianceService, CancellationToken ct)
    {
        var wetlands = await complianceService.GetBufferWetlandsAsync(bufferId, ct);
        return TypedResults.Ok(wetlands);
    }

    /// <summary>
    /// GET /api/buffers/{bufferId}/landcover — NLCD land cover classes for a buffer.
    /// </summary>
    private static async Task<IResult> GetBufferLandCover(
        int bufferId, IComplianceDataService complianceService, CancellationToken ct)
    {
        var landCover = await complianceService.GetBufferLandCoverAsync(bufferId, ct);
        return TypedResults.Ok(landCover);
    }

    /// <summary>
    /// GET /api/buffers/{bufferId}/vegetation-structure — LANDFIRE EVT/EVH for a buffer.
    /// </summary>
    private static async Task<IResult> GetBufferVegetationStructure(
        int bufferId, IComplianceDataService complianceService, CancellationToken ct)
    {
        var vegStructure = await complianceService.GetBufferVegetationStructureAsync(bufferId, ct);
        return TypedResults.Ok(vegStructure);
    }

    /// <summary>
    /// GET /api/soils — SSURGO soil polygons from bronze schema (GeoJSON FeatureCollection).
    /// </summary>
    private static async Task<IResult> GetSoils(
        ISpatialQueryService spatialService, CancellationToken ct)
    {
        var fc = await spatialService.GetSoilsAsync(ct);
        return TypedResults.Ok(fc);
    }

    /// <summary>
    /// GET /api/buffers/{bufferId}/soils — SSURGO soil overlaps for a specific buffer.
    /// </summary>
    private static async Task<IResult> GetBufferSoils(
        int bufferId, IComplianceDataService complianceService, CancellationToken ct)
    {
        var soils = await complianceService.GetBufferSoilsAsync(bufferId, ct);
        return TypedResults.Ok(soils);
    }

    /// <summary>
    /// GET /api/buffers/scores — buffer polygons with SMP composite health scores (GeoJSON FeatureCollection).
    /// </summary>
    private static async Task<IResult> GetBuffersWithScores(
        ISpatialQueryService spatialService, CancellationToken ct)
    {
        var fc = await spatialService.GetBuffersWithScoresAsync(ct);
        return TypedResults.Ok(fc);
    }

    /// <summary>
    /// GET /api/buffers/{bufferId}/score — detailed SMP health score breakdown for a buffer.
    /// </summary>
    private static async Task<IResult> GetBufferHealthScore(
        int bufferId, IComplianceDataService complianceService, CancellationToken ct)
    {
        var scores = await complianceService.GetBufferHealthScoreAsync(bufferId, ct);
        return TypedResults.Ok(scores);
    }

    /// <summary>
    /// GET /api/buffers/{bufferId}/canopy — LiDAR canopy height stats for a buffer.
    /// </summary>
    private static async Task<IResult> GetBufferCanopy(
        int bufferId, IComplianceDataService complianceService, CancellationToken ct)
    {
        var canopy = await complianceService.GetBufferCanopyAsync(bufferId, ct);
        return TypedResults.Ok(canopy);
    }

    /// <summary>
    /// GET /api/tiles/{z}/{x}/{y}.pbf — buffer polygons with SMP health scores (MVT).
    /// </summary>
    private static async Task<IResult> GetBufferTiles(
        int z, int x, int y, ISpatialQueryService spatialService, CancellationToken ct)
    {
        var mvt = await spatialService.GetBufferTilesAsync(z, x, y, ct);
        return mvt.Length == 0
            ? Results.NoContent()
            : Results.Bytes(mvt, "application/x-protobuf");
    }

    /// <summary>
    /// GET /api/tiles/streams/{z}/{x}/{y}.pbf — stream centerlines (MVT).
    /// </summary>
    private static async Task<IResult> GetStreamTiles(
        int z, int x, int y, ISpatialQueryService spatialService, CancellationToken ct)
    {
        var mvt = await spatialService.GetStreamTilesAsync(z, x, y, ct);
        return mvt.Length == 0
            ? Results.NoContent()
            : Results.Bytes(mvt, "application/x-protobuf");
    }

    /// <summary>
    /// GET /api/tiles/parcels/{z}/{x}/{y}.pbf — parcels with compliance (MVT).
    /// </summary>
    private static async Task<IResult> GetParcelTiles(
        int z, int x, int y, ISpatialQueryService spatialService, CancellationToken ct)
    {
        var mvt = await spatialService.GetParcelTilesAsync(z, x, y, ct);
        return mvt.Length == 0
            ? Results.NoContent()
            : Results.Bytes(mvt, "application/x-protobuf");
    }

    /// <summary>
    /// GET /api/tiles/buffers-ndvi/{z}/{x}/{y}.pbf — buffers with latest NDVI health (MVT).
    /// </summary>
    private static async Task<IResult> GetBufferNdviTiles(
        int z, int x, int y, ISpatialQueryService spatialService, CancellationToken ct)
    {
        var mvt = await spatialService.GetBufferNdviTilesAsync(z, x, y, ct);
        return mvt.Length == 0
            ? Results.NoContent()
            : Results.Bytes(mvt, "application/x-protobuf");
    }

    /// <summary>
    /// GET /api/tiles/buffers-ndvi/{date}/{z}/{x}/{y}.pbf — buffers with NDVI for specific date (MVT).
    /// </summary>
    private static async Task<IResult> GetBufferNdviTilesByDate(
        DateOnly date, int z, int x, int y,
        ISpatialQueryService spatialService, CancellationToken ct)
    {
        var mvt = await spatialService.GetBufferNdviTilesByDateAsync(z, x, y, date, ct);
        return mvt.Length == 0
            ? Results.NoContent()
            : Results.Bytes(mvt, "application/x-protobuf");
    }

    /// <summary>
    /// GET /api/tiles/vegetation/{z}/{x}/{y}.pbf — buffers colored by vegetation structure (MVT).
    /// </summary>
    private static async Task<IResult> GetVegetationTiles(
        int z, int x, int y, ISpatialQueryService spatialService, CancellationToken ct)
    {
        var mvt = await spatialService.GetVegetationTilesAsync(z, x, y, ct);
        return mvt.Length == 0
            ? Results.NoContent()
            : Results.Bytes(mvt, "application/x-protobuf");
    }

    /// <summary>
    /// GET /api/tiles/wetlands/{z}/{x}/{y}.pbf — NWI wetland polygons (MVT).
    /// </summary>
    private static async Task<IResult> GetWetlandTiles(
        int z, int x, int y, ISpatialQueryService spatialService, CancellationToken ct)
    {
        var mvt = await spatialService.GetWetlandTilesAsync(z, x, y, ct);
        return mvt.Length == 0
            ? Results.NoContent()
            : Results.Bytes(mvt, "application/x-protobuf");
    }

    /// <summary>
    /// GET /api/tiles/soils/{z}/{x}/{y}.pbf — SSURGO soil polygons (MVT).
    /// </summary>
    private static async Task<IResult> GetSoilTiles(
        int z, int x, int y, ISpatialQueryService spatialService, CancellationToken ct)
    {
        var mvt = await spatialService.GetSoilTilesAsync(z, x, y, ct);
        return mvt.Length == 0
            ? Results.NoContent()
            : Results.Bytes(mvt, "application/x-protobuf");
    }

    /// <summary>
    /// GET /api/tiles/centroids/{z}/{x}/{y}.pbf — buffer centroids for heatmaps (MVT).
    /// </summary>
    private static async Task<IResult> GetBufferCentroidTiles(
        int z, int x, int y, ISpatialQueryService spatialService, CancellationToken ct)
    {
        var mvt = await spatialService.GetBufferCentroidTilesAsync(z, x, y, ct);
        return mvt.Length == 0
            ? Results.NoContent()
            : Results.Bytes(mvt, "application/x-protobuf");
    }

    /// <summary>
    /// GET /api/buffers/health/centroids — buffer centroids with NDVI for heatmap (GeoJSON).
    /// </summary>
    private static async Task<IResult> GetBufferHealthCentroids(
        ISpatialQueryService spatialService, CancellationToken ct)
    {
        var fc = await spatialService.GetBufferHealthCentroidsAsync(ct);
        return TypedResults.Ok(fc);
    }
}

/// <summary>
/// NDVI vegetation health reading for a single date.
/// Uses a class (not positional record) so Dapper uses property-based mapping,
/// which correctly handles snake_case columns with MatchNamesWithUnderscores.
/// </summary>
public sealed class VegetationReading
{
    public int Id { get; init; }
    public int BufferId { get; init; }
    public DateOnly AcquisitionDate { get; init; }
    public decimal? MeanNdvi { get; init; }
    public decimal? MinNdvi { get; init; }
    public decimal? MaxNdvi { get; init; }
    public string HealthCategory { get; init; } = "";
    public string SeasonContext { get; init; } = "";
    public string? Satellite { get; init; }
    public DateTime ProcessedAt { get; init; }
}

/// <summary>
/// Internal DTO for Dapper mapping of distinct acquisition dates.
/// </summary>
public sealed class NdviDateRow
{
    public DateOnly AcquisitionDate { get; init; }
}

/// <summary>
/// Watershed-level compliance summary from the gold schema.
/// Uses a class (not record) so Dapper uses property-based mapping,
/// which correctly handles nullable DB columns.
/// </summary>
public sealed class ComplianceSummary
{
    public int Id { get; init; }
    public int WatershedId { get; init; }
    public string Huc8 { get; init; } = "";
    public decimal? TotalStreamLengthM { get; init; }
    public decimal? TotalBufferAreaSqM { get; init; }
    public int TotalParcels { get; init; }
    public int CompliantParcels { get; init; }
    public int FocusAreaParcels { get; init; }
    public decimal? CompliancePct { get; init; }
    public decimal? AvgNdvi { get; init; }
    public decimal? HealthyBufferPct { get; init; }
    public decimal? DegradedBufferPct { get; init; }
    public decimal? BareBufferPct { get; init; }
    public decimal? AvgCompositeScore { get; init; }
    public decimal? GradeAPct { get; init; }
    public decimal? GradeBPct { get; init; }
    public decimal? GradeCPct { get; init; }
    public decimal? GradeDPct { get; init; }
    public decimal? GradeFPct { get; init; }
    public DateTimeOffset CreatedAt { get; init; }
}

/// <summary>
/// NWI wetland overlap for a riparian buffer from the silver schema.
/// Uses a class (not record) so Dapper uses property-based mapping,
/// which correctly handles snake_case columns with MatchNamesWithUnderscores.
/// </summary>
public sealed class BufferWetland
{
    public int Id { get; init; }
    public int BufferId { get; init; }
    public int WetlandId { get; init; }
    public decimal? OverlapAreaSqM { get; init; }
    public decimal? WetlandPctOfBuffer { get; init; }
    public string? WetlandType { get; init; }
    public string? CowardinCode { get; init; }
    public DateTime ProcessedAt { get; init; }
}

/// <summary>
/// NLCD land cover class entry for a riparian buffer from the silver schema.
/// </summary>
public sealed class BufferLandCover
{
    public int Id { get; init; }
    public int BufferId { get; init; }
    public int NlcdClass { get; init; }
    public string NlcdDescription { get; init; } = "";
    public int PixelCount { get; init; }
    public decimal? AreaPct { get; init; }
    public bool IsNatural { get; init; }
    public int? AcquisitionYear { get; init; }
    public DateTime ProcessedAt { get; init; }
}

/// <summary>
/// LANDFIRE vegetation structure entry for a riparian buffer from the silver schema.
/// </summary>
public sealed class BufferVegetationStructure
{
    public int Id { get; init; }
    public int BufferId { get; init; }
    public int? EvtCode { get; init; }
    public string? EvtName { get; init; }
    public string? EvhClass { get; init; }
    public decimal? MeanHeightM { get; init; }
    public string? DominantLifeform { get; init; }
    public int? PixelCount { get; init; }
    public decimal? AreaPct { get; init; }
    public DateTime ProcessedAt { get; init; }
}

/// <summary>
/// SSURGO soil overlap for a riparian buffer from the silver schema.
/// Uses a class (not record) so Dapper uses property-based mapping,
/// which correctly handles snake_case columns with MatchNamesWithUnderscores.
/// </summary>
public sealed class BufferSoil
{
    public int Id { get; init; }
    public int BufferId { get; init; }
    public int SoilId { get; init; }
    public decimal? OverlapAreaSqM { get; init; }
    public decimal? SoilPctOfBuffer { get; init; }
    public string? HydricRating { get; init; }
    public decimal? HydricPct { get; init; }
    public string? Muname { get; init; }
    public DateTime ProcessedAt { get; init; }
}

/// <summary>
/// SMP composite health score for a riparian buffer from the gold schema.
/// </summary>
public sealed class BufferHealthScore
{
    public int Id { get; init; }
    public int BufferId { get; init; }
    public decimal? NdviScore { get; init; }
    public decimal? VerticalComplexityScore { get; init; }
    public decimal? SpeciesCompositionScore { get; init; }
    public decimal? ShrubLayerScore { get; init; }
    public decimal? PatchinessScore { get; init; }
    public decimal? NativeRegenerationScore { get; init; }
    public decimal? NativeCoverScore { get; init; }
    public decimal? VegetationStructureScore { get; init; }
    public decimal? ConnectivityScore { get; init; }
    public decimal? ContributingAreaScore { get; init; }
    public decimal? CompositeScore { get; init; }
    public string? ScoreGrade { get; init; }
    public DateTime ScoredAt { get; init; }
}

/// <summary>
/// LiDAR canopy height statistics for a riparian buffer from the silver schema.
/// </summary>
public sealed class BufferCanopy
{
    public int Id { get; init; }
    public int BufferId { get; init; }
    public decimal? MeanHeightM { get; init; }
    public decimal? MaxHeightM { get; init; }
    public decimal? P95HeightM { get; init; }
    public decimal? CanopyCoverPct { get; init; }
    public decimal? HeightStdDev { get; init; }
    public DateTime ProcessedAt { get; init; }
}
