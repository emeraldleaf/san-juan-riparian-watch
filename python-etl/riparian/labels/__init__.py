"""Label sources and the crosswalk that normalizes them.

Existing riparian/wetland GIS products are **weak labels with confidence**, not gospel.
This subpackage normalizes each source's native classes into one vocabulary so they can
be fused (and so a bad mapping is visible in a CSV rather than buried in a rasterizer).

Sources:
- ``nmripmap`` — NM Natural Heritage riparian habitat map (NM half of the basin). The only
  one wired up so far. Its ``L2_Code`` hierarchy also yields a free **tamarisk /
  Russian-olive** label (``IC``) for the Stage-2 invasives track.
- *planned*: CO-RIP (Colorado side), CNHP wetlands, NWI, NLCD (confusion classes),
  manually digitized NAIP polygons (validation).

The human-readable crosswalk lives in ``crosswalk.csv``.
"""
