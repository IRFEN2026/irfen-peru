"""Offline tests for the Casma Gate A raw-capture mechanism.

They simulate the MINAM service with deliberately irregular JSON bytes
(odd whitespace, key order, unicode escapes) so any re-serialization of the
archived raw bodies would be detected. No network access is used. Gate B is
never modified or established by this mechanism.
"""
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/recover_phase2_casma_minam_n7.py"
CONTRACT = REPO / "config/phase2_casma_minam_n7_recovery_contract_v0_1.json"
WORKFLOW = REPO / ".github/workflows/phase2-casma-n7-source-gap.yml"
ADJUDICATION = REPO / "site/data/phase2/source_assessments/casma_minam_recovery_gate_adjudication_v0_1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("casma_capture_mechanism", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def metadata_bytes(wkid=32718, latest=32718, map_wkid=4326):
    # Mirrors the frozen MINAM layer 1 resource (ArcGIS 10.71): no top-level
    # spatialReference, extent.spatialReference 4326 (map SR) and
    # sourceSpatialReference 32718 (storage CRS of the source dataset).
    fields = ",".join(
        '{"name": "%s"}' % name for name in contract()["source"]["output_fields"]
    )
    return (
        '{ "currentVersion":10.71, "geometryType":"esriGeometryPolygon" ,\n'
        '  "extent":{"xmin":-79.2,"ymin":-10.2,"xmax":-77,"ymax":-8.4,"spatialReference":{"wkid":%d,"latestWkid":%d}},\n'
        '  "sourceSpatialReference":{"wkid":%d,"latestWkid":%d},\r\n'
        '  "supportedQueryFormats":"JSON, geoJSON",\n'
        '  "fields":[%s] }' % (map_wkid, map_wkid, wkid, latest, fields)
    ).encode("utf-8")


def geojson_bytes(unit, objectid, name=None):
    name = unit["name"] if name is None else name
    # Irregular spacing, non-sorted keys and \u escapes on purpose.
    return (
        '{"type":"FeatureCollection","features":[ {"type":"Feature",'
        '"geometry":{"coordinates":[[[-78.6,-9.8],[-77.5,-9.8],[-77.5,-8.8],[-78.6,-9.8]]],"type":"Polygon"},'
        '"properties":{"OBJECTID":%d,"CODIGO":"%s","NIVEL":7,"NIVEL7":"%s",'
        '"NOMB_UH_N7":%s,"AREA_KM2":%s}} ]  }\n'
        % (objectid, unit["code"], unit["code"], json.dumps(name), repr(unit["area_km2"] + 0.01234))
    ).encode("utf-8")


def native_bytes(unit, objectid, wkid=32718, code=None, extra=""):
    code = unit["code"] if code is None else code
    return (
        '{"displayFieldName":"NOMB_UH_N7","spatialReference":{"wkid":%d,"latestWkid":%d},'
        '"features":[{"attributes":{"OBJECTID":%d,"CODIGO":"%s","NIVEL7":"%s","NOMB_UH_N7":"R\\u00edo"},'
        '"geometry":{"rings":[[[800000.125,8900000.5],[810000,8900000],[810000,8910000],[800000.125,8900000.5]]]}}]%s}'
        % (wkid, wkid, objectid, code, code, extra)
    ).encode("utf-8")


class FakeService:
    def __init__(self, module, overrides=None):
        self.module = module
        self.overrides = overrides or {}
        self.bodies = {}
        c = contract()
        self.bodies[c["source"]["metadata_url"]] = metadata_bytes()
        for i, unit in enumerate(c["units"], start=1):
            self.bodies[module.query_url(c, unit["code"])] = geojson_bytes(unit, i)
            self.bodies[module.native_query_url(c, unit["code"], 32718)] = native_bytes(unit, i)
        self.bodies.update(self.overrides)

    def __call__(self, url, *, accept, max_bytes=15_000_000):
        body = self.bodies[url]
        if isinstance(body, Exception):
            raise body
        return body, {
            "requested_url": url,
            "final_url": url,
            "http_status": 200,
            "headers": {"Content-Type": "application/json"},
            "retrieved_at_utc": "2026-09-30T00:00:00Z",
            "body_size_bytes": len(body),
            "body_sha256": hashlib.sha256(body).hexdigest(),
        }


class CasmaCaptureMechanismTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.tmp = Path(tempfile.mkdtemp())
        self.module.ROOT = self.tmp
        self.contract = contract()
        self.outputs = self.contract["outputs"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_capture(self, overrides=None):
        service = FakeService(self.module, overrides)
        self.module.fetch_response = service
        return service, self.module.refresh(self.contract)

    def test_raw_bodies_are_archived_byte_for_byte(self):
        service, manifest = self.run_capture()
        archive = self.tmp / self.outputs["archive_root"]
        meta = self.tmp / self.outputs["metadata_archive_path"]
        self.assertEqual(meta.read_bytes(), service.bodies[self.contract["source"]["metadata_url"]])
        for unit in self.contract["units"]:
            code = unit["code"]
            self.assertEqual(
                (archive / f"{code}.geojson").read_bytes(),
                service.bodies[self.module.query_url(self.contract, code)],
            )
            self.assertEqual(
                (archive / f"{code}.native.json").read_bytes(),
                service.bodies[self.module.native_query_url(self.contract, code, 32718)],
            )
        self.assertEqual(manifest["capture_format_version"], 3)
        self.assertEqual(manifest["feature_count"], 9)

    def test_native_query_requests_declared_storage_crs_explicitly(self):
        url = self.module.native_query_url(self.contract, "1375961", 32718)
        self.assertIn("f=json", url)
        self.assertIn("outSR=32718", url)
        self.assertNotIn("outSR=4326", url)
        self.assertNotIn("datumTransformation", url)
        self.assertIn("1375961", url)

    def test_native_query_refuses_map_spatial_reference(self):
        with self.assertRaisesRegex(self.module.RecoveryError, "NATIVE_OUTSR_NOT_DECLARED_SOURCE"):
            self.module.native_query_url(self.contract, "1375961", 4326)

    def test_manifest_hashes_and_http_provenance_match_bytes(self):
        service, manifest = self.run_capture()
        for row in manifest["features"]:
            raw = (self.tmp / row["raw_archive_path"]).read_bytes()
            native = (self.tmp / row["native_archive_path"]).read_bytes()
            self.assertEqual(row["raw_response_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(row["native_response_sha256"], hashlib.sha256(native).hexdigest())
            self.assertEqual(row["raw_response_http"]["body_sha256"], row["raw_response_sha256"])
            self.assertEqual(row["native_response_http"]["body_sha256"], row["native_response_sha256"])
            self.assertEqual(row["native_spatial_reference"]["wkid"], 32718)
        self.assertEqual(
            manifest["metadata_http"]["body_sha256"], manifest["metadata_sha256"]
        )

    def test_sha256sums_is_verifiable_with_coreutils(self):
        self.run_capture()
        archive = self.tmp / self.outputs["archive_root"]
        lines = (archive / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1 + 9 * 2)
        for line in lines:
            self.assertRegex(line, r"^[0-9a-f]{64}  [^/]+$")
        if shutil.which("sha256sum"):
            subprocess.run(
                ["sha256sum", "--strict", "-c", "SHA256SUMS"],
                cwd=archive, check=True, capture_output=True,
            )

    def test_offline_verify_detects_single_byte_tampering(self):
        self.run_capture()
        self.module.verify_existing(self.contract)
        archive = self.tmp / self.outputs["archive_root"]
        for name, message in [
            ("1375964.native.json", "NATIVE_RESPONSE_HASH_DRIFT"),
            ("1375964.geojson", "RAW_RESPONSE_HASH_DRIFT"),
        ]:
            with self.subTest(name=name):
                path = archive / name
                original = path.read_bytes()
                path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
                with self.assertRaisesRegex(self.module.RecoveryError, message):
                    self.module.verify_existing(self.contract)
                path.write_bytes(original)
        sums = archive / "SHA256SUMS"
        sums.write_text(sums.read_text(encoding="utf-8") + "0" * 64 + "  extra\n", encoding="utf-8")
        with self.assertRaisesRegex(self.module.RecoveryError, "SHA256SUMS_HASH_DRIFT"):
            self.module.verify_existing(self.contract)

    def test_any_failure_writes_nothing(self):
        units = self.contract["units"]
        bad = units[4]
        cases = {
            "NATIVE_WKID_DRIFT": {self.module.native_query_url(self.contract, bad["code"], 32718): native_bytes(bad, 5, wkid=4326)},
            "NATIVE_CODE_MISMATCH": {self.module.native_query_url(self.contract, bad["code"], 32718): native_bytes(bad, 5, code="1375961")},
            "NATIVE_TRANSFER_LIMIT_EXCEEDED": {self.module.native_query_url(self.contract, bad["code"], 32718): native_bytes(bad, 5, extra=',"exceededTransferLimit":true')},
            "NATIVE_GEOJSON_OBJECTID_MISMATCH": {self.module.native_query_url(self.contract, bad["code"], 32718): native_bytes(bad, 99)},
            "SOURCE_FETCH_FAILED": {self.module.native_query_url(self.contract, units[8]["code"], 32718): self.module.SourceUnavailable("SOURCE_FETCH_FAILED URLError")},
        }
        for message, override in cases.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(self.module.RecoveryError, message):
                    self.run_capture(override)
                self.assertFalse(any(self.tmp.rglob("*")), f"partial archive written for {message}")

    def test_gate_b_is_not_modified_or_established(self):
        before = ADJUDICATION.read_bytes()
        _, manifest = self.run_capture()
        self.assertEqual(ADJUDICATION.read_bytes(), before)
        self.assertEqual(manifest["gate_b_lineage_equivalence"], "NOT_ESTABLISHED")
        self.assertFalse(manifest["historical_geometry_equivalence_to_Uh_pfas100"])
        self.assertFalse(manifest["map_publication_authorized"])
        for row in manifest["features"]:
            self.assertEqual(row["gate_b_lineage_equivalence"], "NOT_ESTABLISHED")
            self.assertFalse(row["historical_geometry_equivalence_to_Uh_pfas100"])
        geometry = json.loads((self.tmp / self.outputs["geometry_path"]).read_text(encoding="utf-8"))
        self.assertEqual(geometry["properties"]["gate_b_lineage_equivalence"], "NOT_ESTABLISHED")
        self.assertFalse(geometry["properties"]["map_eligible_as_research_context"])

    def test_legacy_capture_without_native_bytes_is_rejected(self):
        _, manifest = self.run_capture()
        path = self.tmp / self.outputs["manifest_path"]
        manifest.pop("capture_format_version")
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(self.module.RecoveryError, "UNSUPPORTED_CAPTURE_FORMAT"):
            self.module.verify_existing(self.contract)


    # --- Regression: first real Gate A run on PR #344 (2026-09-30) failed with
    # NATIVE_WKID_DRIFT because a MapServer query without outSR returns the map
    # spatial reference (4326), not the layer's storage CRS (32718).
    OBSERVED_4326_NATIVE = (
        '{"displayFieldName":"NOMB_UH_N7","spatialReference":{"wkid":4326,"latestWkid":4326},'
        '"features":[{"attributes":{"OBJECTID":1,"CODIGO":"1375961","NIVEL7":"1375961"},'
        '"geometry":{"rings":[[[-78.142525993906602,-9.2687765987241661],[-78.1,-9.2],'
        '[-78.0,-9.3],[-78.142525993906602,-9.2687765987241661]]]}}]}'
    ).encode("utf-8")

    def test_observed_map_sr_native_response_still_fails_closed(self):
        url = self.module.native_query_url(self.contract, "1375961", 32718)
        with self.assertRaisesRegex(self.module.RecoveryError, r"NATIVE_WKID_DRIFT code=1375961"):
            self.run_capture({url: self.OBSERVED_4326_NATIVE})
        self.assertFalse(any(self.tmp.rglob("*")))

    def test_metadata_source_sr_drift_fails_closed(self):
        meta_url = self.contract["source"]["metadata_url"]
        for body, message in [
            (metadata_bytes(wkid=4326, latest=4326), "SOURCE_WKID_DRIFT"),
            (metadata_bytes(latest=4326), "SOURCE_LATEST_WKID_DRIFT"),
        ]:
            with self.subTest(message=message):
                with self.assertRaisesRegex(self.module.RecoveryError, message):
                    self.run_capture({meta_url: body})
                self.assertFalse(any(self.tmp.rglob("*")))

    def test_manifest_records_crs_provenance_without_accepting_map_sr(self):
        _, manifest = self.run_capture()
        crs = manifest["crs_provenance"]
        self.assertEqual(crs["layer_source_spatial_reference"]["wkid"], 32718)
        self.assertIsNone(crs["layer_top_level_spatial_reference"])
        self.assertEqual(crs["layer_extent_spatial_reference"]["wkid"], 4326)
        self.assertEqual(crs["native_request_outSR"], 32718)
        self.assertFalse(crs["map_spatial_reference_accepted_as_native"])
        self.assertFalse(crs["datum_transformation_requested"])
        for row in manifest["features"]:
            self.assertIn("outSR=32718", row["native_query_url"])
            self.assertEqual(row["native_spatial_reference"]["wkid"], 32718)

    def test_offline_verify_rejects_manifest_claiming_map_sr_as_native(self):
        _, manifest = self.run_capture()
        path = self.tmp / self.outputs["manifest_path"]
        for mutate, message in [
            (lambda m: m["features"][0].__setitem__("native_spatial_reference", {"wkid": 4326, "latestWkid": 4326}), "ROW_NATIVE_WKID_DRIFT"),
            (lambda m: m["crs_provenance"].__setitem__("map_spatial_reference_accepted_as_native", True), "MAP_SR_ACCEPTED_AS_NATIVE"),
            (lambda m: m["crs_provenance"].__setitem__("native_request_outSR", 4326), "NATIVE_OUTSR_PROVENANCE_DRIFT"),
        ]:
            with self.subTest(message=message):
                doc = json.loads(json.dumps(manifest))
                mutate(doc)
                path.write_text(json.dumps(doc), encoding="utf-8")
                with self.assertRaisesRegex(self.module.RecoveryError, message):
                    self.module.verify_existing(self.contract)


class CasmaCaptureWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_commit_is_bootstrap_only_same_repo_and_never_to_main(self):
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", self.text)
        self.assertIn("steps.mode.outputs.bootstrap == 'true' && github.event_name == 'pull_request'", self.text)
        pushes = re.findall(r"^\s*git push .*$", self.text, flags=re.M)
        self.assertEqual([p.strip() for p in pushes], ['git push origin "HEAD:refs/heads/$HEAD_REF"'])
        self.assertIn("HEAD_REF: ${{ github.event.pull_request.head.ref }}", self.text)
        self.assertIn('"$HEAD_REF" == "main"', self.text)
        self.assertIn('"$HEAD_REF" == "$DEFAULT_BRANCH"', self.text)
        self.assertIn("REFUSING_TO_PUSH_TO_DEFAULT_BRANCH", self.text)
        executable = "\n".join(
            line for line in self.text.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertNotRegex(executable, r"(?i)\bgh pr merge\b|\bgit merge\b|HEAD:main|refs/heads/main")

    def test_default_branch_guard_refuses_main(self):
        block = self.text.split("Commit the one-shot Gate A capture", 1)[1].split("run: |", 1)[1]
        guard = block.split("git config", 1)[0]
        script = "set -euo pipefail\n" + "\n".join(line.strip() for line in guard.splitlines())
        if not shutil.which("bash"):
            self.skipTest("bash not available")
        for head, expected in [("main", 1), ("", 1), ("trunk", 1), ("phase2-casma-feature", 0)]:
            with self.subTest(head=head):
                env = {"HEAD_REF": head, "DEFAULT_BRANCH": "trunk", "PATH": "/usr/bin:/bin"}
                result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_frozen_capture_is_replayed_offline_and_checked_with_coreutils(self):
        self.assertIn("sha256sum --strict -c SHA256SUMS", self.text)
        self.assertIn('git diff --exit-code -- "$CASMA_ARCHIVE" "$CASMA_GEOMETRY" "$CASMA_MANIFEST"', self.text)
        self.assertIn("data/phase2/source_archive/casma_minam_n7/**", self.text)


class CasmaGateCTopologyTests(unittest.TestCase):
    """Fail-closed Gate C checks on the immutable MINAM Gate A capture.

    These tests do not establish historical equivalence to Uh_pfas100 and do
    not authorize map publication. They only test the internal topology of the
    frozen CURRENT institutional descendant in its declared storage CRS.
    """

    ARCHIVE = REPO / "data/phase2/source_archive/casma_minam_n7"
    CODES = tuple(f"137596{i}" for i in range(1, 10))
    EPS = 1e-7

    @classmethod
    def setUpClass(cls):
        cls.polygons = {}
        cls.attributes = {}
        for code in cls.CODES:
            doc = json.loads((cls.ARCHIVE / f"{code}.native.json").read_text(encoding="utf-8"))
            assert doc["spatialReference"]["wkid"] == 32718
            assert len(doc["features"]) == 1
            feature = doc["features"][0]
            assert feature["attributes"]["CODIGO"] == code
            rings = feature["geometry"]["rings"]
            assert len(rings) == 1
            cls.polygons[code] = [tuple(map(float, p)) for p in rings[0]]
            cls.attributes[code] = feature["attributes"]

    @staticmethod
    def _bbox(ring):
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return min(xs), min(ys), max(xs), max(ys)

    @classmethod
    def _bbox_disjoint(cls, a, b):
        A, B = cls._bbox(a), cls._bbox(b)
        return A[2] < B[0] or B[2] < A[0] or A[3] < B[1] or B[3] < A[1]

    @staticmethod
    def _orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    @classmethod
    def _on_segment(cls, a, b, p):
        if abs(cls._orient(a, b, p)) > cls.EPS:
            return False
        return (
            min(a[0], b[0]) - cls.EPS <= p[0] <= max(a[0], b[0]) + cls.EPS
            and min(a[1], b[1]) - cls.EPS <= p[1] <= max(a[1], b[1]) + cls.EPS
        )

    @classmethod
    def _proper_intersection(cls, a, b, c, d):
        o1, o2 = cls._orient(a, b, c), cls._orient(a, b, d)
        o3, o4 = cls._orient(c, d, a), cls._orient(c, d, b)
        return (
            ((o1 > cls.EPS and o2 < -cls.EPS) or (o1 < -cls.EPS and o2 > cls.EPS))
            and ((o3 > cls.EPS and o4 < -cls.EPS) or (o3 < -cls.EPS and o4 > cls.EPS))
        )

    @classmethod
    def _point_state(cls, p, ring):
        # 1 interior, 0 boundary, -1 exterior.
        for i in range(len(ring) - 1):
            if cls._on_segment(ring[i], ring[i + 1], p):
                return 0
        inside = False
        x, y = p
        j = len(ring) - 2
        for i in range(len(ring) - 1):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / (yj - yi) + xi
            ):
                inside = not inside
            j = i
        return 1 if inside else -1

    @staticmethod
    def _shoelace_km2(ring):
        twice = 0.0
        for a, b in zip(ring, ring[1:]):
            twice += a[0] * b[1] - b[0] * a[1]
        return abs(twice) / 2.0 / 1_000_000.0

    def test_all_nine_native_polygons_are_closed_nonzero_single_rings(self):
        self.assertEqual(set(self.polygons), set(self.CODES))
        for code, ring in self.polygons.items():
            with self.subTest(code=code):
                self.assertGreaterEqual(len(ring), 4)
                self.assertEqual(ring[0], ring[-1])
                self.assertGreater(self._shoelace_km2(ring), 0.0)

    def test_no_proper_self_crossings(self):
        for code, ring in self.polygons.items():
            with self.subTest(code=code):
                for i in range(len(ring) - 1):
                    a, b = ring[i], ring[i + 1]
                    ab = (
                        min(a[0], b[0]), min(a[1], b[1]),
                        max(a[0], b[0]), max(a[1], b[1]),
                    )
                    for j in range(i + 1, len(ring) - 1):
                        if j == i + 1 or (i == 0 and j == len(ring) - 2):
                            continue
                        c, d = ring[j], ring[j + 1]
                        if (
                            ab[2] < min(c[0], d[0]) or max(c[0], d[0]) < ab[0]
                            or ab[3] < min(c[1], d[1]) or max(c[1], d[1]) < ab[1]
                        ):
                            continue
                        self.assertFalse(
                            self._proper_intersection(a, b, c, d),
                            f"proper self-crossing in {code}: segments {i}/{j}",
                        )

    def test_no_pairwise_area_overlap(self):
        codes = list(self.CODES)
        for left_i, left_code in enumerate(codes):
            left = self.polygons[left_code]
            for right_code in codes[left_i + 1:]:
                right = self.polygons[right_code]
                if self._bbox_disjoint(left, right):
                    continue
                with self.subTest(left=left_code, right=right_code):
                    # Boundary crossings would imply positive-area overlap for
                    # these simple single-ring polygons.
                    for i in range(len(left) - 1):
                        a, b = left[i], left[i + 1]
                        ab = (
                            min(a[0], b[0]), min(a[1], b[1]),
                            max(a[0], b[0]), max(a[1], b[1]),
                        )
                        for j in range(len(right) - 1):
                            c, d = right[j], right[j + 1]
                            if (
                                ab[2] < min(c[0], d[0]) or max(c[0], d[0]) < ab[0]
                                or ab[3] < min(c[1], d[1]) or max(c[1], d[1]) < ab[1]
                            ):
                                continue
                            self.assertFalse(
                                self._proper_intersection(a, b, c, d),
                                f"proper crossing {left_code}/{right_code}: {i}/{j}",
                            )
                    # If boundaries do not cross, overlap can only remain by
                    # containment. One non-boundary vertex is sufficient.
                    for candidate, container, label in (
                        (left, right, f"{left_code} inside {right_code}"),
                        (right, left, f"{right_code} inside {left_code}"),
                    ):
                        state = None
                        for p in candidate[:-1]:
                            state = self._point_state(p, container)
                            if state != 0:
                                break
                        self.assertNotEqual(state, 1, label)

    def test_shared_edges_cancel_to_one_closed_outer_boundary(self):
        # The nine polygons come from one frozen source coverage. Exact shared
        # source edges must therefore occur twice; outer edges once. A single
        # degree-2 unmatched component rules out enclosed internal gaps under
        # the source vertex topology without inventing a parent geometry.
        edge_counts = {}
        for code, ring in self.polygons.items():
            for a, b in zip(ring, ring[1:]):
                edge = tuple(sorted((a, b)))
                row = edge_counts.setdefault(edge, {"count": 0, "owners": set()})
                row["count"] += 1
                row["owners"].add(code)

        multiplicities = {row["count"] for row in edge_counts.values()}
        self.assertTrue(multiplicities.issubset({1, 2}), multiplicities)
        self.assertIn(2, multiplicities, "no shared internal boundaries found")

        unmatched = [edge for edge, row in edge_counts.items() if row["count"] == 1]
        adjacency = {}
        for a, b in unmatched:
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
        self.assertTrue(adjacency)
        self.assertTrue(all(len(neighbors) == 2 for neighbors in adjacency.values()))

        seen = set()
        components = 0
        for start in adjacency:
            if start in seen:
                continue
            components += 1
            stack = [start]
            while stack:
                vertex = stack.pop()
                if vertex in seen:
                    continue
                seen.add(vertex)
                stack.extend(adjacency[vertex] - seen)
        self.assertEqual(components, 1, "unmatched boundary contains internal hole/gap loops")

    def test_area_fields_are_not_substituted_for_geometric_or_historical_equivalence(self):
        geometric_sum = sum(self._shoelace_km2(r) for r in self.polygons.values())
        area_km2_sum = sum(float(self.attributes[c]["AREA_KM2"]) for c in self.CODES)
        area_final_sum = sum(float(self.attributes[c]["AREA_FINAL"]) for c in self.CODES)

        # Frozen-source observations only. The three area notions differ and
        # therefore must stay explicit; none proves Uh_pfas100 equivalence.
        self.assertAlmostEqual(geometric_sum, 2990.689973229004, places=6)
        self.assertAlmostEqual(area_km2_sum, 2989.8386, places=6)
        self.assertAlmostEqual(area_final_sum, 2973.9707, places=6)
        self.assertGreater(abs(geometric_sum - area_final_sum), 10.0)

        gate = json.loads(ADJUDICATION.read_text(encoding="utf-8"))
        self.assertEqual(gate["gate_b_lineage_equivalence"]["current_status"], "NOT_ESTABLISHED")
        self.assertFalse(gate["gate_b_lineage_equivalence"]["historical_geometry_equivalence_to_Uh_pfas100"])
        self.assertFalse(gate["gate_c_topology_map"]["map_publication_authorized"])



if __name__ == "__main__":
    unittest.main()
