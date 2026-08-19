using Microsoft.Extensions.Logging;
using NSubstitute;
using RiparianPoc.Api.Repositories;
using RiparianPoc.Api.Services;
using Xunit;

namespace RiparianPoc.Api.Tests;

/// <summary>
/// Unit tests for <see cref="AgentQueryService"/>. Metric/method validation lives in the
/// service (CLAUDE.md "Service Layer Architecture"), so it is testable without a DB by
/// mocking <see cref="IPostGisRepository"/>. These pin the contract — validation, the
/// share-percent math, provenance — not the SQL (the live-PostGIS job exercises that).
/// </summary>
public sealed class AgentQueryServiceTests
{
    private const string Geom = """{"type":"Point","coordinates":[-108.2,36.73]}""";

    private readonly IPostGisRepository _repo = Substitute.For<IPostGisRepository>();
    private readonly ILogger<AgentQueryService> _logger =
        Substitute.For<ILogger<AgentQueryService>>();

    private AgentQueryService CreateSut() => new(_repo, _logger);

    [Fact]
    public void Constructor_NullRepository_Throws()
    {
        Assert.Throws<ArgumentNullException>(() => new AgentQueryService(null!, _logger));
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public async Task GetAreaMetricAsync_MissingGeometry_ThrowsArgumentException(string geom)
    {
        await Assert.ThrowsAsync<ArgumentException>(
            () => CreateSut().GetAreaMetricAsync("extent", geom, "rf", CancellationToken.None));

        await _repo.DidNotReceive().QueryAsync<AreaRow>(
            Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>());
    }

    [Fact]
    public async Task GetAreaMetricAsync_UnknownMetric_ThrowsBeforeTouchingRepository()
    {
        // invasive-share has no materialized table yet — it must be rejected, not guessed.
        await Assert.ThrowsAsync<ArgumentException>(
            () => CreateSut().GetAreaMetricAsync(
                "invasive-share", Geom, "rf", CancellationToken.None));

        await _repo.DidNotReceive().QueryAsync<AreaRow>(
            Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>());
    }

    [Theory]
    [InlineData("bogus")]
    [InlineData("all")]
    public async Task GetAreaMetricAsync_ExtentWithBadMethod_ThrowsArgumentException(string method)
    {
        await Assert.ThrowsAsync<ArgumentException>(
            () => CreateSut().GetAreaMetricAsync("extent", Geom, method, CancellationToken.None));

        await _repo.DidNotReceive().QueryAsync<AreaRow>(
            Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>());
    }

    [Fact]
    public async Task GetAreaMetricAsync_Extent_ComputesSharePercentAndProvenance()
    {
        // A cell right in the corridor (nearest = 0) → covered, share computed.
        IReadOnlyList<AreaRow> rows = new List<AreaRow>
        {
            new() { AreaSqM = 404686.0, RiparianSqM = 40468.6, NearestCellM = 0.0 },
        };
        _repo.QueryAsync<AreaRow>(
                Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>())
            .Returns(rows);

        var result = await CreateSut().GetAreaMetricAsync(
            "extent", Geom, "rf", CancellationToken.None);

        Assert.Equal("extent", result.Metric);
        Assert.True(result.Covered);
        Assert.Equal(10.0, result.Value!.Value, 3); // 10 riparian acres / 100 acres
        Assert.Equal("percent riparian", result.Unit);
        Assert.Contains("riparian_extent", result.Provenance);
        Assert.Equal("rf", result.Method);
    }

    [Fact]
    public async Task GetAreaMetricAsync_Extent_FarFromAnyCell_RefusesInsteadOfZero()
    {
        // The Animas case: nearest extent cell ~3 km away → outside the modeled
        // region → Covered=false, not a confident 0%.
        IReadOnlyList<AreaRow> rows = new List<AreaRow>
        {
            new() { AreaSqM = 500000.0, RiparianSqM = 0.0, NearestCellM = 2947.0 },
        };
        _repo.QueryAsync<AreaRow>(
                Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>())
            .Returns(rows);

        var result = await CreateSut().GetAreaMetricAsync(
            "extent", Geom, "rf", CancellationToken.None);

        Assert.False(result.Covered);
        Assert.Null(result.Value);
        Assert.Contains("does not cover", result.Detail);
    }

    [Fact]
    public async Task GetAreaMetricAsync_Extent_NoCellsAtAll_RefusesAsUnmodeled()
    {
        // No rows (null nearest) → the method has no extent → refuse, don't zero.
        _repo.QueryAsync<AreaRow>(
                Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>())
            .Returns(new List<AreaRow>());

        var result = await CreateSut().GetAreaMetricAsync(
            "extent", Geom, "olmoearth", CancellationToken.None);

        Assert.False(result.Covered);
        Assert.Null(result.Value);
        Assert.Equal("olmoearth", result.Method);
    }

    [Fact]
    public async Task GetAreaMetricAsync_HealthGrade_MapsMeanComposite()
    {
        IReadOnlyList<AreaRow> rows =
            new List<AreaRow> { new() { MeanComposite = 72.34, ScoredBuffers = 5 } };
        _repo.QueryAsync<AreaRow>(
                Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>())
            .Returns(rows);

        var result = await CreateSut().GetAreaMetricAsync(
            "health-grade", Geom, "rf", CancellationToken.None);

        Assert.Equal("health-grade", result.Metric);
        Assert.True(result.Covered); // 5 scored buffers present
        Assert.Equal(72.3, result.Value!.Value, 3); // rounded to 1 dp
        Assert.Contains("buffer_health_score", result.Provenance);
    }
}
