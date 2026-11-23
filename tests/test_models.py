#!/usr/bin/env python3
"""Tests for models module."""
# noqa: E402

import importlib.util
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "models", Path(__file__).parents[1] / "models.py"
)
models = importlib.util.module_from_spec(_SPEC)
sys.modules["models"] = models
_SPEC.loader.exec_module(models)

#--------------------------------------------------
# Test doubles
#--------------------------------------------------


class FakeTransport:
    """Scripted stand-in for HttpTransport returning bodies by URL fragment."""

    def __init__(self, *, pages):
        self._pages = dict(pages)
        self.calls = []

    def fetch_text(self, *, url, timeout):
        """Record the call and return or raise the matching scripted body."""
        self.calls.append(url)
        for key, value in self._pages.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise urllib.error.URLError("not found")

#--------------------------------------------------
# Fixtures
#--------------------------------------------------

SAMPLE_CATALOG = {
    "openai": {
        "id": "openai",
        "name": "OpenAI",
        "models": {
            "gpt-4o": {
                "id": "gpt-4o",
                "name": "GPT-4o",
                "description": "Flagship model",
                "attachment": True,
                "reasoning": False,
                "tool_call": True,
                "structured_output": True,
                "release_date": "2024-05-13",
                "last_updated": "2024-11-20",
                "limit": {"context": 128000, "output": 16384},
                "cost": {"input": 2.5, "output": 10},
            },
            "gpt-4o-mini": {
                "id": "gpt-4o-mini",
                "name": "GPT-4o Mini",
                "description": "Affordable small model",
                "attachment": True,
                "reasoning": False,
                "tool_call": True,
                "structured_output": True,
                "release_date": "2024-07-18",
                "last_updated": "2024-10-01",
                "limit": {"context": 128000, "output": 16384},
                "cost": {"input": 0.15, "output": 0.6},
            },
        },
    },
    "anthropic": {
        "id": "anthropic",
        "name": "Anthropic",
        "models": {
            "claude-opus-4": {
                "id": "claude-opus-4",
                "name": "Claude Opus 4",
                "description": "Most capable model",
                "attachment": True,
                "reasoning": True,
                "tool_call": True,
                "structured_output": True,
                "release_date": "2025-06-26",
                "last_updated": "2025-07-15",
                "limit": {"context": 200000, "output": 32000},
                "cost": {"input": 15, "output": 75},
            },
        },
    },
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek",
        "models": {
            "deepseek-v3": {
                "id": "deepseek-v3",
                "name": "DeepSeek V3",
                "description": "Open weight model",
                "attachment": False,
                "reasoning": False,
                "tool_call": True,
                "structured_output": False,
                "release_date": "2024-12-26",
                "last_updated": "2025-03-24",
                "limit": {"context": 64000, "output": 8192},
                "cost": {"input": 0.27, "output": 1.1},
            },
            "deepseek-r1": {
                "id": "deepseek-r1",
                "name": "DeepSeek R1",
                "description": "Reasoning model",
                "attachment": False,
                "reasoning": True,
                "tool_call": False,
                "structured_output": False,
                "release_date": "2025-01-20",
                "last_updated": "2025-02-25",
                "limit": {"context": 64000, "output": 8192},
                "cost": {"input": 0.55, "output": 2.19},
            },
        },
    },
}

SAMPLE_MODELS = [
    {
        "provider": "OpenAI", "provider_id": "openai", "id": "gpt-4o",
        "name": "GPT-4o", "description": "Flagship model",
        "input_cost": 2.5, "output_cost": 10, "total_cost": 12.5,
        "context": 128000, "output_limit": 16384,
        "reasoning": False, "tool_call": True, "structured_output": True,
        "attachment": True, "open_weights": False, "status": "",
        "release_date": "2024-05-13", "updated_date": "2024-11-20",
    },
    {
        "provider": "OpenAI", "provider_id": "openai", "id": "gpt-4o-mini",
        "name": "GPT-4o Mini", "description": "Affordable small model",
        "input_cost": 0.15, "output_cost": 0.6, "total_cost": 0.75,
        "context": 128000, "output_limit": 16384,
        "reasoning": False, "tool_call": True, "structured_output": True,
        "attachment": True, "open_weights": False, "status": "",
        "release_date": "2024-07-18", "updated_date": "2024-10-01",
    },
    {
        "provider": "Anthropic", "provider_id": "anthropic", "id": "claude-opus-4",
        "name": "Claude Opus 4", "description": "Most capable model",
        "input_cost": 15, "output_cost": 75, "total_cost": 90,
        "context": 200000, "output_limit": 32000,
        "reasoning": True, "tool_call": True, "structured_output": True,
        "attachment": True, "open_weights": False, "status": "",
        "release_date": "2025-06-26", "updated_date": "2025-07-15",
    },
    {
        "provider": "DeepSeek", "provider_id": "deepseek", "id": "deepseek-v3",
        "name": "DeepSeek V3", "description": "Open weight model",
        "input_cost": 0.27, "output_cost": 1.1, "total_cost": 1.37,
        "context": 64000, "output_limit": 8192,
        "reasoning": False, "tool_call": True, "structured_output": False,
        "attachment": False, "open_weights": True, "status": "",
        "release_date": "2024-12-26", "updated_date": "2025-03-24",
    },
]

#--------------------------------------------------
# Intelligence fixtures
#--------------------------------------------------

BENCHLM_DATA = {
    "items": [
        {"canonicalModelKey": "gpt-4o", "model": "GPT-4o", "creator": "OpenAI",
         "score": 55.3, "overallRank": 7},
        {"canonicalModelKey": "gpt-4o-mini", "model": "GPT-4o Mini",
         "creator": "OpenAI", "score": 20.0, "overallRank": 90},
        {"canonicalModelKey": "deepseek-v3", "model": "DeepSeek V3",
         "creator": "DeepSeek", "score": 30.0, "overallRank": 40},
        {"canonicalModelKey": "mistral-7b-v03-preview", "model": "Mistral 7B v0.3",
         "creator": "Mistral", "score": 5.0, "overallRank": 200},
    ]
}

INTEL_ENTRIES = [
    {"key": "gpt-4o", "name": "GPT-4o", "creator": "OpenAI", "score": 55.3, "rank": 7},
    {"key": "gpt-4o-mini", "name": "GPT-4o Mini", "creator": "OpenAI", "score": 20.0, "rank": 90},
    {"key": "deepseek-v3", "name": "DeepSeek V3", "creator": "DeepSeek", "score": 30.0, "rank": 40},
    {"key": "mistral-7b-v03-preview", "name": "Mistral 7B v0.3", "creator": "Mistral",
     "score": 5.0, "rank": 200},
]

INTEL_MODELS = [
    dict(SAMPLE_MODELS[0], intelligence=55.3, intelligence_rank=7),
    dict(SAMPLE_MODELS[1], intelligence=20.0, intelligence_rank=90),
    dict(SAMPLE_MODELS[2], intelligence=None, intelligence_rank=None),
    dict(SAMPLE_MODELS[3], intelligence=30.0, intelligence_rank=40),
]

#--------------------------------------------------
# flatten_models
#--------------------------------------------------


class TestFlattenModels(unittest.TestCase):
    """Tests for flatten_models."""

    def test_flatten_count(self):
        """All models across providers are flattened."""
        result = models.ModelCatalog().flatten(catalog=SAMPLE_CATALOG)
        self.assertEqual(len(result), 5)

    def test_flatten_preserves_provider(self):
        """Each flattened model carries its provider name."""
        result = models.ModelCatalog().flatten(catalog=SAMPLE_CATALOG)
        providers = {m["provider"] for m in result}
        self.assertEqual(providers, {"OpenAI", "Anthropic", "DeepSeek"})

    def test_flatten_empty_catalog(self):
        """An empty catalog yields an empty list."""
        self.assertEqual(models.ModelCatalog().flatten(catalog={}), [])

    def test_flatten_missing_cost(self):
        """Models without cost get zero costs."""
        catalog = {"test": {"id": "test", "name": "Test", "models": {
            "m1": {"id": "m1", "name": "M1", "description": "", "release_date": "",
                   "limit": {"context": 1000, "output": 100}}
        }}}
        result = models.ModelCatalog().flatten(catalog=catalog)
        self.assertEqual(result[0]["total_cost"], 0)

#--------------------------------------------------
# filter_models
#--------------------------------------------------


class TestFilterModels(unittest.TestCase):
    """Tests for filter_models."""

    def test_exclude_free(self):
        """Free models are excluded when exclude_free=True."""
        free = dict(SAMPLE_MODELS[0], total_cost=0, input_cost=0, output_cost=0)
        result = models.ModelFilter().apply(models=[free] + SAMPLE_MODELS, exclude_free=True)
        for m in result:
            self.assertGreater(m["total_cost"], 0)

    def test_free_only(self):
        """Only free models remain when free_only=True."""
        free = dict(SAMPLE_MODELS[0], total_cost=0, input_cost=0, output_cost=0)
        result = models.ModelFilter().apply(models=[free] + SAMPLE_MODELS, free_only=True)
        self.assertEqual(result, [free])

    def test_filter_by_provider(self):
        """Filtering by provider name matches case-insensitively."""
        result = models.ModelFilter().apply(models=SAMPLE_MODELS, provider="openai")
        self.assertTrue(all(m["provider_id"] == "openai" for m in result))

    def test_filter_by_provider_fuzzy(self):
        """Partial provider name matches."""
        result = models.ModelFilter().apply(models=SAMPLE_MODELS, provider="anth")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["provider_id"], "anthropic")

    def test_filter_min_context(self):
        """Models below min_context are excluded."""
        result = models.ModelFilter().apply(models=SAMPLE_MODELS, min_context=100000)
        for m in result:
            self.assertGreaterEqual(m["context"], 100000)

    def test_filter_tool_call(self):
        """Only tool_call models remain."""
        result = models.ModelFilter().apply(models=SAMPLE_MODELS, tool_call=True)
        self.assertTrue(all(m["tool_call"] for m in result))

    def test_filter_reasoning(self):
        """Only reasoning models remain."""
        result = models.ModelFilter().apply(models=SAMPLE_MODELS, reasoning=True)
        self.assertTrue(all(m["reasoning"] for m in result))

    def test_combined_filters(self):
        """Multiple filters narrow results."""
        result = models.ModelFilter().apply(models=
            SAMPLE_MODELS, exclude_free=True, provider="openai", tool_call=True
        )
        self.assertTrue(all(m["provider_id"] == "openai" and m["tool_call"] for m in result))

    def test_no_match(self):
        """Impossible filter returns empty list."""
        result = models.ModelFilter().apply(models=SAMPLE_MODELS, provider="nonexistent")
        self.assertEqual(result, [])

#--------------------------------------------------
# score_model
#--------------------------------------------------


class TestScoreModel(unittest.TestCase):
    """Tests for score_model."""

    def test_free_model_score_positive(self):
        """Free models get a score based on context and capabilities."""
        m = dict(SAMPLE_MODELS[0], total_cost=0, input_cost=0, output_cost=0, context=128000)
        self.assertGreater(models.ModelScorer().score(model=m), 0.0)

    def test_free_model_score_scales_with_context(self):
        """Free model score increases with larger context."""
        m1 = dict(SAMPLE_MODELS[0], total_cost=0, context=64000)
        m2 = dict(SAMPLE_MODELS[0], total_cost=0, context=128000)
        self.assertGreater(
            models.ModelScorer().score(model=m2),
            models.ModelScorer().score(model=m1),
        )

    def test_value_increases_with_context(self):
        """Higher context yields higher score, all else equal."""
        m1 = dict(SAMPLE_MODELS[0], total_cost=10, context=100000)
        m2 = dict(SAMPLE_MODELS[0], total_cost=10, context=200000)
        self.assertGreater(
            models.ModelScorer().score(model=m2),
            models.ModelScorer().score(model=m1),
        )

    def test_value_decreases_with_cost(self):
        """Higher cost yields lower score, all else equal."""
        m1 = dict(SAMPLE_MODELS[0], total_cost=5, context=100000)
        m2 = dict(SAMPLE_MODELS[0], total_cost=10, context=100000)
        self.assertGreater(
            models.ModelScorer().score(model=m1),
            models.ModelScorer().score(model=m2),
        )

    def test_capabilities_bonus(self):
        """More capabilities yield higher score."""
        m_base = dict(SAMPLE_MODELS[0], total_cost=10, context=100000,
                       reasoning=False, tool_call=False, structured_output=False, attachment=False)
        m_full = dict(
            m_base,
            reasoning=True,
            tool_call=True,
            structured_output=True,
            attachment=True,
        )
        self.assertGreater(
            models.ModelScorer().score(model=m_full),
            models.ModelScorer().score(model=m_base),
        )

#--------------------------------------------------
# score_intelligence
#--------------------------------------------------


class TestScoreIntelligence(unittest.TestCase):
    """Tests for score_intelligence."""

    def test_points_per_dollar(self):
        """Scores scale as intelligence divided by total cost."""
        m = dict(SAMPLE_MODELS[0], intelligence=50.0)
        self.assertEqual(models.ModelScorer().intelligence(model=m), 4.0)

    def test_free_model_returns_intelligence(self):
        """Free models score their raw intelligence."""
        m = dict(SAMPLE_MODELS[0], total_cost=0, input_cost=0, output_cost=0,
                 intelligence=42.0)
        self.assertEqual(models.ModelScorer().intelligence(model=m), 42.0)

    def test_missing_intelligence_scores_zero(self):
        """Models without an intelligence entry score zero."""
        self.assertEqual(models.ModelScorer().intelligence(model=SAMPLE_MODELS[0]), 0.0)

    def test_none_intelligence_scores_zero(self):
        """None intelligence scores zero."""
        m = dict(SAMPLE_MODELS[0], intelligence=None)
        self.assertEqual(models.ModelScorer().intelligence(model=m), 0.0)

#--------------------------------------------------
# attach_intelligence
#--------------------------------------------------


class TestAttachIntelligence(unittest.TestCase):
    """Tests for attach_intelligence."""

    def _intel(self, extra=None):
        """Build the intelligence fixture list."""
        entries = list(INTEL_ENTRIES)
        if extra:
            entries.extend(extra)
        return entries

    def test_exact_id_match(self):
        """Catalog ids match BenchLM keys directly."""
        result = models.IntelligenceMatcher.attach(
            models=list(SAMPLE_MODELS),
            entries=self._intel(),
        )
        self.assertEqual(result[0]["intelligence"], 55.3)
        self.assertEqual(result[0]["intelligence_rank"], 7)

    def test_variant_suffix_stripping(self):
        """Qualifier suffixes like -preview are stripped for matching."""
        model = [dict(SAMPLE_MODELS[3], id="mistral-7b-v03", name="Mistral 7B")]
        result = models.IntelligenceMatcher.attach(models=model, entries=self._intel())
        self.assertEqual(result[0]["intelligence"], 5.0)

    def test_plan_and_hosting_markers(self):
        """Plan and hosting markers like -free and -ultraspeed are stripped."""
        extra = [{"key": "mimo-v2-6-pro", "name": "MiMo V2.6 Pro",
                  "creator": "Xiaomi", "score": 73.6, "rank": 20}]
        model = [dict(SAMPLE_MODELS[3], id="mimo-v2.6-pro-ultraspeed", name="MiMo V2.6 Pro")]
        result = models.IntelligenceMatcher.attach(models=model, entries=self._intel(extra=extra))
        self.assertEqual(result[0]["intelligence"], 73.6)
        extra = [{"key": "glm-5-3-flash", "name": "GLM 5.3 Flash",
                  "creator": "Z AI", "score": 58.5, "rank": 35}]
        model = [dict(SAMPLE_MODELS[3], id="opencode/glm-5.3-flash-free", name="GLM-5.3-Flash")]
        result = models.IntelligenceMatcher.attach(models=model, entries=self._intel(extra=extra))
        self.assertEqual(result[0]["intelligence"], 58.5)

    def test_non_reasoning_phrase(self):
        """A non-reasoning marker is stripped even though reasoning is part of it."""
        extra = [{"key": "grok-4-20-beta", "name": "Grok 4.20 Beta",
                  "creator": "xAI", "score": 57.4, "rank": 45}]
        model = [dict(SAMPLE_MODELS[3], id="xai/grok-4.20-beta-non-reasoning",
                      name="Grok 4.20 Beta")]
        result = models.IntelligenceMatcher.attach(models=model, entries=self._intel(extra=extra))
        self.assertEqual(result[0]["intelligence"], 57.4)

    def test_model_defining_markers_not_stripped(self):
        """Model-defining markers like turbo keep variants from wrong matches."""
        extra = [{"key": "glm-5-3", "name": "GLM 5.3", "creator": "Z AI",
                  "score": 68.0, "rank": 30}]
        model = [dict(SAMPLE_MODELS[3], id="glm-5.3-turbo", name="GLM 5.3 Turbo")]
        result = models.IntelligenceMatcher.attach(models=model, entries=self._intel(extra=extra))
        self.assertEqual(result[0]["intelligence"], None)

    def test_none_intel_list(self):
        """A None intelligence list leaves every model unscored."""
        result = models.IntelligenceMatcher.attach(models=list(SAMPLE_MODELS), entries=None)
        self.assertEqual([m["intelligence"] for m in result], [None] * 4)

    def test_name_match_fallback(self):
        """A model name can match even when the id differs."""
        model = [dict(SAMPLE_MODELS[3], id="deepseek/chat-v3", name="DeepSeek V3")]
        result = models.IntelligenceMatcher.attach(models=model, entries=self._intel())
        self.assertEqual(result[0]["intelligence"], 30.0)

    def test_unmatched_models_get_none(self):
        """Models without a BenchLM entry get None intelligence."""
        result = models.IntelligenceMatcher.attach(
            models=list(SAMPLE_MODELS),
            entries=self._intel(),
        )
        self.assertEqual(result[2]["intelligence"], None)
        self.assertEqual(result[2]["intelligence_rank"], None)

    def test_attaches_rank(self):
        """Matched models carry the BenchLM overall rank."""
        result = models.IntelligenceMatcher.attach(
            models=list(SAMPLE_MODELS),
            entries=self._intel(),
        )
        self.assertEqual(result[1]["intelligence_rank"], 90)

    def test_does_not_mutate_input(self):
        """Attaching intelligence leaves the source models untouched."""
        source = [dict(m) for m in SAMPLE_MODELS]
        models.IntelligenceMatcher.attach(models=source, entries=self._intel())
        for m in SAMPLE_MODELS:
            self.assertNotIn("intelligence", m)

#--------------------------------------------------
# sort_value and sort_best
#--------------------------------------------------


class TestSortValue(unittest.TestCase):
    """Tests for sort_value."""

    def test_ranked_models_first(self):
        """Intelligence-ranked models come before unranked ones."""
        result = models.ModelSorter().value(models=INTEL_MODELS)
        self.assertEqual(result[-1]["id"], "claude-opus-4")

    def test_intelligence_per_dollar_order(self):
        """Within ranked models, intelligence per dollar dictates order."""
        result = models.ModelSorter().value(models=INTEL_MODELS)
        ids = [m["id"] for m in result]
        self.assertEqual(ids[:3], ["gpt-4o-mini", "deepseek-v3", "gpt-4o"])

    def test_unranked_ties_use_value_score(self):
        """Unranked models tie-break by the legacy value score."""
        result = models.ModelSorter().value(models=INTEL_MODELS)
        tail = result[3:]
        scores = [models.ModelScorer().score(model=m) for m in tail]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestScoreIntelligenceAllowance(unittest.TestCase):
    """Tests for score_intelligence_allowance."""

    def test_intelligence_multiplied_by_requests(self):
        """Score is intelligence times the plan request allowance."""
        m = dict(GO_MODEL, intelligence=44.0, requests=110)
        self.assertEqual(models.ModelScorer().intelligence_allowance(model=m), 4840.0)

    def test_no_intelligence_scores_zero(self):
        """Models without intelligence score zero."""
        m = dict(GO_MODEL, intelligence=None)
        self.assertEqual(models.ModelScorer().intelligence_allowance(model=m), 0.0)

    def test_unlimited_scores_infinity(self):
        """Unlimited allowance is intelligence times infinity."""
        m = dict(GO_MODEL, intelligence=50.0, unlimited=True)
        self.assertEqual(models.ModelScorer().intelligence_allowance(model=m), float("inf"))


class TestSortValueGo(unittest.TestCase):
    """Tests for sort_value_go."""

    def test_ranked_before_unranked(self):
        """Ranked Go models come before unranked ones."""
        result = models.ModelSorter().value_go(models=GO_INTEL_MODELS)
        self.assertEqual(result[-1]["id"], "other")

    def test_unranked_follow_by_go_score(self):
        """Unranked Go models fall back to the Go usage score order."""
        ranked = dict(
            GO_MODEL,
            id="kimi-k3",
            name="Kimi K3",
            intelligence=44.0,
            intelligence_rank=20,
        )
        unranked_low_score = dict(GO_MODEL, id="weak", name="Weak", requests=5000)
        result = models.ModelSorter().value_go(models=[unranked_low_score, ranked])
        self.assertEqual(result[0]["id"], "kimi-k3")

    def test_ranked_by_intelligence_throughput(self):
        """Ranked Go models are ordered by intelligence x allowance."""
        premium = dict(GO_MODEL, id="kimi", name="Kimi K3",
                       intelligence=70.0, requests=110)
        generous = dict(GO_MODEL, id="muse", name="Muse Spark 1.2",
                        intelligence=65.9, requests=45300)
        result = models.ModelSorter().value_go(models=[premium, generous])
        self.assertEqual([m["id"] for m in result], ["muse", "kimi"])

    def test_unlimited_ranked_first(self):
        """Unlimited-allowance models lead, ordered by intelligence."""
        unlimited = dict(GO_MODEL, id="beam", name="Beam Free",
                         intelligence=50.0, unlimited=True)
        finite = dict(GO_MODEL, id="muse", name="Muse Spark 1.2",
                      intelligence=65.9, requests=45300)
        stronger = dict(GO_MODEL, id="apex", name="Apex",
                        intelligence=80.0, unlimited=True)
        result = models.ModelSorter().value_go(models=[finite, unlimited, stronger])
        self.assertEqual([m["id"] for m in result], ["apex", "beam", "muse"])


class TestSortBest(unittest.TestCase):
    """Tests for sort_best."""

    def test_intelligence_order(self):
        """Models are ordered by raw intelligence descending."""
        result = models.ModelSorter().best(models=INTEL_MODELS)
        intel = [m["intelligence"] for m in result[:3]]
        self.assertEqual(intel, [55.3, 30.0, 20.0])

    def test_unranked_models_last(self):
        """Models without intelligence come after ranked ones."""
        result = models.ModelSorter().best(models=INTEL_MODELS)
        self.assertIsNone(result[-1]["intelligence"])

    def test_unranked_fallback_prefers_large_context(self):
        """Unranked models order by context, capabilities, then release date."""
        result = models.ModelSorter().best(models=SAMPLE_MODELS)
        self.assertEqual(result[0]["id"], "claude-opus-4")

    def test_works_without_release_date(self):
        """Go merged models lack release_date; sorting must not crash."""
        result = models.ModelSorter().best(models=GO_INTEL_MODELS)
        self.assertEqual(result[0]["id"], "kimi-k3")
        self.assertEqual(result[-1]["id"], "other")

#--------------------------------------------------
# sort functions
#--------------------------------------------------


class TestSortCheapest(unittest.TestCase):
    """Tests for sort_cheapest."""

    def test_cheapest_order(self):
        """Models are sorted by total cost ascending."""
        result = models.ModelSorter().cheapest(models=SAMPLE_MODELS)
        costs = [m["total_cost"] for m in result]
        self.assertEqual(costs, sorted(costs))

    def test_cheapest_preserves_all(self):
        """All models are present after sorting."""
        result = models.ModelSorter().cheapest(models=SAMPLE_MODELS)
        self.assertEqual(len(result), len(SAMPLE_MODELS))


class TestSortReleased(unittest.TestCase):
    """Tests for sort_released."""

    def test_released_order(self):
        """Models are sorted by release date descending."""
        result = models.ModelSorter().released(models=SAMPLE_MODELS)
        dates = [m["release_date"] for m in result]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_released_preserves_all(self):
        """All models are present after sorting."""
        result = models.ModelSorter().released(models=SAMPLE_MODELS)
        self.assertEqual(len(result), len(SAMPLE_MODELS))

    def test_released_most_recent_first(self):
        """Most recently released model is first."""
        result = models.ModelSorter().released(models=SAMPLE_MODELS)
        self.assertEqual(result[0]["release_date"], "2025-06-26")


class TestSortUpdated(unittest.TestCase):
    """Tests for sort_updated."""

    def test_updated_order(self):
        """Models are sorted by update date descending."""
        result = models.ModelSorter().updated(models=SAMPLE_MODELS)
        dates = [m["updated_date"] for m in result]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_updated_preserves_all(self):
        """All models are present after sorting."""
        result = models.ModelSorter().updated(models=SAMPLE_MODELS)
        self.assertEqual(len(result), len(SAMPLE_MODELS))

    def test_updated_most_recent_first(self):
        """Most recently updated model is first."""
        result = models.ModelSorter().updated(models=SAMPLE_MODELS)
        self.assertEqual(result[0]["updated_date"], "2025-07-15")

#--------------------------------------------------
# Format helpers
#--------------------------------------------------


class TestFormatCost(unittest.TestCase):
    """Tests for format_cost."""

    def test_free(self):
        """Zero cost displays as 'free'."""
        self.assertEqual(models.ModelFormatter().cost(value=0), "free")

    def test_small_cost(self):
        """Very small costs show 4 decimals."""
        self.assertEqual(models.ModelFormatter().cost(value=0.005), "$0.0050")

    def test_medium_cost(self):
        """Medium costs show 3 decimals."""
        self.assertEqual(models.ModelFormatter().cost(value=0.5), "$0.500")

    def test_large_cost(self):
        """Large costs show 2 decimals."""
        self.assertEqual(models.ModelFormatter().cost(value=15), "$15.00")


class TestFormatContext(unittest.TestCase):
    """Tests for format_context."""

    def test_millions(self):
        """Context in millions shows M suffix."""
        self.assertEqual(models.ModelFormatter().context(tokens=1280000), "1.3M")

    def test_thousands(self):
        """Context in thousands shows K suffix."""
        self.assertEqual(models.ModelFormatter().context(tokens=128000), "128K")

    def test_small(self):
        """Small context shows raw number."""
        self.assertEqual(models.ModelFormatter().context(tokens=500), "500")


class TestFormatFlags(unittest.TestCase):
    """Tests for format_flags."""

    def test_all_caps(self):
        """All capabilities present shows RTSA."""
        m = {"reasoning": True, "tool_call": True, "structured_output": True, "attachment": True}
        self.assertEqual(models.ModelFormatter().flags(model=m), "RTSA")

    def test_no_caps(self):
        """No capabilities shows dash."""
        m = {
            "reasoning": False,
            "tool_call": False,
            "structured_output": False,
            "attachment": False,
        }
        self.assertEqual(models.ModelFormatter().flags(model=m), "-")

    def test_partial(self):
        """Partial capabilities show only present flags."""
        m = {"reasoning": True, "tool_call": False, "structured_output": True, "attachment": False}
        self.assertEqual(models.ModelFormatter().flags(model=m), "RS")


class TestFormatIntelligence(unittest.TestCase):
    """Tests for format_intelligence."""

    def test_dash_when_missing(self):
        """Missing intelligence displays as a dash."""
        self.assertEqual(models.ModelFormatter().intelligence(model={}), "-")
        self.assertEqual(models.ModelFormatter().intelligence(model={"intelligence": None}), "-")

    def test_one_decimal(self):
        """Intelligence scores display with one decimal."""
        self.assertEqual(
            models.ModelFormatter().intelligence(model={"intelligence": 55.34}),
            "55.3",
        )

    def test_integer_score(self):
        """Integer scores display with one decimal."""
        self.assertEqual(models.ModelFormatter().intelligence(model={"intelligence": 20}), "20.0")


class TestPrintIntelAttribution(unittest.TestCase):
    """Tests for print_intel_attribution."""

    def test_stdout_by_default(self):
        """The credit prints to stdout for human-readable output."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            models.IntelligenceAttribution.render()
        self.assertIn("BenchLM", out.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_stderr_for_machine_output(self):
        """The credit prints to stderr for CSV and JSON output."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            models.IntelligenceAttribution.render(machine_output=True)
        self.assertIn("BenchLM", err.getvalue())
        self.assertEqual(out.getvalue(), "")


class TestShowIntelAttribution(unittest.TestCase):
    """Tests for _show_intel_attribution."""

    def test_prints_when_any_score_present(self):
        """The credit prints when at least one displayed model has a score."""
        shown = [dict(SAMPLE_MODELS[0], intelligence=55.3),
                 dict(SAMPLE_MODELS[1], intelligence=None)]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            models.IntelligenceAttribution.show(models=shown, machine_output=False)
        self.assertIn("BenchLM", out.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_stderr_for_machine_output(self):
        """The credit prints to stderr when stdout stays machine-readable."""
        shown = [dict(SAMPLE_MODELS[0], intelligence=55.3)]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            models.IntelligenceAttribution.show(models=shown, machine_output=True)
        self.assertIn("BenchLM", err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_silent_without_scores(self):
        """No credit prints when no displayed model has a score."""
        shown = [dict(SAMPLE_MODELS[0], intelligence=None)]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            models.IntelligenceAttribution.show(models=shown, machine_output=False)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")

    def test_silent_for_empty_list(self):
        """No credit prints when nothing is displayed."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            models.IntelligenceAttribution.show(models=[], machine_output=False)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")

#--------------------------------------------------
# CLI argument parsing
#--------------------------------------------------


class TestParser(unittest.TestCase):
    """Tests for the argument parser."""

    def _get_parser(self):
        app = models.App(
            author='test', title='test', description='test'
        )
        return app.build_parser()

    def test_cheapest_mode(self):
        """--cheapest sets cheapest=True."""
        parser = self._get_parser()
        args = parser.parse_args(["--cheapest"])
        self.assertTrue(args.cheapest)
        self.assertFalse(args.value)
        self.assertFalse(args.best)

    def test_free_mode(self):
        """--free sets free=True."""
        parser = self._get_parser()
        args = parser.parse_args(["--free"])
        self.assertTrue(args.free)
        self.assertFalse(args.cheapest)
        self.assertFalse(args.value)

    def test_value_mode(self):
        """--value sets value=True."""
        parser = self._get_parser()
        args = parser.parse_args(["--value"])
        self.assertTrue(args.value)

    def test_best_mode(self):
        """--best sets best=True."""
        parser = self._get_parser()
        args = parser.parse_args(["--best"])
        self.assertTrue(args.best)

    def test_released_mode(self):
        """--released sets released=True."""
        parser = self._get_parser()
        args = parser.parse_args(["--released"])
        self.assertTrue(args.released)
        self.assertFalse(args.best)
        self.assertFalse(args.value)

    def test_updated_mode(self):
        """--updated sets updated=True."""
        parser = self._get_parser()
        args = parser.parse_args(["--updated"])
        self.assertTrue(args.updated)
        self.assertFalse(args.best)
        self.assertFalse(args.released)

    def test_smart_argument_removed(self):
        """--smart is no longer accepted."""
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self._get_parser().parse_args(["--smart"])

    def test_mutually_exclusive(self):
        """Cannot combine --cheapest and --best."""
        parser = self._get_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--cheapest", "--best"])

    def test_free_mutually_exclusive(self):
        """Cannot combine --free and --cheapest."""
        parser = self._get_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--free", "--cheapest"])

    def test_no_mode_defaults_to_updated(self):
        """No mode flag does not set any explicit mode."""
        parser = self._get_parser()
        args = parser.parse_args([])
        self.assertFalse(args.cheapest)
        self.assertFalse(args.free)
        self.assertFalse(args.value)
        self.assertFalse(args.best)
        self.assertFalse(args.released)
        self.assertFalse(args.updated)
        self.assertFalse(args.providers)

    def test_optional_filters(self):
        """Optional filters parse correctly."""
        parser = self._get_parser()
        args = parser.parse_args(["--cheapest", "--provider", "openai", "--min-context", "100000",
                                  "--tool-call", "--reasoning", "--limit", "5", "--md"])
        self.assertEqual(args.provider, "openai")
        self.assertEqual(args.min_context, 100000)
        self.assertTrue(args.tool_call)
        self.assertTrue(args.reasoning)
        self.assertEqual(args.limit, 5)
        self.assertTrue(args.md_output)

    def test_default_limit(self):
        """Default limit is 10."""
        parser = self._get_parser()
        args = parser.parse_args(["--cheapest"])
        self.assertEqual(args.limit, 10)

    def test_md_flag(self):
        """--md sets md_output=True."""
        parser = self._get_parser()
        args = parser.parse_args(["--cheapest", "--md"])
        self.assertTrue(args.md_output)

    def test_csv_flag(self):
        """--csv sets csv_output=True."""
        parser = self._get_parser()
        args = parser.parse_args(["--cheapest", "--csv"])
        self.assertTrue(args.csv_output)

    def test_providers_mode(self):
        """--providers sets providers=True."""
        parser = self._get_parser()
        args = parser.parse_args(["--providers"])
        self.assertTrue(args.providers)

    def test_default_provider(self):
        """Default provider is 'opencode'."""
        parser = self._get_parser()
        args = parser.parse_args(["--cheapest"])
        self.assertEqual(args.provider, "opencode")

    def test_providers_mutually_exclusive(self):
        """Cannot combine --providers and --cheapest."""
        parser = self._get_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--providers", "--cheapest"])

    def test_released_mutually_exclusive(self):
        """Cannot combine --released and --best."""
        parser = self._get_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--released", "--best"])

    def test_updated_mutually_exclusive(self):
        """Cannot combine --updated and --cheapest."""
        parser = self._get_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--updated", "--cheapest"])

#--------------------------------------------------
# Output selection and rendering
#--------------------------------------------------


class TestOutputFormat(unittest.TestCase):
    """Tests for OutputFormat."""

    def _args(self, argv):
        """Parse output flags with the application parser."""
        app = models.App(author='test', title='test', description='test')
        return app.build_parser().parse_args(argv)

    def test_default_is_table(self):
        """No output flag selects the table printer."""
        self.assertEqual(models.OutputFormat.select(args=self._args([])), "table")

    def test_json_selected(self):
        """--json selects the JSON printer."""
        self.assertEqual(
            models.OutputFormat.select(args=self._args(["--json"])),
            "json",
        )

    def test_markdown_selected(self):
        """--md selects the markdown printer."""
        self.assertEqual(
            models.OutputFormat.select(args=self._args(["--md"])),
            "markdown",
        )

    def test_csv_takes_precedence(self):
        """--csv wins when combined with --json."""
        args = self._args(["--csv", "--json"])
        self.assertEqual(models.OutputFormat.select(args=args), "csv")

    def test_markdown_takes_precedence_over_json(self):
        """--md wins when combined with --json."""
        args = self._args(["--md", "--json"])
        self.assertEqual(models.OutputFormat.select(args=args), "markdown")

    def test_machine_formats(self):
        """CSV and JSON are machine-readable formats."""
        self.assertTrue(models.OutputFormat.is_machine(name="json"))
        self.assertTrue(models.OutputFormat.is_machine(name="csv"))
        self.assertFalse(models.OutputFormat.is_machine(name="markdown"))
        self.assertFalse(models.OutputFormat.is_machine(name="table"))


class TestOutputRendering(unittest.TestCase):
    """Tests for the output classes that select a printer."""

    def _args(self, argv):
        """Parse output flags with the application parser."""
        app = models.App(author='test', title='test', description='test')
        return app.build_parser().parse_args(argv)

    def test_model_output_json(self):
        """ModelOutput routes to the JSON printer."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelOutput().render(
                args=self._args(["--cheapest", "--json"]),
                models=SAMPLE_MODELS[:1],
                title="T",
            )
        self.assertEqual(json.loads(buf.getvalue())[0]["id"], "gpt-4o")

    def test_model_output_csv_takes_precedence(self):
        """ModelOutput prefers CSV when both output flags are set."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelOutput().render(
                args=self._args(["--cheapest", "--csv", "--json"]),
                models=SAMPLE_MODELS[:1],
                title="T",
            )
        self.assertIn("provider,model", buf.getvalue())

    def test_go_output_json(self):
        """GoOutput routes to the JSON printer."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoOutput().render(
                args=self._args(["--go", "--json"]),
                models=[GO_MODEL],
            )
        self.assertEqual(json.loads(buf.getvalue())[0]["id"], "kimi-k3")

    def test_provider_output_json(self):
        """ProviderOutput routes to the JSON printer."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ProviderOutput().render(
                args=self._args(["--providers", "--json"]),
                catalog=SAMPLE_CATALOG,
            )
        self.assertEqual(len(json.loads(buf.getvalue())), 3)


#--------------------------------------------------
# print_json
#--------------------------------------------------


class TestPrintJson(unittest.TestCase):
    """Tests for print_json output."""

    def test_json_output(self):
        """print_json outputs valid JSON."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelJsonPrinter().render(models=SAMPLE_MODELS[:2])
        data = json.loads(buf.getvalue())
        self.assertEqual(len(data), 2)
        self.assertIn("provider", data[0])
        self.assertIn("score", data[0])

    def test_json_includes_intelligence(self):
        """JSON output carries the intelligence field."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelJsonPrinter().render(models=SAMPLE_MODELS[:1])
        data = json.loads(buf.getvalue())
        self.assertEqual(data[0]["intelligence"], None)
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelJsonPrinter().render(models=INTEL_MODELS[:1])
        data = json.loads(buf.getvalue())
        self.assertEqual(data[0]["intelligence"], 55.3)

    def test_json_excludes_internal_fields(self):
        """JSON output does not include internal fields."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelJsonPrinter().render(models=SAMPLE_MODELS[:1])
        data = json.loads(buf.getvalue())
        self.assertNotIn("total_cost", data[0])
        self.assertNotIn("provider_id", data[0])

#--------------------------------------------------
# print_markdown
#--------------------------------------------------


class TestPrintMarkdown(unittest.TestCase):
    """Tests for print_markdown output."""

    def test_markdown_output(self):
        """print_markdown outputs valid markdown table."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelMarkdownPrinter().render(models=SAMPLE_MODELS[:2], title="Test Title")
        output = buf.getvalue()
        self.assertIn("## Test Title", output)
        self.assertIn("| Provider |", output)
        self.assertIn("GPT-4o", output)
        self.assertIn("GPT-4o Mini", output)

    def test_markdown_empty_models(self):
        """print_markdown with empty list shows no-match message."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelMarkdownPrinter().render(models=[], title="Empty")
        output = buf.getvalue()
        self.assertIn("No models match", output)

    def test_markdown_contains_table_separator(self):
        """Markdown output includes the table separator line."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelMarkdownPrinter().render(models=SAMPLE_MODELS[:1], title="T")
        output = buf.getvalue()
        self.assertIn("|---|---|---|---|---|---|---|", output)

    def test_markdown_intel_column(self):
        """Markdown output adds an Intel column when requested."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelMarkdownPrinter().render(
                models=INTEL_MODELS[:1],
                title="T",
                show_intel=True,
            )
        output = buf.getvalue()
        self.assertIn("| Cap | Intel | Score |", output)
        self.assertIn("| TSA | 55.3 |", output)

    def test_markdown_no_intel_by_default(self):
        """The Intel column is absent unless requested."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelMarkdownPrinter().render(models=INTEL_MODELS[:1], title="T")
        output = buf.getvalue()
        self.assertNotIn("Intel", output)

#--------------------------------------------------
# print_providers
#--------------------------------------------------


class TestPrintProviders(unittest.TestCase):
    """Tests for print_providers output."""

    def test_providers_output(self):
        """print_providers outputs provider table."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ProviderTablePrinter().render(catalog=SAMPLE_CATALOG)
        output = buf.getvalue()
        self.assertIn("OpenAI", output)
        self.assertIn("Anthropic", output)
        self.assertIn("DeepSeek", output)

    def test_providers_sorted(self):
        """Providers are listed in alphabetical order."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ProviderTablePrinter().render(catalog=SAMPLE_CATALOG)
        output = buf.getvalue()
        pos_anthropic = output.index("Anthropic")
        pos_deepseek = output.index("DeepSeek")
        pos_openai = output.index("OpenAI")
        self.assertLess(pos_anthropic, pos_deepseek)
        self.assertLess(pos_deepseek, pos_openai)

    def test_providers_model_count(self):
        """Model count is displayed for each provider."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ProviderTablePrinter().render(catalog=SAMPLE_CATALOG)
        output = buf.getvalue()
        self.assertIn("2", output)


class TestPrintProvidersJson(unittest.TestCase):
    """Tests for print_providers_json output."""

    def test_providers_json_output(self):
        """print_providers_json outputs valid JSON."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ProviderJsonPrinter().render(catalog=SAMPLE_CATALOG)
        data = json.loads(buf.getvalue())
        self.assertEqual(len(data), 3)
        self.assertIn("id", data[0])
        self.assertIn("name", data[0])
        self.assertIn("models", data[0])

    def test_providers_json_sorted(self):
        """Providers are sorted alphabetically in JSON."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ProviderJsonPrinter().render(catalog=SAMPLE_CATALOG)
        data = json.loads(buf.getvalue())
        names = [p["name"] for p in data]
        self.assertEqual(names, sorted(names, key=str.lower))


class TestPrintProvidersMarkdown(unittest.TestCase):
    """Tests for print_providers_markdown output."""

    def test_providers_markdown_output(self):
        """print_providers_markdown outputs valid markdown table."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ProviderMarkdownPrinter().render(catalog=SAMPLE_CATALOG)
        output = buf.getvalue()
        self.assertIn("## Available Providers", output)
        self.assertIn("| ID | Name | Models |", output)
        self.assertIn("OpenAI", output)
        self.assertIn("Anthropic", output)
        self.assertIn("DeepSeek", output)


#--------------------------------------------------
# print_csv
#--------------------------------------------------


class TestPrintCsv(unittest.TestCase):
    """Tests for print_csv output."""

    def test_csv_output(self):
        """print_csv outputs valid CSV with header."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelCsvPrinter().render(models=SAMPLE_MODELS[:2])
        lines = buf.getvalue().strip().split("\n")
        self.assertEqual(len(lines), 3)
        self.assertIn("provider,model,input_cost", lines[0])
        self.assertIn("GPT-4o", lines[1])

    def test_csv_empty_models(self):
        """print_csv with empty list produces no output."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelCsvPrinter().render(models=[])
        self.assertEqual(buf.getvalue(), "")

    def test_csv_columns(self):
        """CSV output contains expected columns."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelCsvPrinter().render(models=SAMPLE_MODELS[:1])
        header = buf.getvalue().split("\n")[0]
        for col in ["provider", "model", "input_cost", "output_cost", "context",
                     "score", "reasoning", "tool_call", "structured_output", "attachment"]:
            self.assertIn(col, header)

    def test_csv_intelligence_column(self):
        """CSV output carries the intelligence column between attachment and score."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelCsvPrinter().render(models=SAMPLE_MODELS[:1])
        header = buf.getvalue().splitlines()[0]
        cols = header.split(",")
        self.assertGreater(cols.index("intelligence"), cols.index("attachment"))
        self.assertLess(cols.index("intelligence"), cols.index("score"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelCsvPrinter().render(models=INTEL_MODELS[:1])
        row = buf.getvalue().split("\n")[1]
        self.assertIn(",55.3,", row)

#--------------------------------------------------
# print_providers_csv
#--------------------------------------------------


class TestPrintProvidersCsv(unittest.TestCase):
    """Tests for print_providers_csv output."""

    def test_providers_csv_output(self):
        """print_providers_csv outputs valid CSV with header."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ProviderCsvPrinter().render(catalog=SAMPLE_CATALOG)
        lines = buf.getvalue().strip().split("\n")
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], "id,name,models")
        output = buf.getvalue()
        self.assertIn("OpenAI", output)

    def test_providers_csv_sorted(self):
        """Providers are listed in alphabetical order in CSV."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ProviderCsvPrinter().render(catalog=SAMPLE_CATALOG)
        lines = buf.getvalue().strip().split("\n")[1:]
        names = [line.split(",")[1] for line in lines]
        self.assertEqual(names, sorted(names, key=str.lower))

#--------------------------------------------------
# print_table
#--------------------------------------------------


class TestPrintTable(unittest.TestCase):
    """Tests for print_table output."""

    def test_table_output(self):
        """print_table outputs formatted table with headers."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelTablePrinter().render(models=SAMPLE_MODELS[:2], title="Test Table")
        output = buf.getvalue()
        self.assertIn("Provider", output)
        self.assertIn("Model", output)
        self.assertIn("In", output)
        self.assertIn("Out", output)
        self.assertIn("Context", output)
        self.assertIn("Score", output)
        self.assertIn("Cap", output)

    def test_table_contains_models(self):
        """print_table includes model names in output."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelTablePrinter().render(models=SAMPLE_MODELS[:2], title="Test Table")
        output = buf.getvalue()
        self.assertIn("GPT-4o", output)
        self.assertIn("GPT-4o Mini", output)

    def test_table_intel_column(self):
        """print_table shows the Intel column only when requested."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelTablePrinter().render(
                models=INTEL_MODELS[:1],
                title="Intel Table",
                show_intel=True,
            )
        output = buf.getvalue()
        self.assertIn("Intel", output)
        self.assertIn("55.3", output)
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelTablePrinter().render(models=INTEL_MODELS[:1], title="Plain Table")
        output = buf.getvalue()
        self.assertNotIn("Intel", output)

    def test_table_empty_models(self):
        """print_table with empty list shows warning."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelTablePrinter().render(models=[], title="Empty Table")
        output = buf.getvalue()
        self.assertIn("No models match", output)

    def test_table_title(self):
        """print_table includes the title in output."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.ModelTablePrinter().render(models=SAMPLE_MODELS[:1], title="My Custom Title")
        output = buf.getvalue()
        self.assertIn("My Custom Title", output)

#--------------------------------------------------
# --json flag
#--------------------------------------------------


class TestJsonFlag(unittest.TestCase):
    """Tests for --json flag parsing."""

    def test_json_flag(self):
        """--json sets json_output=True."""
        app = models.App(author='test', title='test', description='test')
        parser = app.build_parser()
        args = parser.parse_args(["--cheapest", "--json"])
        self.assertTrue(args.json_output)

    def test_json_flag_default_false(self):
        """json_output defaults to False."""
        app = models.App(author='test', title='test', description='test')
        parser = app.build_parser()
        args = parser.parse_args(["--cheapest"])
        self.assertFalse(args.json_output)

    def test_csv_takes_precedence_over_json(self):
        """When both --csv and --json are set, csv_output is checked first."""
        app = models.App(author='test', title='test', description='test')
        parser = app.build_parser()
        args = parser.parse_args(["--cheapest", "--csv", "--json"])
        self.assertTrue(args.csv_output)
        self.assertTrue(args.json_output)

    def test_md_takes_precedence_over_json(self):
        """When both --md and --json are set, md_output is checked first."""
        app = models.App(author='test', title='test', description='test')
        parser = app.build_parser()
        args = parser.parse_args(["--cheapest", "--md", "--json"])
        self.assertTrue(args.md_output)
        self.assertTrue(args.json_output)


#--------------------------------------------------
# fetch_go_models
#--------------------------------------------------

GO_HTML = """
<section class="console-go-models" data-layer="go-model-catalogue">
  <table aria-label="Go and Go Plus allowances" data-layer="model-table">
    <thead>
      <tr>
        <th scope="col">Model</th>
        <th scope="col"><span class="sr-only">Relative request allowances</span></th>
        <th scope="col" data-allowance-type="requests">Est. requests <span>/ 5 hr</span></th>
        <th scope="col" data-allowance-type="usage">Monthly <span>limit</span></th>
      </tr>
    </thead>
    <tbody>
      <tr data-model="kimi-k3">
        <th scope="row"><span data-layer="model-name">Kimi K3</span></th>
        <td aria-hidden="true"></td>
        <td data-allowance-type="requests">
          <div data-layer="requests" aria-hidden="true">
            <span data-layer="allowance" data-plan="go"><span data-layer="current-value">110</span></span>
            <span data-layer="allowance" data-plan="go-plus"><span data-layer="current-value">440</span></span>
          </div>
          <span class="sr-only">Go: 110; Go Plus: 440</span>
        </td>
        <td data-allowance-type="usage">
          <div data-layer="usage" aria-hidden="true">
            <span data-layer="allowance" data-plan="go"><span data-layer="current-value">$15</span></span>
            <span data-layer="allowance" data-plan="go-plus"><span data-layer="current-value">$60</span></span>
          </div>
        </td>
      </tr>
      <tr data-model="other">
        <th scope="row">
          <span class="console-go-models-name-line">
            <span data-layer="model-name">Other</span>
            <span data-layer="model-note">Limited time</span>
          </span>
        </th>
        <td aria-hidden="true"></td>
        <td data-allowance-type="requests">
          <div data-layer="requests" aria-hidden="true">
            <span data-layer="allowance" data-plan="go"><span data-layer="current-value">5,000</span></span>
            <span data-layer="allowance" data-plan="go-plus"><span data-layer="current-value">20,000</span></span>
          </div>
          <span class="sr-only">Go: 5,000; Go Plus: 20,000</span>
        </td>
        <td data-allowance-type="usage">
          <div data-layer="usage" aria-hidden="true">
            <span data-layer="allowance" data-plan="go"><span data-layer="current-value">$15</span></span>
            <span data-layer="allowance" data-plan="go-plus"><span data-layer="current-value">$60</span></span>
          </div>
        </td>
      </tr>
    </tbody>
  </table>
</section>
"""

GO_UNLIMITED_HTML = """
<section class="console-go-models" data-layer="go-model-catalogue">
  <table aria-label="Go and Go Plus allowances" data-layer="model-table">
    <thead>
      <tr>
        <th scope="col">Model</th>
        <th scope="col"><span class="sr-only">Relative request allowances</span></th>
        <th scope="col" data-allowance-type="requests">Est. requests <span>/ 5 hr</span></th>
        <th scope="col" data-allowance-type="usage">Monthly <span>limit</span></th>
      </tr>
    </thead>
    <tbody>
      <tr data-model="kimi-k3">
        <th scope="row"><span data-layer="model-name">Kimi K3</span></th>
        <td aria-hidden="true"></td>
        <td data-allowance-type="requests">
          <div data-layer="requests" aria-hidden="true">
            <span data-layer="allowance" data-plan="go"><span data-layer="current-value">110</span></span>
            <span data-layer="allowance" data-plan="go-plus"><span data-layer="current-value">440</span></span>
          </div>
        </td>
        <td data-allowance-type="usage"></td>
      </tr>
      <tr data-model="union-alpha">
        <th scope="row"><span data-layer="model-name">Union Alpha</span></th>
        <td aria-hidden="true"></td>
        <td data-allowance-type="requests">
          <div data-layer="requests" aria-hidden="true">
            <span data-layer="allowance" data-plan="go"><span data-layer="current-value">∞</span></span>
            <span data-layer="allowance" data-plan="go-plus"><span data-layer="current-value">∞</span></span>
          </div>
        </td>
        <td data-allowance-type="usage"></td>
      </tr>
    </tbody>
  </table>
</section>
"""

GO_CATALOG = {
    "opencode": {
        "id": "opencode",
        "name": "OpenCode",
        "models": {
            "opencode/kimi-k3": {
                "id": "opencode/kimi-k3",
                "name": "Kimi K3",
                "attachment": True,
                "reasoning": True,
                "tool_call": True,
                "structured_output": True,
                "limit": {"context": 200000, "output": 8192},
                "cost": {"input": 1.0, "output": 2.0},
            },
            "opencode/plain-model": {
                "id": "opencode/plain-model",
                "name": "Plain Model",
                "attachment": False,
                "reasoning": False,
                "tool_call": True,
                "structured_output": False,
                "limit": {"context": 64000, "output": 4096},
                "cost": {"input": 0.5, "output": 1.5},
            },
        },
    },
}

GO_MODEL = {
    "id": "kimi-k3",
    "name": "Kimi K3",
    "requests": 110,
    "input_cost": 1.0,
    "output_cost": 2.0,
    "total_cost": 3.0,
    "context": 200000,
    "reasoning": True,
    "tool_call": True,
    "structured_output": True,
    "attachment": True,
}

GO_INTEL_MODELS = [
    dict(GO_MODEL, id="other", name="Other", intelligence=None, intelligence_rank=None),
    dict(GO_MODEL, id="kimi-k3", name="Kimi K3", intelligence=44.0, intelligence_rank=20),
]


class TestFetchGoModels(unittest.TestCase):
    """Tests for GoFetcher."""

    def setUp(self):
        """Create an isolated cache before each test."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = models.Cache()
        self.cache.cache_dir = Path(self.tmp.name)

    def fetch_with(self, pages):
        """Fetch Go models from a URL-to-body mapping and record calls."""
        transport = FakeTransport(pages=pages)
        fetcher = models.GoFetcher(transport=transport, cache=self.cache)
        result = fetcher.fetch()
        return result, transport.calls

    def test_parses_and_sorts_by_requests(self):
        """Go models are parsed and sorted by requests descending."""
        result, _ = self.fetch_with({models.GoFetcher.URL: GO_HTML})
        self.assertEqual([m["name"] for m in result], ["Other", "Kimi K3"])
        self.assertEqual(result[1]["requests"], 110)

    def test_model_id_is_captured(self):
        """The row data-model slug is kept as the Go model id."""
        result, _ = self.fetch_with({models.GoFetcher.URL: GO_HTML})
        self.assertEqual(result[1]["id"], "kimi-k3")

    def test_go_plan_values_are_selected(self):
        """Go request values win over the Go Plus values in the same cell."""
        result, calls = self.fetch_with({models.GoFetcher.URL: GO_HTML})
        self.assertEqual(result[1]["requests"], 110)
        self.assertEqual(result[0]["requests"], 5000)
        self.assertNotIn(440, [m["requests"] for m in result])
        self.assertEqual(calls, [models.GoFetcher.URL])

    def test_missing_table_exits(self):
        """A page without a Go requests table exits with an error."""
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.fetch_with({
                models.GoFetcher.URL: "<html><body><p>nothing here</p></body></html>",
            })

    def test_page_fetch_error_exits(self):
        """A failed page fetch exits with an error."""
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.fetch_with({models.GoFetcher.URL: urllib.error.URLError("boom")})

    def test_unlimited_requests_parsed_as_unlimited(self):
        """An Unlimited request value is parsed without crashing and sorted first."""
        result, _ = self.fetch_with({models.GoFetcher.URL: GO_UNLIMITED_HTML})
        unlimited = next(m for m in result if m["name"] == "Union Alpha")
        self.assertTrue(unlimited["unlimited"])
        self.assertEqual(unlimited["requests"], 0)
        self.assertEqual(result[0]["name"], "Union Alpha")
        limited = next(m for m in result if m["name"] == "Kimi K3")
        self.assertFalse(limited["unlimited"])
        self.assertEqual(limited["requests"], 110)

    def test_unlimited_model_not_in_flagged_positions(self):
        """Non-unlimited models keep the unlimited flag disabled."""
        result, _ = self.fetch_with({models.GoFetcher.URL: GO_HTML})
        self.assertFalse(any(m["unlimited"] for m in result))


#--------------------------------------------------
# fetch_intelligence
#--------------------------------------------------


class TestFetchIntelligence(unittest.TestCase):
    """Tests for BenchLmFetcher."""

    def setUp(self):
        """Create an isolated BenchLM cache before each test."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = models.Cache()
        self.cache.cache_dir = Path(self.tmp.name)

    def fetcher_with(self, pages):
        """Build a BenchLM fetcher backed by a scripted transport."""
        transport = FakeTransport(pages=pages)
        return models.BenchLmFetcher(transport=transport, cache=self.cache), transport

    def test_fetches_and_parses_items(self):
        """The leaderboard items are parsed into intelligence entries."""
        fetcher, _ = self.fetcher_with({
            models.BenchLmFetcher.URL: json.dumps(BENCHLM_DATA),
        })
        result = fetcher.fetch()
        self.assertEqual(result[0]["key"], "gpt-4o")
        self.assertEqual(result[0]["score"], 55.3)

    def test_fetch_error_exits(self):
        """A failed leaderboard fetch exits with an error."""
        fetcher, _ = self.fetcher_with({
            models.BenchLmFetcher.URL: urllib.error.URLError("boom"),
        })
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            fetcher.fetch()

    def test_fetch_error_not_required_returns_none(self):
        """With required=False a failed fetch logs a warning and returns None."""
        fetcher, _ = self.fetcher_with({
            models.BenchLmFetcher.URL: urllib.error.URLError("boom"),
        })
        result = fetcher.fetch(required=False)
        self.assertIsNone(result)

    def test_cached_data_reused(self):
        """Cached leaderboard data is used without a network call."""
        self.cache.write(request="benchlm", data=INTEL_ENTRIES)
        fetcher, transport = self.fetcher_with({"": AssertionError("network")})
        result = fetcher.fetch()
        self.assertEqual(result[0]["score"], 55.3)
        self.assertEqual(transport.calls, [])


#--------------------------------------------------
# merge_go_with_catalog
#--------------------------------------------------


class TestMergeGoWithCatalog(unittest.TestCase):
    """Tests for merge_go_with_catalog."""

    def test_short_and_full_id_match(self):
        """Go ids match both full and short catalog ids."""
        go_models = [
            {"id": "kimi-k3", "name": "Kimi K3", "requests": 110},
            {"id": "opencode/plain-model", "name": "Plain", "requests": 50},
        ]
        merged = models.ModelCatalog().merge_go(go_models=go_models, catalog=GO_CATALOG)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["id"], "kimi-k3")
        self.assertEqual(merged[1]["id"], "plain-model")

    def test_name_matches_catalog(self):
        """Docs names match punctuation-insensitive catalog names and ids."""
        go_models = [{"name": "Kimi K3", "requests": 110}]
        merged = models.ModelCatalog().merge_go(go_models=go_models, catalog=GO_CATALOG)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["id"], "kimi-k3")
        self.assertEqual(merged[0]["total_cost"], 3.0)

    def test_opencode_go_provider_wins(self):
        """Duplicate model names resolve to the OpenCode Go provider first."""
        catalog = {
            "other": {
                "id": "other",
                "name": "Other",
                "models": {
                    "kimi-k3": {
                        "id": "kimi-k3",
                        "name": "Kimi K3",
                        "cost": {"input": 9, "output": 9},
                    },
                },
            },
            "opencode-go": {
                "id": "opencode-go",
                "name": "OpenCode Go",
                "models": {
                    "kimi-k3": {
                        "id": "kimi-k3",
                        "name": "Kimi K3",
                        "cost": {"input": 1, "output": 2},
                    },
                },
            },
        }
        go_models = [{"name": "Kimi K3", "requests": 110}]
        merged = models.ModelCatalog().merge_go(go_models=go_models, catalog=catalog)
        self.assertEqual(merged[0]["input_cost"], 1)
        self.assertEqual(merged[0]["output_cost"], 2)

    def test_unlimited_flag_is_merged(self):
        """The unlimited flag propagates through the catalog merge."""
        go_models = [
            {"id": "kimi-k3", "name": "Kimi K3", "requests": 110, "unlimited": True},
        ]
        merged = models.ModelCatalog().merge_go(go_models=go_models, catalog=GO_CATALOG)
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]["unlimited"])
        self.assertEqual(merged[0]["total_cost"], 3.0)
        self.assertEqual(merged[0]["context"], 200000)
        self.assertTrue(merged[0]["reasoning"])

    def test_unmatched_go_model_is_skipped(self):
        """Go models absent from the catalog are dropped."""
        go_models = [{"id": "missing", "name": "Missing", "requests": 10}]
        with redirect_stdout(io.StringIO()):
            merged = models.ModelCatalog().merge_go(go_models=go_models, catalog=GO_CATALOG)
        self.assertEqual(merged, [])


#--------------------------------------------------
# score_go_model
#--------------------------------------------------


class TestScoreGoModel(unittest.TestCase):
    """Tests for score_go_model."""

    def test_free_model_scores_positive(self):
        """Free Go models get a positive score."""
        m = dict(GO_MODEL, total_cost=0)
        self.assertGreater(models.ModelScorer().score_go(model=m), 0.0)

    def test_more_requests_lower_score(self):
        """More monthly requests yield a lower score, all else equal."""
        m1 = dict(GO_MODEL, requests=100)
        m2 = dict(GO_MODEL, requests=1000)
        self.assertGreater(
            models.ModelScorer().score_go(model=m1),
            models.ModelScorer().score_go(model=m2),
        )

    def test_higher_cost_lower_score(self):
        """Higher cost yields a lower score, all else equal."""
        m1 = dict(GO_MODEL, total_cost=1.0)
        m2 = dict(GO_MODEL, total_cost=10.0)
        self.assertGreater(
            models.ModelScorer().score_go(model=m1),
            models.ModelScorer().score_go(model=m2),
        )


#--------------------------------------------------
# print_go_* output
#--------------------------------------------------


class TestPrintGo(unittest.TestCase):
    """Tests for the Go output formatters."""

    def test_go_json_output(self):
        """print_go_json outputs valid JSON with Go fields."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoJsonPrinter().render(models=[GO_MODEL])
        data = json.loads(buf.getvalue())
        self.assertEqual(data[0]["id"], "kimi-k3")
        self.assertEqual(data[0]["requests"], 110)
        self.assertIn("score", data[0])
        self.assertEqual(data[0]["intelligence"], None)

    def test_go_json_includes_intelligence(self):
        """print_go_json carries the intelligence field when attached."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoJsonPrinter().render(models=GO_INTEL_MODELS)
        data = json.loads(buf.getvalue())
        self.assertEqual(data[0]["intelligence"], None)
        self.assertEqual(data[1]["intelligence"], 44.0)

    def test_go_markdown_output(self):
        """print_go_markdown outputs a markdown table with the source."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoMarkdownPrinter().render(models=[GO_MODEL])
        output = buf.getvalue()
        self.assertIn("| Model | Requests |", output)
        self.assertIn("Kimi K3", output)
        self.assertIn(models.GoFetcher.URL, output)

    def test_go_markdown_intel_column(self):
        """print_go_markdown adds an Intel column when requested."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoMarkdownPrinter().render(models=GO_INTEL_MODELS, show_intel=True)
        output = buf.getvalue()
        self.assertIn("| Cap | Intel | Score |", output)
        self.assertIn("| 44.0 |", output)
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoMarkdownPrinter().render(models=GO_INTEL_MODELS)
        self.assertNotIn("Intel", buf.getvalue())

    def test_go_csv_output(self):
        """print_go_csv outputs a header and one row per model."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoCsvPrinter().render(models=[GO_MODEL])
        lines = buf.getvalue().strip().split("\n")
        self.assertEqual(len(lines), 2)
        self.assertIn("model,requests", lines[0])
        self.assertIn("Kimi K3", lines[1])

    def test_go_csv_intelligence_column(self):
        """print_go_csv carries intelligence between attachment and score."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoCsvPrinter().render(models=[GO_MODEL])
        cols = buf.getvalue().split("\n")[0].split(",")
        self.assertGreater(cols.index("intelligence"), cols.index("attachment"))
        self.assertLess(cols.index("intelligence"), cols.index("score"))

    def test_go_table_output(self):
        """print_go_table outputs the model and the source link."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoTablePrinter().render(models=[GO_MODEL])
        output = buf.getvalue()
        self.assertIn("Kimi K3", output)
        self.assertIn("Requests", output)
        self.assertNotIn("Intel", output)

    def test_go_table_intel_column(self):
        """print_go_table shows the Intel column only when requested."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoTablePrinter().render(models=GO_INTEL_MODELS, show_intel=True)
        output = buf.getvalue()
        self.assertIn("Intel", output)
        self.assertIn("44.0", output)

    def test_go_json_empty(self):
        """print_go_json with no models prints an empty list."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoJsonPrinter().render(models=[])
        self.assertEqual(json.loads(buf.getvalue()), [])

    def test_go_table_default_score_unchanged(self):
        """Without --value the table keeps the legacy usage-adjusted score."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoTablePrinter().render(models=[GO_MODEL])
        self.assertIn("1.03", buf.getvalue())

    def test_go_table_value_score(self):
        """The table Score cell shows the throughput share with --value."""
        ranked = dict(GO_MODEL, intelligence=44.0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoTablePrinter().render(models=[ranked], value_score=True)
        self.assertIn("1.0000", buf.getvalue())

    def test_go_table_value_shares(self):
        """Value shares are relative to the strongest model in the list."""
        base = dict(GO_MODEL, id="base", name="Base", intelligence=44.0,
                    requests=110)
        double = dict(GO_MODEL, id="twice", name="Twice", intelligence=44.0,
                      requests=220)
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoTablePrinter().render(models=[double, base], value_score=True)
        output = buf.getvalue()
        self.assertIn("1.0000", output)
        self.assertIn("0.5000", output)

    def test_go_table_value_unlimited(self):
        """Unlimited-allowance models cap at the 1.0 share in --value mode."""
        ranked = dict(GO_MODEL, intelligence=44.0, unlimited=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoTablePrinter().render(models=[ranked], value_score=True)
        self.assertIn("1.0000", buf.getvalue())

    def test_go_markdown_value_score(self):
        """The markdown Score cell shows the throughput share with --value."""
        ranked = dict(GO_MODEL, intelligence=44.0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoMarkdownPrinter().render(models=[ranked], show_intel=True, value_score=True)
        self.assertIn("| 1.0000 |", buf.getvalue())

    def test_go_csv_value_score(self):
        """CSV score shows the 4-decimal throughput share with --value."""
        base = dict(GO_MODEL, id="base", name="Base", intelligence=44.0,
                    requests=110)
        double = dict(GO_MODEL, id="twice", name="Twice", intelligence=44.0,
                      requests=220)
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoCsvPrinter().render(models=[double, base], value_score=True)
        lines = buf.getvalue().strip().split("\n")
        self.assertIn(",1.0000", lines[1])
        self.assertIn(",0.5000", lines[2])

    def test_go_json_value_score(self):
        """JSON score carries the 4-decimal throughput share with --value."""
        base = dict(GO_MODEL, id="base", name="Base", intelligence=44.0,
                    requests=110)
        double = dict(GO_MODEL, id="twice", name="Twice", intelligence=44.0,
                      requests=220)
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoJsonPrinter().render(models=[double, base], value_score=True)
        scores = [row["score"] for row in json.loads(buf.getvalue())]
        self.assertEqual(scores, [1.0, 0.5])

    def test_go_json_value_unranked_null(self):
        """Models without intelligence carry a null score in --value JSON."""
        unranked = dict(GO_MODEL, intelligence=None)
        buf = io.StringIO()
        with redirect_stdout(buf):
            models.GoJsonPrinter().render(models=[unranked], value_score=True)
        self.assertIsNone(json.loads(buf.getvalue())[0]["score"])


#--------------------------------------------------
# --go flag parsing
#--------------------------------------------------


class TestGoFlag(unittest.TestCase):
    """Tests for --go flag parsing."""

    def test_go_flag(self):
        """--go sets go=True."""
        app = models.App(author='test', title='test', description='test')
        parser = app.build_parser()
        args = parser.parse_args(["--go"])
        self.assertTrue(args.go)

    def test_go_flag_default_false(self):
        """go defaults to False."""
        app = models.App(author='test', title='test', description='test')
        parser = app.build_parser()
        args = parser.parse_args([])
        self.assertFalse(args.go)


#--------------------------------------------------
# --cache flag
#--------------------------------------------------


class TestCacheFlag(unittest.TestCase):
    """Tests for the --cache flag and Cache.clear."""

    def setUp(self):
        """Create a temporary directory for cache tests."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_cache_flag(self):
        """--cache sets cache=True."""
        app = models.App(author='test', title='test', description='test')
        parser = app.build_parser()
        args = parser.parse_args(["--cache"])
        self.assertTrue(args.cache)

    def test_cache_flag_default_false(self):
        """cache defaults to False."""
        app = models.App(author='test', title='test', description='test')
        parser = app.build_parser()
        args = parser.parse_args([])
        self.assertFalse(args.cache)

    def test_clear_removes_cache_dir(self):
        """Cache.clear removes the whole cache directory."""
        cache = models.Cache()
        cache.cache_dir = Path(self.tmp.name)
        (cache.cache_dir / "2020-01-01_00-00-00_models.json").write_text("{}", encoding="utf-8")
        cache.clear()
        self.assertFalse(cache.cache_dir.exists())

    def test_clear_missing_dir_is_noop(self):
        """Cache.clear on a missing directory does not raise."""
        cache = models.Cache()
        cache.cache_dir = Path(self.tmp.name) / "does-not-exist"
        cache.clear()
        self.assertFalse(cache.cache_dir.exists())


if __name__ == '__main__':
    unittest.main()
