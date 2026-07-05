using Microsoft.Extensions.Logging;
using NetTopologySuite.Features;
using NSubstitute;
using RiparianPoc.Api.Repositories;
using RiparianPoc.Api.Services;
using Xunit;

namespace RiparianPoc.Api.Tests;

/// <summary>
/// Unit tests for <see cref="SpatialQueryService"/>. The <see cref="IPostGisRepository"/>
/// is mocked — this is exactly why the repository interface earns its keep (it lets the
/// service be tested without a database). See docs/decisions/2026-07-04-nextaurora-rules-applicability.md.
/// </summary>
public sealed class SpatialQueryServiceTests
{
    private readonly IPostGisRepository _repo = Substitute.For<IPostGisRepository>();
    private readonly ILogger<SpatialQueryService> _logger =
        Substitute.For<ILogger<SpatialQueryService>>();

    private SpatialQueryService CreateSut() => new(_repo, _logger);

    [Fact]
    public void Constructor_NullRepository_Throws()
    {
        // ARRANGE / ACT / ASSERT — null guard on the injected dependency
        Assert.Throws<ArgumentNullException>(() => new SpatialQueryService(null!, _logger));
    }

    [Fact]
    public async Task GetRiparianExtentAsync_ReturnsWhatTheRepositoryReturns()
    {
        // ARRANGE — the repo yields a canned feature collection
        var expected = new FeatureCollection();
        _repo.QueryGeoJsonAsync(
                Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>())
            .Returns(expected);

        // ACT
        var result = await CreateSut().GetRiparianExtentAsync("rf", CancellationToken.None);

        // ASSERT — the service passes the repository result straight through
        Assert.Same(expected, result);
    }

    [Fact]
    public async Task GetRiparianExtentAsync_QueriesSilverExtentTableParameterizedByMethod()
    {
        // ARRANGE
        _repo.QueryGeoJsonAsync(
                Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>())
            .Returns(new FeatureCollection());
        var sut = CreateSut();

        // ACT
        await sut.GetRiparianExtentAsync("rf", CancellationToken.None);

        // ASSERT — SQL targets silver.riparian_extent and filters on the @method parameter
        await _repo.Received(1).QueryGeoJsonAsync(
            Arg.Is<string>(sql =>
                sql.Contains("silver.riparian_extent") && sql.Contains("@method")),
            Arg.Any<object?>(),
            Arg.Any<CancellationToken>());
    }

    [Fact]
    public async Task GetRiparianExtentAsync_NullMethodFilter_StillQueries()
    {
        // ARRANGE — a null method means "all methods"; the query still runs
        _repo.QueryGeoJsonAsync(
                Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>())
            .Returns(new FeatureCollection());

        // ACT
        var result = await CreateSut().GetRiparianExtentAsync(null, CancellationToken.None);

        // ASSERT
        Assert.NotNull(result);
        await _repo.Received(1).QueryGeoJsonAsync(
            Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>());
    }
}
