using NetTopologySuite.IO.Converters;
using OpenTelemetry.Trace;
using RiparianPoc.Api.Endpoints;
using RiparianPoc.Api.Middleware;
using RiparianPoc.Api.Repositories;
using RiparianPoc.Api.Services;

Dapper.DefaultTypeMap.MatchNamesWithUnderscores = true;

var builder = WebApplication.CreateBuilder(args);

builder.AddServiceDefaults();

// Register Npgsql data source for PostGIS (connection string "ripariandb" from Aspire)
builder.AddNpgsqlDataSource("ripariandb");

// Register repository and service layers
builder.Services.AddScoped<IPostGisRepository, PostGisRepository>();
builder.Services.AddScoped<ISpatialQueryService, SpatialQueryService>();
builder.Services.AddScoped<IComplianceDataService, ComplianceDataService>();

// Register custom ActivitySources for OpenTelemetry tracing
builder.Services.AddOpenTelemetry()
    .WithTracing(tracing => tracing
        .AddSource("RiparianPoc.Api.Repository")
        .AddSource("RiparianPoc.Api.SpatialQuery")
        .AddSource("RiparianPoc.Api.ComplianceData"));

// Configure GeoJSON serialization via NetTopologySuite
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.Converters.Add(new GeoJsonConverterFactory());
});

builder.Services.AddOpenApi();

// CORS — open for development
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.AllowAnyOrigin()
              .AllowAnyMethod()
              .AllowAnyHeader()
              .WithExposedHeaders("X-Correlation-Id");
    });
});

var app = builder.Build();

app.MapDefaultEndpoints();

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

// Correlation middleware first: establishes IDs and logging scope for everything downstream
app.UseMiddleware<CorrelationMiddleware>();

// Exception handling second: has correlation context, catches errors from all downstream
app.UseMiddleware<ExceptionHandlingMiddleware>();

app.UseCors();
app.UseHttpsRedirection();
app.MapGeoDataEndpoints();

await app.RunAsync();
