using Microsoft.Extensions.Logging;
using NSubstitute;
using RiparianPoc.Api.Endpoints;
using RiparianPoc.Api.Repositories;
using RiparianPoc.Api.Services;
using Xunit;

namespace RiparianPoc.Api.Tests;

/// <summary>
/// Unit tests for <see cref="ComplianceDataService"/> input validation. Validation lives in
/// the service (per CLAUDE.md "Service Layer Architecture"), so it is testable without a DB
/// by mocking <see cref="IPostGisRepository"/>.
/// </summary>
public sealed class ComplianceDataServiceTests
{
    private readonly IPostGisRepository _repo = Substitute.For<IPostGisRepository>();
    private readonly ILogger<ComplianceDataService> _logger =
        Substitute.For<ILogger<ComplianceDataService>>();

    private ComplianceDataService CreateSut() => new(_repo, _logger);

    [Fact]
    public void Constructor_NullRepository_Throws()
    {
        // ARRANGE / ACT / ASSERT
        Assert.Throws<ArgumentNullException>(() => new ComplianceDataService(null!, _logger));
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(-100)]
    public async Task GetVegetationByBufferAsync_NonPositiveBufferId_ThrowsArgumentException(
        int badId)
    {
        // ARRANGE
        var sut = CreateSut();

        // ACT / ASSERT — the service rejects the bad id before touching the repository
        await Assert.ThrowsAsync<ArgumentException>(
            () => sut.GetVegetationByBufferAsync(badId, CancellationToken.None));

        await _repo.DidNotReceive().QueryAsync<VegetationReading>(
            Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>());
    }

    [Fact]
    public async Task GetVegetationByBufferAsync_ValidId_DelegatesToRepository()
    {
        // ARRANGE
        IReadOnlyList<VegetationReading> expected = new List<VegetationReading>();
        _repo.QueryAsync<VegetationReading>(
                Arg.Any<string>(), Arg.Any<object?>(), Arg.Any<CancellationToken>())
            .Returns(expected);

        // ACT
        var result = await CreateSut().GetVegetationByBufferAsync(42, CancellationToken.None);

        // ASSERT — a positive id passes validation and the repository result flows through
        Assert.Same(expected, result);
    }
}
