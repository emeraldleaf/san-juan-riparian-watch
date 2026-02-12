using NetTopologySuite.Features;
using RiparianPoc.Api.Endpoints;

namespace RiparianPoc.Api.Services;

/// <summary>
/// Provides GeoJSON FeatureCollection queries for spatial map layers.
/// </summary>
public interface ISpatialQueryService
{
    /// <summary>Returns stream centerlines from the bronze schema.</summary>
    Task<FeatureCollection> GetStreamsAsync(CancellationToken ct);

    /// <summary>Returns riparian buffer polygons from the silver schema.</summary>
    Task<FeatureCollection> GetBuffersAsync(CancellationToken ct);

    /// <summary>Returns all parcels with compliance status.</summary>
    Task<FeatureCollection> GetParcelsAsync(CancellationToken ct);

    /// <summary>Returns only focus-area parcels.</summary>
    Task<FeatureCollection> GetFocusAreasAsync(CancellationToken ct);

    /// <summary>Returns buffer polygons with latest peak-growing NDVI health data.</summary>
    Task<FeatureCollection> GetBuffersWithHealthAsync(CancellationToken ct);

    /// <summary>Returns buffer polygons with NDVI health data for a specific acquisition date.</summary>
    Task<FeatureCollection> GetBuffersWithHealthByDateAsync(DateOnly date, CancellationToken ct);
}

/// <summary>
/// Provides non-spatial compliance and vegetation data queries.
/// </summary>
public interface IComplianceDataService
{
    /// <summary>Returns NDVI time series readings for a specific buffer.</summary>
    Task<IReadOnlyList<VegetationReading>> GetVegetationByBufferAsync(
        int bufferId, CancellationToken ct);

    /// <summary>Returns watershed-level compliance summaries from the gold schema.</summary>
    Task<IReadOnlyList<ComplianceSummary>> GetSummaryAsync(CancellationToken ct);

    /// <summary>Returns distinct NDVI acquisition dates ordered chronologically.</summary>
    Task<IReadOnlyList<DateOnly>> GetNdviDatesAsync(CancellationToken ct);
}
