"""
Tests for GPU provider integrations.

Tests are split into:
  - Unit tests: validate static catalog data (no network)
  - Integration test: hit DataCrunch live API

Run:  python3 -m pytest tests/ -v
"""
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# We can't import lambda/handler.py directly because it reads S3_BUCKET,
# OPENROUTER_API_TOKEN, and boto3 at module level. Instead, we patch the
# environment and mock boto3 before importing.
# ---------------------------------------------------------------------------

# Patch env vars BEFORE handler import
_ENV_PATCH = {
    "S3_BUCKET": "test-bucket",
    "OPENROUTER_API_TOKEN": "test-token",
}


def _import_handler():
    """Import handler with mocked AWS dependencies."""
    with patch.dict("os.environ", _ENV_PATCH):
        # Mock boto3 so it doesn't need real AWS credentials
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = MagicMock()
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            # Remove cached module if previously imported
            sys.modules.pop("handler", None)
            # Add lambda/ to path
            lambda_dir = str(Path(__file__).parent.parent / "lambda")
            if lambda_dir not in sys.path:
                sys.path.insert(0, lambda_dir)
            import handler
            return handler


handler = _import_handler()


# ---------------------------------------------------------------------------
# Unit tests — static catalog providers (no network)
# ---------------------------------------------------------------------------


class TestGoogleCloudGpus(unittest.TestCase):
    """Test Google Cloud static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_google_cloud_gpus()
        self.assertEqual(len(results), 10)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_google_cloud_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_pricing_has_demand_and_spot(self):
        for gpu in handler.fetch_google_cloud_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertIn("spot_min", p)
            self.assertGreater(p["demand_min"], 0)
            self.assertGreater(p["spot_min"], 0)
            # Spot should be cheaper than on-demand
            self.assertLess(p["spot_min"], p["demand_min"])

    def test_sorted_by_name(self):
        results = handler.fetch_google_cloud_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))

    def test_known_gpus_present(self):
        names = {r["name"] for r in handler.fetch_google_cloud_gpus()}
        for expected in ["NVIDIA H100 80GB", "NVIDIA A100 80GB", "NVIDIA T4", "NVIDIA L4"]:
            self.assertIn(expected, names)


class TestCoreWeaveGpus(unittest.TestCase):
    """Test CoreWeave static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_coreweave_gpus()
        self.assertEqual(len(results), 10)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_coreweave_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_pricing_has_min_and_avg(self):
        for gpu in handler.fetch_coreweave_gpus():
            p = gpu["pricing"]
            self.assertIn("min", p)
            self.assertIn("avg", p)
            self.assertGreater(p["min"], 0)

    def test_handles_none_prices(self):
        """CoreWeave has some GPUs with only demand or only spot."""
        results = handler.fetch_coreweave_gpus()
        # HGX B300 has no demand price, GB200 NVL72 has no spot
        names_with_demand = [r["name"] for r in results if "demand_min" in r["pricing"]]
        names_with_spot = [r["name"] for r in results if "spot_min" in r["pricing"]]
        # Not all have both
        self.assertGreater(len(names_with_demand), 0)
        self.assertGreater(len(names_with_spot), 0)

    def test_sorted_by_name(self):
        results = handler.fetch_coreweave_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


class TestFluidStackGpus(unittest.TestCase):
    """Test FluidStack static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_fluidstack_gpus()
        self.assertEqual(len(results), 5)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_fluidstack_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        """FluidStack is on-demand only."""
        for gpu in handler.fetch_fluidstack_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_sorted_by_name(self):
        results = handler.fetch_fluidstack_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


class TestJarvisLabsGpus(unittest.TestCase):
    """Test Jarvis Labs static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_jarvislabs_gpus()
        self.assertEqual(len(results), 7)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_jarvislabs_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        """Jarvis Labs is on-demand only."""
        for gpu in handler.fetch_jarvislabs_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_known_gpus_present(self):
        names = {r["name"] for r in handler.fetch_jarvislabs_gpus()}
        for expected in ["NVIDIA H100 SXM", "NVIDIA A100 80GB", "NVIDIA L4"]:
            self.assertIn(expected, names)

    def test_sorted_by_name(self):
        results = handler.fetch_jarvislabs_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


# ---------------------------------------------------------------------------
# Unit tests — Batch 1 static catalog providers (no network)
# ---------------------------------------------------------------------------


class TestPaperspaceGpus(unittest.TestCase):
    """Test Paperspace static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_paperspace_gpus()
        self.assertEqual(len(results), 12)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_paperspace_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        for gpu in handler.fetch_paperspace_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_sorted_by_name(self):
        results = handler.fetch_paperspace_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))

    def test_known_gpus_present(self):
        names = {r["name"] for r in handler.fetch_paperspace_gpus()}
        for expected in ["NVIDIA H100", "NVIDIA A6000", "NVIDIA V100"]:
            self.assertIn(expected, names)


class TestSaladGpus(unittest.TestCase):
    """Test SaladCloud static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_salad_gpus()
        self.assertEqual(len(results), 11)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_salad_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        for gpu in handler.fetch_salad_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_very_low_prices(self):
        """Salad uses consumer GPUs — prices should be very low."""
        for gpu in handler.fetch_salad_gpus():
            self.assertLess(gpu["pricing"]["min"], 1.0,
                            f"{gpu['name']} price should be under $1/hr")

    def test_sorted_by_name(self):
        results = handler.fetch_salad_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


class TestCrusoeGpus(unittest.TestCase):
    """Test Crusoe static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_crusoe_gpus()
        self.assertEqual(len(results), 6)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_crusoe_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        for gpu in handler.fetch_crusoe_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_has_amd(self):
        """Crusoe offers AMD MI300X."""
        names = {r["name"] for r in handler.fetch_crusoe_gpus()}
        self.assertIn("AMD MI300X", names)

    def test_sorted_by_name(self):
        results = handler.fetch_crusoe_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


class TestHyperstackGpus(unittest.TestCase):
    """Test Hyperstack static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_hyperstack_gpus()
        self.assertEqual(len(results), 11)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_hyperstack_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        for gpu in handler.fetch_hyperstack_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_sorted_by_name(self):
        results = handler.fetch_hyperstack_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


class TestNebiusGpus(unittest.TestCase):
    """Test Nebius static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_nebius_gpus()
        self.assertEqual(len(results), 6)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_nebius_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        for gpu in handler.fetch_nebius_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_has_latest_gen(self):
        """Nebius offers B200 and B300."""
        names = {r["name"] for r in handler.fetch_nebius_gpus()}
        self.assertIn("NVIDIA B200 SXM", names)
        self.assertIn("NVIDIA B300 SXM", names)

    def test_sorted_by_name(self):
        results = handler.fetch_nebius_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


class TestDigitalOceanGpus(unittest.TestCase):
    """Test DigitalOcean static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_digitalocean_gpus()
        self.assertEqual(len(results), 4)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_digitalocean_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        for gpu in handler.fetch_digitalocean_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_sorted_by_name(self):
        results = handler.fetch_digitalocean_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


class TestOvhGpus(unittest.TestCase):
    """Test OVHcloud static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_ovh_gpus()
        self.assertEqual(len(results), 6)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_ovh_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        for gpu in handler.fetch_ovh_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_sorted_by_name(self):
        results = handler.fetch_ovh_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


class TestHetznerGpus(unittest.TestCase):
    """Test Hetzner static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_hetzner_gpus()
        self.assertEqual(len(results), 2)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_hetzner_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        for gpu in handler.fetch_hetzner_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_sorted_by_name(self):
        results = handler.fetch_hetzner_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


class TestScalewayGpus(unittest.TestCase):
    """Test Scaleway static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_scaleway_gpus()
        self.assertEqual(len(results), 5)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_scaleway_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        for gpu in handler.fetch_scaleway_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_sorted_by_name(self):
        results = handler.fetch_scaleway_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


class TestAlibabaGpus(unittest.TestCase):
    """Test Alibaba Cloud static catalog."""

    def test_returns_expected_count(self):
        results = handler.fetch_alibaba_gpus()
        self.assertEqual(len(results), 4)

    def test_all_have_required_fields(self):
        for gpu in handler.fetch_alibaba_gpus():
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

    def test_demand_only_no_spot(self):
        for gpu in handler.fetch_alibaba_gpus():
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertNotIn("spot_min", p)

    def test_sorted_by_name(self):
        results = handler.fetch_alibaba_gpus()
        names = [r["name"] for r in results]
        self.assertEqual(names, sorted(names))


# ---------------------------------------------------------------------------
# Unit test — DataCrunch with mocked API response
# ---------------------------------------------------------------------------


class TestDataCrunchGpusMocked(unittest.TestCase):
    """Test DataCrunch fetch logic with mocked API response."""

    MOCK_RESPONSE = [
        {
            "model": "H100",
            "name": "H100 SXM5 80GB",
            "gpu": {"number_of_gpus": 1},
            "gpu_memory": {"size_in_gigabytes": 80},
            "price_per_hour": "3.25",
            "spot_price": "1.14",
        },
        {
            "model": "H100",
            "name": "H100 SXM5 80GB",
            "gpu": {"number_of_gpus": 2},  # multi-GPU — should be skipped
            "gpu_memory": {"size_in_gigabytes": 160},
            "price_per_hour": "6.50",
            "spot_price": "2.28",
        },
        {
            "model": "A100 80GB",
            "name": "A100 SXM4 80GB",
            "gpu": {"number_of_gpus": 1},
            "gpu_memory": {"size_in_gigabytes": 80},
            "price_per_hour": "1.79",
            "spot_price": "0.63",
        },
    ]

    @patch.object(handler, "http_get", return_value=MOCK_RESPONSE)
    def test_filters_multi_gpu(self, mock_get):
        results = handler.fetch_datacrunch_gpus()
        # Should only have 2 (single-GPU entries), not the 2x H100
        self.assertEqual(len(results), 2)

    @patch.object(handler, "http_get", return_value=MOCK_RESPONSE)
    def test_pricing_structure(self, mock_get):
        results = handler.fetch_datacrunch_gpus()
        for gpu in results:
            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertIn("spot_min", p)
            self.assertGreater(p["demand_min"], 0)
            self.assertGreater(p["spot_min"], 0)
            self.assertLess(p["spot_min"], p["demand_min"])

    @patch.object(handler, "http_get", return_value=MOCK_RESPONSE)
    def test_vram_extracted(self, mock_get):
        results = handler.fetch_datacrunch_gpus()
        for gpu in results:
            self.assertGreater(gpu["vram_gb"], 0)

    @patch.object(handler, "http_get", return_value=None)
    def test_handles_api_failure(self, mock_get):
        results = handler.fetch_datacrunch_gpus()
        self.assertEqual(results, [])

    @patch.object(handler, "http_get", return_value=[])
    def test_handles_empty_response(self, mock_get):
        results = handler.fetch_datacrunch_gpus()
        self.assertEqual(results, [])

    @patch.object(handler, "http_get", return_value="unexpected")
    def test_handles_unexpected_type(self, mock_get):
        results = handler.fetch_datacrunch_gpus()
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# Integration test — DataCrunch live API (skipped if offline)
# ---------------------------------------------------------------------------


class TestDataCrunchLiveAPI(unittest.TestCase):
    """Integration test hitting the real DataCrunch API."""

    def test_live_api_returns_data(self):
        """Verify DataCrunch API returns GPU data without auth."""
        import urllib.request

        try:
            req = urllib.request.Request(
                handler.DATACRUNCH_API_URL,
                headers={"User-Agent": "dame-test/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            self.skipTest(f"DataCrunch API unreachable: {e}")

        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0, "API returned empty list")

        # Verify structure of first entry
        entry = data[0]
        self.assertIn("model", entry)
        self.assertIn("price_per_hour", entry)
        self.assertIn("gpu", entry)
        self.assertIn("gpu_memory", entry)

    def test_fetch_function_returns_valid_data(self):
        """End-to-end test of fetch_datacrunch_gpus() against live API."""
        results = handler.fetch_datacrunch_gpus()
        if not results:
            self.skipTest("DataCrunch API returned no data (may be offline)")

        self.assertGreater(len(results), 5, "Expected at least 5 GPU types")

        for gpu in results:
            self.assertIn("name", gpu)
            self.assertIn("vram_gb", gpu)
            self.assertIn("pricing", gpu)
            self.assertGreater(gpu["vram_gb"], 0)

            p = gpu["pricing"]
            self.assertIn("demand_min", p)
            self.assertIn("spot_min", p)
            self.assertGreater(p["demand_min"], 0)
            self.assertGreater(p["spot_min"], 0)


# ---------------------------------------------------------------------------
# Cross-provider consistency tests
# ---------------------------------------------------------------------------


class TestProviderConsistency(unittest.TestCase):
    """Verify all providers return data in a consistent schema."""

    MOCK_DATACRUNCH = [
        {
            "model": "H100", "name": "H100 SXM5 80GB",
            "gpu": {"number_of_gpus": 1},
            "gpu_memory": {"size_in_gigabytes": 80},
            "price_per_hour": "3.25", "spot_price": "1.14",
        },
        {
            "model": "A100 80GB", "name": "A100 SXM4 80GB",
            "gpu": {"number_of_gpus": 1},
            "gpu_memory": {"size_in_gigabytes": 80},
            "price_per_hour": "1.79", "spot_price": "0.63",
        },
    ]

    PROVIDERS = [
        ("Google Cloud", handler.fetch_google_cloud_gpus),
        ("CoreWeave", handler.fetch_coreweave_gpus),
        ("FluidStack", handler.fetch_fluidstack_gpus),
        ("Jarvis Labs", handler.fetch_jarvislabs_gpus),
        ("Paperspace", handler.fetch_paperspace_gpus),
        ("SaladCloud", handler.fetch_salad_gpus),
        ("Crusoe", handler.fetch_crusoe_gpus),
        ("Hyperstack", handler.fetch_hyperstack_gpus),
        ("Nebius", handler.fetch_nebius_gpus),
        ("DigitalOcean", handler.fetch_digitalocean_gpus),
        ("OVHcloud", handler.fetch_ovh_gpus),
        ("Hetzner", handler.fetch_hetzner_gpus),
        ("Scaleway", handler.fetch_scaleway_gpus),
        ("Alibaba Cloud", handler.fetch_alibaba_gpus),
    ]

    def _datacrunch_mocked(self):
        """Return DataCrunch results using mocked API data."""
        with patch.object(handler, "http_get", return_value=self.MOCK_DATACRUNCH):
            return handler.fetch_datacrunch_gpus()

    def _all_providers(self):
        """All providers including DataCrunch (mocked)."""
        return self.PROVIDERS + [("DataCrunch", self._datacrunch_mocked)]

    def test_all_return_lists(self):
        for name, fn in self._all_providers():
            with self.subTest(provider=name):
                result = fn() if not callable(getattr(fn, '__self__', None)) else fn()
                self.assertIsInstance(result, list)
                self.assertGreater(len(result), 0)

    def test_all_have_consistent_schema(self):
        for name, fn in self._all_providers():
            with self.subTest(provider=name):
                for gpu in fn():
                    self.assertIsInstance(gpu["name"], str)
                    self.assertIsInstance(gpu["vram_gb"], (int, float))
                    self.assertIsInstance(gpu["pricing"], dict)
                    self.assertIn("min", gpu["pricing"])

    def test_all_prices_reasonable(self):
        """Sanity check: GPU prices should be between $0.01 and $100/hr."""
        for name, fn in self._all_providers():
            with self.subTest(provider=name):
                for gpu in fn():
                    p = gpu["pricing"]
                    min_price = p["min"]
                    self.assertGreater(min_price, 0.01, f"{gpu['name']} price too low")
                    self.assertLess(min_price, 100.0, f"{gpu['name']} price too high")

    def test_all_vram_reasonable(self):
        """Sanity check: VRAM should be between 4GB and 512GB."""
        for name, fn in self._all_providers():
            with self.subTest(provider=name):
                for gpu in fn():
                    vram = gpu["vram_gb"]
                    self.assertGreaterEqual(vram, 4, f"{gpu['name']} VRAM too low")
                    self.assertLessEqual(vram, 512, f"{gpu['name']} VRAM too high")

    def test_all_sorted_by_name(self):
        for name, fn in self._all_providers():
            with self.subTest(provider=name):
                results = fn()
                names = [r["name"] for r in results]
                self.assertEqual(names, sorted(names))


if __name__ == "__main__":
    unittest.main()
