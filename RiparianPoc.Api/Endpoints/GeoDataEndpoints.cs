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
        api.MapGet("/parcels", GetParcels).WithName("GetParcels");
        api.MapGet("/focus-areas", GetFocusAreas).WithName("GetFocusAreas");
        api.MapGet("/vegetation/buffers/{bufferId:int}", GetVegetationByBuffer)
            .WithName("GetVegetationByBuffer");
        api.MapGet("/summary", GetSummary).WithName("GetSummary");

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
}

/// <summary>
/// NDVI vegetation health reading for a single date.
/// </summary>
public sealed record VegetationReading(
    int Id,
    int BufferId,
    DateOnly AcquisitionDate,
    decimal? MeanNdvi,
    decimal? MinNdvi,
    decimal? MaxNdvi,
    string HealthCategory,
    string SeasonContext,
    string? Satellite,
    DateTimeOffset ProcessedAt);

/// <summary>
/// Watershed-level compliance summary from the gold schema.
/// </summary>
public sealed record ComplianceSummary(
    int Id,
    int WatershedId,
    string Huc8,
    decimal? TotalStreamLengthM,
    decimal? TotalBufferAreaSqM,
    int TotalParcels,
    int CompliantParcels,
    int FocusAreaParcels,
    decimal? CompliancePct,
    decimal? AvgNdvi,
    decimal? HealthyBufferPct,
    decimal? DegradedBufferPct,
    decimal? BareBufferPct,
    DateTimeOffset CreatedAt);
