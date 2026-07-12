using RiparianPoc.Api.Services;
using Xunit;

namespace RiparianPoc.Api.Tests;

/// <summary>
/// Guards the single canonical MVT tile shape produced by <see cref="MvtTileSql"/>. Every tile
/// endpoint routes through <c>Build()</c>, so the correctness- and performance-critical
/// invariants — the index-backed bbox pre-filter, the SRID transforms, the 4096 extent, and the
/// pre-filter running BEFORE any extra join — are asserted once here instead of being copy-pasted
/// (and silently drifting) across nine per-layer queries.
/// </summary>
public sealed class MvtTileSqlTests
{
    [Fact]
    public void Build_EmitsParameterizedTileEnvelope()
    {
        // tile coordinates are bound as @parameters, never interpolated
        var sql = MvtTileSql.Build("buffers", "b.geom", "b.id", "silver.riparian_buffers b");
        Assert.Contains("ST_TileEnvelope(@z, @x, @y)", sql);
    }

    [Fact]
    public void Build_UsesIndexBackedBboxPreFilterInStorageCrs()
    {
        // && against the source SRID (4269) is what lets PostGIS hit the GiST index
        var sql = MvtTileSql.Build("buffers", "b.geom", "b.id", "silver.riparian_buffers b");
        Assert.Contains("b.geom && ST_Transform(tile.envelope, 4269)", sql);
    }

    [Fact]
    public void Build_TransformsTileGeometryToWebMercator()
    {
        var sql = MvtTileSql.Build("streams", "s.geom", "s.id", "bronze.streams s");
        Assert.Contains("ST_AsMVTGeom(ST_Transform(s.geom, 3857), tile.envelope)", sql);
    }

    [Fact]
    public void Build_EmitsLayerNameAndStandardExtent()
    {
        var sql = MvtTileSql.Build("wetlands", "w.geom", "w.id", "bronze.nwi_wetlands w");
        Assert.Contains("ST_AsMVT(mvt_geom.*, 'wetlands', 4096, 'geom')", sql);
    }

    [Fact]
    public void Build_RenderGeomOverride_KeepsPreFilterOnIndexedColumn()
    {
        // the centroids layer renders ST_Centroid but must still pre-filter on the raw
        // indexed geometry, or the GiST index is bypassed
        var sql = MvtTileSql.Build(
            "centroids", "b.geom", "b.id, vh.mean_ndvi", "silver.riparian_buffers b",
            renderGeom: "ST_Centroid(b.geom)");

        Assert.Contains("ST_AsMVTGeom(ST_Transform(ST_Centroid(b.geom), 3857)", sql);
        Assert.Contains("b.geom && ST_Transform(tile.envelope, 4269)", sql);
    }

    [Fact]
    public void Build_PreFilterRunsBeforeExtraJoins()
    {
        // the bbox filter must sit immediately after the source table, before any LEFT JOIN,
        // or the planner may evaluate expensive joins for out-of-tile rows — the exact
        // 10-40x regression the pre-filter exists to avoid
        var sql = MvtTileSql.Build(
            "buffers", "b.geom", "b.id", "silver.riparian_buffers b",
            extraJoins: "LEFT JOIN silver.buffer_vegetation_structure v ON b.id = v.buffer_id");

        var tileJoin = sql.IndexOf("JOIN tile ON", StringComparison.Ordinal);
        var extraJoin = sql.IndexOf(
            "LEFT JOIN silver.buffer_vegetation_structure", StringComparison.Ordinal);

        Assert.True(tileJoin >= 0 && extraJoin >= 0);
        Assert.True(tileJoin < extraJoin, "tile bbox pre-filter must precede extra joins");
    }

    [Fact]
    public void Build_AppendsOptionalWhereClause()
    {
        var sql = MvtTileSql.Build(
            "centroids", "b.geom", "b.id", "silver.riparian_buffers b",
            where: "WHERE vh.mean_ndvi IS NOT NULL");
        Assert.Contains("WHERE vh.mean_ndvi IS NOT NULL", sql);
    }
}
