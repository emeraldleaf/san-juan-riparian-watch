# docintel API contract (public seam)

The **stable contract** between the private RAG backend and the public riparian frontend. This is
what lets the harness stay private while the integration stays reproducible: anyone can implement
this contract; ours happens to be backed by the Re-find Catalog harness. Two endpoints.

Storage/return CRS is **EPSG:4269 (NAD83)**; geometry is GeoJSON. Grounding is enforced
backend-side ("no source, no claim"); the resolver — not the LLM — produces geometry.

## `POST /docs/ask`

Ask a question; get a cited answer plus resolved geography to drive the map.

**Request**
```json
{
  "question": "What does the plan say about tamarisk control near Farmington?",
  "top_k": 8,                      // optional; backend default if omitted
  "map_context": {                 // optional; current map view to bias retrieval
    "huc12": "140801041003",
    "bbox": [-108.017, 36.872, -107.804, 36.977]
  }
}
```

**Response**
```json
{
  "answer": "…grounded synthesis…",
  "citations": [
    {
      "doc_id": "sjrip-bassett-2015-historical-ecology-riparian",
      "title": "San Juan River Historical Ecology Assessment…",
      "page_start": 42, "page_end": 43,
      "snippet": "…Russian olive and tamarisk encroachment…",
      "source_url": "https://…"
    }
  ],
  "geo_mentions": [                 // free-form, from the generation step (no geometry here)
    { "mention_text": "Animas River near Farmington", "mention_type": "river", "confidence": 0.86 }
  ],
  "resolved_geometries": [          // produced by docintel/geo/resolver.py (deterministic)
    {
      "mention_text": "Animas River near Farmington",
      "chosen": {
        "kind": "nhd_flowline",
        "ref": "gnis=Animas River",
        "geom_geojson": { "type": "MultiLineString", "coordinates": [ /* … */ ] },
        "confidence": 0.9
      },
      "candidates": [ /* full set when ambiguous; UI offers a pick */ ]
    }
  ],
  "insufficient_evidence": false    // true → answer withheld, UI shows the "no grounded answer" state
}
```

The frontend: renders `answer` + `citations`; fits/zooms to the union of `resolved_geometries`,
highlights each, and offers to overlay the riparian extent / health / invasive layers there.

## `POST /docs/for-area`

Map-click reverse lookup: given a clicked point or polygon, return the documents relevant to that
area, with a cited summary.

**Request**
```json
{
  "geometry": { "type": "Point", "coordinates": [-108.05, 36.92] },   // or a Polygon
  "radius_m": 1000                 // optional; buffer a point before the spatial join
}
```

**Response**
```json
{
  "resolved_keys": {               // deterministic resolution of the click
    "huc12": "140801041003",
    "nearest_river": "Animas River",
    "nearest_reach_id": 8123
  },
  "summary": "…cited synthesis of what the corpus says about this area…",
  "citations": [ /* same shape as /docs/ask */ ],
  "documents": [                   // ranked docs touching this area (via docs.chunk_geo_mentions)
    { "doc_id": "…", "title": "…", "agency": "SJRIP", "year": 2015, "relevance": 0.87 }
  ],
  "insufficient_evidence": false
}
```

Retrieval is two-tier: **deterministic geo-linked chunks first** (spatial join on
`docs.chunk_geo_mentions`), semantic fallback second.

## Types

`geo_mentions[].mention_type` ∈ `river | reservoir | huc | town | reach | place | coord | bbox`.
`resolved_geometries[].chosen.kind` ∈ `huc12 | huc8 | nhd_flowline | reach | gnis` (or `null` when
unresolved). These mirror `docintel/geo/models.py` (`MentionType`, `ResolvedKind`) and the
`docs.chunk_geo_mentions` columns in `sql/docintel_migration.sql`.
