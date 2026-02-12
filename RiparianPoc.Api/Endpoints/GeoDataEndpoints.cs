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
