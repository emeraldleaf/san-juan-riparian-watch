---
description: Scaffold a new C# API endpoint following the service → repository → thin-handler pattern
argument-hint: <route + one-line description, e.g. "GET /api/riparian/extent — riparian extent by method">
disable-model-invocation: true
---

# /add-endpoint

Scaffold a new API endpoint that respects the project's service-layer architecture. The
endpoint is a thin delegate; the SQL and logic live in the service; data access goes through
the generic repository. See CLAUDE.md "Service Layer Architecture" + "Common Patterns".

`$ARGUMENTS` is the route + a one-line description. If empty, ask for it.

## Steps (do them in this order)

1. **Pick the interface.** GeoJSON/spatial result → `ISpatialQueryService`; typed DTO/scalar
   result → `IComplianceDataService`. Add the method signature (with `CancellationToken`) to
   the interface in `RiparianPoc.Api/Services/IGeoDataServices.cs`. If the result is a new
   shape, add a `record` DTO in `GeoDataEndpoints.cs`.
2. **Implement in `GeoDataServices.cs`.** Write the SQL with `ST_AsGeoJSON(geom) AS geojson`
   for spatial results. Call `_repository.QueryGeoJsonAsync(...)` (dynamic GeoJSON rows) or
   `_repository.QueryAsync<T>(...)` (typed). Wrap in `using var activity =
   Source.StartActivity("...")` and `activity?.SetTag(...)` for result counts. Validate input
   here (`throw new ArgumentException(...)` for bad IDs). Pass the `CancellationToken` via
   `CommandDefinition`.
3. **Add the thin route handler** in `RiparianPoc.Api/Endpoints/GeoDataEndpoints.cs`: inject
   the service interface, call the one method, `return TypedResults.Ok(result)`. No SQL, no
   logic in the handler.
4. **Confirm DI.** The service is already `AddScoped` in Program.cs; only add registration if
   you introduced a new interface.

## Guardrails

- **Refuse to put SQL in the endpoint.** If the request implies logic in the handler, push it
  into the service and say why.
- **Spatial rules apply**: EPSG:4269 storage, `geom::geography` for distance/area, `&&` bbox
  pre-filter, GiST-indexed geom. See CLAUDE.md "Spatial Data".
- **No new NuGet packages without asking.**
- Output the diffs for review; don't claim it works until it builds (`dotnet build`) — see the
  `verification-before-completion` skill.

## Reference

Mirror an existing endpoint of the same shape (e.g. `GET /api/buffers/health` for a
LEFT JOIN LATERAL GeoJSON result). Name the canonical file you're mirroring in your output.
