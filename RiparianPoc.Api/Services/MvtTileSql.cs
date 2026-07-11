namespace RiparianPoc.Api.Services;

/// <summary>
/// Builds Mapbox Vector Tile (MVT) SQL with a single canonical shape so the
/// correctness- and performance-critical parts cannot drift between layers:
/// <list type="bullet">
///   <item>an index-backed bbox pre-filter — <c>&amp;&amp; ST_Transform(tile.envelope, 4269)</c>
///   placed immediately after the source table so the GiST index is used before any
///   expensive join (the 10–40× speedup);</item>
///   <item>SRID transforms — storage CRS 4269 → Web Mercator 3857 for the tile geometry;</item>
///   <item>a 4096-extent <c>ST_AsMVT</c> wrapper.</item>
/// </list>
/// Only compile-time SQL fragments are interpolated here (layer names, column lists,
/// join clauses defined in code). Tile coordinates and dates are always bound as
/// <c>@z/@x/@y/@date</c> parameters by the caller — never interpolated.
/// </summary>
internal static class MvtTileSql
{
    /// <summary>
    /// Assemble the tile query. <paramref name="geom"/> is the source geometry column
    /// used for the index pre-filter; <paramref name="renderGeom"/> overrides the geometry
    /// that is encoded into the tile (e.g. <c>ST_Centroid(b.geom)</c>) while the pre-filter
    /// still runs against the indexed column. <paramref name="extraJoins"/> is appended after
    /// the tile join so join order — and therefore the pre-filter's index use — is preserved.
    /// </summary>
    internal static string Build(
        string layer,
        string geom,
        string columns,
        string from,
        string extraJoins = "",
        string where = "",
        string? renderGeom = null)
    {
        // Defense in depth: the layer name is interpolated into a single-quoted SQL literal.
        // All callers pass compile-time constants, but validate anyway so a future caller can't
        // introduce an injection through it. Every real layer is a lowercase identifier.
        if (!System.Text.RegularExpressions.Regex.IsMatch(layer, "^[a-z_]+$"))
        {
            throw new ArgumentException(
                $"Layer name must be a lowercase identifier, got '{layer}'", nameof(layer));
        }

        var render = renderGeom ?? geom;
        return $"""
            WITH tile AS (
                SELECT ST_TileEnvelope(@z, @x, @y) AS envelope
            ),
            mvt_geom AS (
                SELECT
                    {columns},
                    ST_AsMVTGeom(ST_Transform({render}, 3857), tile.envelope) AS geom
                FROM {from}
                JOIN tile ON {geom} && ST_Transform(tile.envelope, 4269)
                {extraJoins}
                {where}
            )
            SELECT ST_AsMVT(mvt_geom.*, '{layer}', 4096, 'geom')
            FROM mvt_geom;
            """;
    }
}
