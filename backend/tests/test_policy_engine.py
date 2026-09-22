import pytest
from backend.app.policies.loader import load_sops
from backend.app.policies.engine import DeterministicSOPEngine
from backend.app.policies.models import SOPDefinition, SOPMatch, ConditionsBlock, ComparisonRule


class TestDeterministicSOPEngine:
    """Comprehensive unit tests for DeterministicSOPEngine."""

    @pytest.fixture
    def engine(self):
        """Create engine with loaded SOPs."""
        sops = load_sops()
        return DeterministicSOPEngine(sops)

    @pytest.fixture
    def sample_weather_hot(self):
        """Sample weather facts: hot conditions."""
        return {
            "temperature": 38,
            "humidity": 65,
            "wind_speed": 5,
            "air_quality_index": 75,
            "weather_condition": "clear",
            "solar_radiation": 850,
            "precipitation": None
        }

    @pytest.fixture
    def sample_weather_moderate(self):
        """Sample weather facts: moderate conditions."""
        return {
            "temperature": 28,
            "humidity": 70,
            "wind_speed": 10,
            "air_quality_index": 50,
            "weather_condition": "cloudy",
            "solar_radiation": 500,
            "precipitation": None
        }

    @pytest.fixture
    def sample_weather_cold_windy(self):
        """Sample weather facts: cold and windy."""
        return {
            "temperature": 3,
            "humidity": 50,
            "wind_speed": 30,
            "air_quality_index": 40,
            "weather_condition": "windy",
            "solar_radiation": 200,
            "precipitation": None
        }

    @pytest.fixture
    def sample_weather_icy(self):
        """Sample weather facts: icy conditions."""
        return {
            "temperature": -8,
            "humidity": 80,
            "wind_speed": 15,
            "air_quality_index": 30,
            "weather_condition": "snowing",
            "solar_radiation": 100,
            "precipitation": "ice"
        }

    @pytest.fixture
    def sample_weather_poor_air(self):
        """Sample weather facts: poor air quality."""
        return {
            "temperature": 30,
            "humidity": 75,
            "wind_speed": 5,
            "air_quality_index": 220,
            "weather_condition": "haze",
            "solar_radiation": 600,
            "precipitation": None
        }

    @pytest.fixture
    def sample_weather_thunderstorm(self):
        """Sample weather facts: thunderstorm."""
        return {
            "temperature": 25,
            "humidity": 90,
            "wind_speed": 40,
            "air_quality_index": 60,
            "weather_condition": "thunderstorm",
            "solar_radiation": 50,
            "precipitation": "rain"
        }

    # ===== SIMPLE SOP MATCH TESTS =====

    def test_simple_sop_match_cycling_hot(self, engine, sample_weather_hot):
        """Test simple SOP match: cycling in extreme heat."""
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="cycling",
            category="outdoor_exercise"
        )
        # At 38°C, should match cycling heat SOP or general heat SOP
        assert len(matches) > 0
        sop_ids = [m.sop_id for m in matches]
        # Should match at least one general or cycling-specific SOP
        assert any(sid in sop_ids for sid in ["SOP-CYC-001", "SOP-GEN-001", "SOP-GEN-002"])

    def test_simple_sop_match_running_hot(self, engine, sample_weather_hot):
        """Test simple SOP match: running in extreme heat."""
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="running",
            category="outdoor_exercise"
        )
        assert len(matches) > 0
        sop_ids = [m.sop_id for m in matches]
        assert "SOP-RUN-001" in sop_ids  # Should match running in extreme heat

    def test_simple_sop_match_walking_moderate_heat(self, engine, sample_weather_moderate):
        """Test simple SOP match: walking in moderate heat."""
        matches = engine.match_all(
            weather_facts=sample_weather_moderate,
            activity="walking",
            category="home_and_leisure"
        )
        assert len(matches) > 0
        sop_ids = [m.sop_id for m in matches]
        assert "SOP-WALK-001" in sop_ids  # Should match walking in moderate heat

    # ===== NO SOP MATCH TESTS =====

    def test_no_sop_match_indoor_activity(self, engine, sample_weather_hot):
        """Test no SOP match: indoor activity."""
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="painting bedroom",
            category="home_and_leisure"
        )
        # Indoor activity should not match outdoor SOPs
        assert len(matches) == 0

    def test_no_sop_match_cool_weather_cycling(self, engine):
        """Test no SOP match: cycling in cool weather."""
        cool_weather = {
            "temperature": 15,
            "humidity": 60,
            "wind_speed": 8,
            "air_quality_index": 40,
            "weather_condition": "clear",
            "solar_radiation": 300,
            "precipitation": None
        }
        matches = engine.match_all(
            weather_facts=cool_weather,
            activity="cycling",
            category="outdoor_exercise"
        )
        # Cool weather with low AQI should match no specific SOPs (or only general ones)
        sop_ids = [m.sop_id for m in matches]
        # Should not match heat/poor air SOPs
        assert "SOP-CYC-001" not in sop_ids

    # ===== MULTIPLE SOP MATCH TESTS =====

    def test_multiple_sop_matches(self, engine, sample_weather_hot):
        """Test multiple SOP matches are returned."""
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="running",
            category="outdoor_exercise"
        )
        # Hot weather should match multiple SOPs (extreme heat, general heat combo, etc.)
        assert len(matches) >= 1

    def test_multiple_matches_sorted_by_severity(self, engine, sample_weather_hot):
        """Test multiple matches are sorted by severity."""
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="running",
            category="outdoor_exercise"
        )
        if len(matches) > 1:
            # Verify sorted by severity (highest first)
            from backend.app.policies.models import SEVERITY_WEIGHTS
            for i in range(len(matches) - 1):
                weight_i = SEVERITY_WEIGHTS.get(matches[i].severity, 0)
                weight_next = SEVERITY_WEIGHTS.get(matches[i + 1].severity, 0)
                assert weight_i >= weight_next

    # ===== SEVERITY-BASED RESOLUTION TESTS =====

    def test_severity_based_resolution_extreme_heat(self, engine, sample_weather_hot):
        """Test resolution selects highest severity SOP."""
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="running",
            category="outdoor_exercise"
        )
        selected, trace = engine.resolve(matches)
        
        if selected:
            # Extreme heat (38°C) for running should be SEVERE
            assert selected.severity in ["severe", "high"]
            assert len(trace) > 0

    def test_severity_based_resolution_trace_output(self, engine, sample_weather_hot):
        """Test resolution includes decision trace."""
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="running",
            category="outdoor_exercise"
        )
        selected, trace = engine.resolve(matches)
        
        assert isinstance(trace, list)
        assert len(trace) > 0
        # Trace should mention selected SOP ID
        if selected:
            assert any(selected.sop_id in str(t) for t in trace)

    # ===== PRIORITY-BASED RESOLUTION TESTS =====

    def test_priority_based_resolution(self, engine, sample_weather_hot):
        """Test resolution uses priority as tiebreaker."""
        # When multiple SOPs have same severity, highest priority wins
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="running",
            category="outdoor_exercise"
        )
        selected, trace = engine.resolve(matches)
        
        if len(matches) > 1:
            # All should be sorted by priority within same severity
            same_severity_matches = [m for m in matches if m.severity == matches[0].severity]
            if len(same_severity_matches) > 1:
                for i in range(len(same_severity_matches) - 1):
                    assert same_severity_matches[i].priority >= same_severity_matches[i + 1].priority

    # ===== ACTIVITY-SPECIFIC MATCHING TESTS =====

    def test_activity_specific_matching_cycling(self, engine, sample_weather_hot):
        """Test engine only matches SOPs for specified activity."""
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="cycling",
            category="outdoor_exercise"
        )
        
        for match in matches:
            assert "cycling" in match.guidance.lower() or "general" in match.guidance.lower()

    def test_activity_specific_matching_walking(self, engine, sample_weather_moderate):
        """Test walking-specific SOPs are matched."""
        matches = engine.match_all(
            weather_facts=sample_weather_moderate,
            activity="walking",
            category="home_and_leisure"
        )
        
        sop_ids = [m.sop_id for m in matches]
        assert any("WALK" in sid for sid in sop_ids)

    # ===== AND CONDITION TESTS =====

    def test_and_conditions_all_must_match(self, engine):
        """Test AND conditions: all rules must match."""
        # SOP-CYC-003: temperature < 5 AND wind_speed >= 25 AND activity == cycling
        cold_windy_weather = {
            "temperature": 3,
            "humidity": 50,
            "wind_speed": 30,
            "air_quality_index": 40,
            "weather_condition": "windy",
            "solar_radiation": 200,
            "precipitation": None,
            "activity": "cycling"
        }
        
        matches = engine.match_all(
            weather_facts=cold_windy_weather,
            activity="cycling",
            category="outdoor_exercise"
        )
        
        sop_ids = [m.sop_id for m in matches]
        assert "SOP-CYC-003" in sop_ids

    def test_and_conditions_partial_match_fails(self, engine):
        """Test AND conditions: partial match should fail."""
        # Cold but not windy - should NOT match SOP-CYC-003
        cold_calm_weather = {
            "temperature": 3,
            "humidity": 50,
            "wind_speed": 5,  # Not >= 25
            "air_quality_index": 40,
            "weather_condition": "calm",
            "solar_radiation": 200,
            "precipitation": None
        }
        
        matches = engine.match_all(
            weather_facts=cold_calm_weather,
            activity="cycling",
            category="outdoor_exercise"
        )
        
        sop_ids = [m.sop_id for m in matches]
        assert "SOP-CYC-003" not in sop_ids

    # ===== COMPOSITE/FUZZY POLICY TESTS =====

    def test_composite_score_policy_air_quality(self, engine, sample_weather_poor_air):
        """Test COMPOSITE_SCORE policy matching (poor air quality)."""
        matches = engine.match_all(
            weather_facts=sample_weather_poor_air,
            activity="cycling",
            category="outdoor_exercise"
        )
        
        sop_ids = [m.sop_id for m in matches]
        # At AQI 220 for cycling, should match air quality or general SOP
        assert len(sop_ids) > 0
        # Either cycling air quality SOP or general SOP should match
        assert any(sid in sop_ids for sid in ["SOP-CYC-002", "SOP-GEN-002", "SOP-WALK-002"])

    def test_composite_score_policy_multi_factor_heat(self, engine, sample_weather_hot):
        """Test COMPOSITE_SCORE policy: multiple heat factors."""
        # SOP-GEN-002 combines temperature, humidity, solar_radiation
        high_heat_weather = {
            "temperature": 38,
            "humidity": 85,
            "wind_speed": 5,
            "air_quality_index": 60,
            "weather_condition": "sunny",
            "solar_radiation": 900,  # High solar load
            "precipitation": None
        }
        
        matches = engine.match_all(
            weather_facts=high_heat_weather,
            activity="running",
            category="outdoor_exercise"
        )
        
        sop_ids = [m.sop_id for m in matches]
        # Should match composite heat policy
        assert "SOP-GEN-002" in sop_ids or "SOP-RUN-001" in sop_ids

    def test_composite_score_calculation(self, engine, sample_weather_icy):
        """Test composite score penalty calculation."""
        matches = engine.match_all(
            weather_facts=sample_weather_icy,
            activity="running",
            category="outdoor_exercise"
        )
        
        # At -8°C with ice, should match running on icy conditions or general SOP
        sop_ids = [m.sop_id for m in matches]
        # Should match at least one icy/winter SOP
        assert len(sop_ids) > 0
        assert any(sid in sop_ids for sid in ["SOP-RUN-003", "SOP-GEN-002"])

    # ===== SEVERE WEATHER OVERRIDE TESTS =====

    def test_severe_weather_thunderstorm(self, engine, sample_weather_thunderstorm):
        """Test severe weather (thunderstorm) takes priority."""
        matches = engine.match_all(
            weather_facts=sample_weather_thunderstorm,
            activity="cycling",
            category="outdoor_exercise"
        )
        
        sop_ids = [m.sop_id for m in matches]
        assert "SOP-GEN-001" in sop_ids  # Thunderstorm SOP

    def test_severe_weather_guidance_explicit(self, engine, sample_weather_thunderstorm):
        """Test severe weather guidance is explicit about stopping."""
        matches = engine.match_all(
            weather_facts=sample_weather_thunderstorm,
            activity="cycling",
            category="outdoor_exercise"
        )
        
        for match in matches:
            if match.sop_id == "SOP-GEN-001":
                assert "STOP" in match.guidance or "IMMEDIATELY" in match.guidance

    # ===== YAML-DRIVEN POLICY LOADING TESTS =====

    def test_sops_loaded_from_yaml(self, engine):
        """Test SOPs are loaded from YAML configuration."""
        assert len(engine.sops) > 0
        assert len(engine.sops) >= 10  # Assignment requires >= 10 SOPs

    def test_sop_categories_coverage(self, engine):
        """Test SOPs cover multiple categories."""
        categories = set()
        for sop in engine.sops:
            categories.add(sop.category)
        
        assert len(categories) >= 3  # Assignment requires >= 3 categories

    def test_sop_severity_levels_represented(self, engine):
        """Test SOPs include multiple severity levels."""
        severities = set()
        for sop in engine.sops:
            severities.add(sop.severity)
        
        # Should have low, moderate, high, severe represented
        assert "high" in severities or "severe" in severities

    def test_sop_guidance_not_empty(self, engine):
        """Test all SOPs have guidance text."""
        for sop in engine.sops:
            assert sop.guidance
            assert len(sop.guidance) > 20

    # ===== DYNAMIC POLICY TEST =====

    def test_engine_accepts_new_sops(self):
        """Test engine can be initialized with modified SOP list."""
        sops = load_sops()
        original_count = len(sops)
        
        # Create new engine with subset
        subset_engine = DeterministicSOPEngine(sops[:3])
        assert len(subset_engine.sops) == 3

    def test_policy_change_without_engine_modification(self):
        """Test engine behavior changes with different SOPs."""
        # Load original SOPs
        sops_original = load_sops()
        engine1 = DeterministicSOPEngine(sops_original)
        
        # Test with subset
        engine2 = DeterministicSOPEngine(sops_original[:5])
        
        weather = {
            "temperature": 38,
            "humidity": 70,
            "wind_speed": 10,
            "air_quality_index": 50,
            "weather_condition": "clear",
            "solar_radiation": 800,
            "precipitation": None
        }
        
        matches1 = engine1.match_all(weather, activity="running")
        matches2 = engine2.match_all(weather, activity="running")
        
        # With subset, fewer matches expected
        assert len(matches1) >= len(matches2)

    # ===== RESOLUTION EDGE CASES =====

    def test_resolution_empty_matches(self, engine):
        """Test resolution with no matches."""
        selected, trace = engine.resolve([])
        
        assert selected is None
        assert len(trace) > 0
        assert "No SOPs matched" in trace[0]

    def test_resolution_single_match(self, engine, sample_weather_hot):
        """Test resolution with single match."""
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="running",
            category="outdoor_exercise"
        )
        
        if matches:
            selected, trace = engine.resolve(matches)
            assert selected is not None
            assert selected == matches[0]

    # ===== MATCH REASONS DOCUMENTATION =====

    def test_match_reasons_provided(self, engine, sample_weather_hot):
        """Test match reasons are documented."""
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="running",
            category="outdoor_exercise"
        )
        
        for match in matches:
            assert isinstance(match.reasons, list)
            # Should have reasons for each rule that was evaluated
            if len(match.reasons) > 0:
                for reason in match.reasons:
                    assert reason.field is not None
                    assert reason.operator is not None

    def test_match_reasons_accurate(self, engine, sample_weather_hot):
        """Test match reasons accurately reflect conditions."""
        matches = engine.match_all(
            weather_facts=sample_weather_hot,
            activity="running",
            category="outdoor_exercise"
        )
        
        for match in matches:
            for reason in match.reasons:
                if reason.matched:
                    # If matched, actual should be consistent with threshold
                    assert reason.actual is not None
                    assert reason.threshold is not None
