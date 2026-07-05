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

    /// <summary>Returns buffer polygons with SMP composite health scores.</summary>
    Task<FeatureCollection> GetBuffersWithScoresAsync(CancellationToken ct);

    /// <summary>
    /// Returns Stage-1 riparian extent polygons from silver.riparian_extent, optionally
    /// filtered by delineation method (<c>rf</c> baseline or <c>olmoearth</c>).
    /// </summary>
    /// <param name="method">Delineation method filter, or null for all methods.</param>
    Task<FeatureCollection> GetRiparianExtentAsync(string? method, CancellationToken ct);

    /// <summary>Returns buffer polygons with NDVI health data for a specific acquisition date.</summary>
    Task<FeatureCollection> GetBuffersWithHealthByDateAsync(DateOnly date, CancellationToken ct);

    /// <summary>
    /// Returns a Mapbox Vector Tile (MVT) binary blob containing riparian buffer polygons
    /// enriched with their latest health scores.
    /// </summary>
    /// <param name="z">Zoom level</param>
    /// <param name="x">Tile X coordinate</param>
    /// <param name="y">Tile Y coordinate</param>
    Task<byte[]> GetBufferTilesAsync(int z, int x, int y, CancellationToken ct);

    /// <summary>Returns NWI wetland polygons from the bronze schema.</summary>
    Task<FeatureCollection> GetWetlandsAsync(CancellationToken ct);

    /// <summary>Returns SSURGO soil polygons from the bronze schema.</summary>
    Task<FeatureCollection> GetSoilsAsync(CancellationToken ct);

    /// <summary>Returns an MVT blob for SSURGO soil polygons at the given tile coordinate.</summary>
    Task<byte[]> GetSoilTilesAsync(int z, int x, int y, CancellationToken ct);

    /// <summary>Returns an MVT blob for buffers colored by vegetation structure at the given tile coordinate.</summary>
    Task<byte[]> GetVegetationTilesAsync(int z, int x, int y, CancellationToken ct);

    /// <summary>Returns an MVT blob for NWI wetland polygons at the given tile coordinate.</summary>
    Task<byte[]> GetWetlandTilesAsync(int z, int x, int y, CancellationToken ct);

    /// <summary>Returns an MVT blob for stream centerlines at the given tile coordinate.</summary>
    Task<byte[]> GetStreamTilesAsync(int z, int x, int y, CancellationToken ct);

    /// <summary>Returns an MVT blob for parcels with compliance status at the given tile coordinate.</summary>
    Task<byte[]> GetParcelTilesAsync(int z, int x, int y, CancellationToken ct);

    /// <summary>Returns an MVT blob for buffers with latest NDVI health at the given tile coordinate.</summary>
    Task<byte[]> GetBufferNdviTilesAsync(int z, int x, int y, CancellationToken ct);

    /// <summary>Returns an MVT blob for buffers with NDVI health for a specific date.</summary>
    Task<byte[]> GetBufferNdviTilesByDateAsync(int z, int x, int y, DateOnly date, CancellationToken ct);

    /// <summary>Returns an MVT blob for buffer centroids with NDVI health data (heatmap optimization).</summary>
    Task<byte[]> GetBufferCentroidTilesAsync(int z, int x, int y, CancellationToken ct);

    /// <summary>Returns buffer centroids with NDVI values for heatmap rendering (lightweight GeoJSON Points).</summary>
    Task<FeatureCollection> GetBufferHealthCentroidsAsync(CancellationToken ct);
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

    /// <summary>Returns NWI wetland overlaps for a specific buffer.</summary>
    Task<IReadOnlyList<BufferWetland>> GetBufferWetlandsAsync(
        int bufferId, CancellationToken ct);

    /// <summary>Returns NLCD land cover class distribution for a specific buffer.</summary>
    Task<IReadOnlyList<BufferLandCover>> GetBufferLandCoverAsync(
        int bufferId, CancellationToken ct);

    /// <summary>Returns LANDFIRE vegetation structure for a specific buffer.</summary>
    Task<IReadOnlyList<BufferVegetationStructure>> GetBufferVegetationStructureAsync(
        int bufferId, CancellationToken ct);

    /// <summary>Returns SSURGO soil overlaps for a specific buffer.</summary>
    Task<IReadOnlyList<BufferSoil>> GetBufferSoilsAsync(
        int bufferId, CancellationToken ct);

    /// <summary>Returns SMP composite health score for a specific buffer.</summary>
    Task<IReadOnlyList<BufferHealthScore>> GetBufferHealthScoreAsync(
        int bufferId, CancellationToken ct);

    /// <summary>Returns LiDAR canopy height stats for a specific buffer.</summary>
    Task<IReadOnlyList<BufferCanopy>> GetBufferCanopyAsync(
        int bufferId, CancellationToken ct);
}
