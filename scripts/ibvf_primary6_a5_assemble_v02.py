#!/usr/bin/env python3
"""Pure implementation correction for GeoJSON Feature vs FeatureCollection containers.
No scientific rule, window, feature, threshold, sensor response, or territorial outcome is changed.
"""
import ibvf_primary6_a5_assemble_v01 as base


def selected_feature(geojson, selector):
    if geojson.get("type") == "Feature":
        feats = [geojson]
    else:
        feats = geojson.get("features", [])
    if selector:
        prop, value = selector["property"], selector["value"]
        feats = [f for f in feats if (f.get("properties") or {}).get(prop) == value]
    if len(feats) != 1:
        raise RuntimeError(f"Expected one selected geometry feature, got {len(feats)}")
    return feats[0]


base.selected_feature = selected_feature

if __name__ == "__main__":
    base.main()
