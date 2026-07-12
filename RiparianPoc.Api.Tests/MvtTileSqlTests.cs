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

    // --- Layer-name validation -------------------------------------------------------
    // The layer name is the one fragment interpolated into a SQL literal, so it is the only
    // injection surface in Build(). These pin the guard.

    [Theory]
    [InlineData("buffers")]
    [InlineData("riparian_extent")]
    [InlineData("soils")]
    public void Build_AcceptsLowercaseIdentifierLayers(string layer)
    {
        var sql = MvtTileSql.Build(layer, "b.geom", "b.id", "silver.riparian_buffers b");
        Assert.Contains($"'{layer}'", sql);
    }

    [Theory]
    [InlineData("")]                        // empty
    [InlineData("Buffers")]                 // uppercase
    [InlineData("buffers2")]                // digits
    [InlineData("buffers-1")]               // hyphen
    [InlineData("buffers b")]               // space
    [InlineData("buffers'")]                // quote — the actual injection shape
    [InlineData("buffers'; DROP TABLE x--")]
    public void Build_RejectsNonIdentifierLayer(string layer)
    {
        var ex = Assert.Throws<ArgumentException>(
            () => MvtTileSql.Build(layer, "b.geom", "b.id", "silver.riparian_buffers b"));
        Assert.Equal("layer", ex.ParamName);
    }

    [Theory]
    [InlineData("buffers\n")]
    [InlineData("buffers\n'; DROP TABLE x--")]
    public void Build_RejectsLayerWithTrailingNewline(string layer)
    {
        // Regression: .NET's `$` ALSO matches immediately before a trailing newline, so the
        // original `^[a-z_]+$` accepted "buffers\n" — and with it anything smuggled onto the
        // following line. The guard now anchors with \A..\z, which admits no trailing newline.
        var ex = Assert.Throws<ArgumentException>(
            () => MvtTileSql.Build(layer, "b.geom", "b.id", "silver.riparian_buffers b"));
        Assert.Equal("layer", ex.ParamName);
    }

    // --- Enriched popup columns (soils / wetlands) ------------------------------------
    // The tile payload feeds the map popups; if a column is dropped from the tile the popup
    // silently renders blank rather than failing, so assert the columns reach the SQL.

    [Fact]
    public void Build_SoilTile_CarriesHydricPopupColumns()
    {
        var sql = MvtTileSql.Build(
            "soils", "s.geom", "s.mukey, s.muname, s.hydric_pct", "bronze.ssurgo_soils s");
        Assert.Contains("s.mukey", sql);
        Assert.Contains("s.muname", sql);
        Assert.Contains("s.hydric_pct", sql);
    }

    [Fact]
    public void Build_WetlandTile_CarriesCowardinPopupColumns()
    {
        var sql = MvtTileSql.Build(
            "wetlands", "w.geom", "w.cowardin_code, w.acres", "bronze.nwi_wetlands w");
        Assert.Contains("w.cowardin_code", sql);
        Assert.Contains("w.acres", sql);
    }
}
