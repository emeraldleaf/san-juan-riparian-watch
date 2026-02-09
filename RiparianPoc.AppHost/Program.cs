var builder = DistributedApplication.CreateBuilder(args);

// PostGIS database — postgis/postgis:16-3.4 with ripariandb
var ripariandb = builder.AddPostgres("postgres")
    .WithImage("postgis/postgis")
    .WithImageTag("16-3.4")
    .WithLifetime(ContainerLifetime.Persistent)
    .AddDatabase("ripariandb");

// C# REST API — waits for PostGIS, exposes HTTP externally
var api = builder.AddProject<Projects.RiparianPoc_Api>("api")
    .WithReference(ripariandb)
    .WaitFor(ripariandb)
    .WithExternalHttpEndpoints();

// Python ETL pipeline — Dockerfile-based, waits for PostGIS
// Set ETL_MODE=scheduled + ETL_SCHEDULE_CRON for recurring updates
var etl = builder.AddDockerfile("etl", "../python-etl")
    .WithReference(ripariandb)
    .WaitFor(ripariandb)
    .WithEnvironment("ETL_MODE", builder.Configuration["ETL_MODE"] ?? "full")
    .WithEnvironment("ETL_SCHEDULE_CRON", builder.Configuration["ETL_SCHEDULE_CRON"] ?? "")
    .WithEnvironment("ETL_SCHEDULE_INTERVAL_HOURS", builder.Configuration["ETL_SCHEDULE_INTERVAL_HOURS"] ?? "")
    .WithEnvironment("ETL_UPDATE_TYPE", builder.Configuration["ETL_UPDATE_TYPE"] ?? "incremental");

// React frontend — Vite dev server locally, Dockerfile for Azure deployment
var frontend = builder.AddJavaScriptApp("frontend", "../frontend", "dev")
    .WithReference(api)
    .WaitFor(api)
    .WithExternalHttpEndpoints()
    .PublishAsDockerFile();

builder.Build().Run();
