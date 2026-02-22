"""
Tests for recommender _score_candidate to handle None scores gracefully.
Validates the fix for TypeError when candidate_score is None.
"""
import pytest
from app.services.recommender import LocalRecommender


def _make_profile(avg_score=75.0):
    return {
        'genres': {'Action': 5, 'Drama': 3},
        'authors': {'Author A'},
        'avg_score': avg_score,
        'anilist_ids': set(),
        'content_types': {'manga'},
    }


def test_score_candidate_with_none_score():
    """candidate.get('score') returns None (key exists, value=None) — must not crash."""
    recommender = LocalRecommender()
    candidate = {
        'genres': ['Action'],
        'authors': [],
        'score': None,
    }
    profile = _make_profile(avg_score=75.0)
    score = recommender._score_candidate(candidate, profile)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_score_candidate_with_missing_score_key():
    """When 'score' key is missing entirely, should use avg_score as fallback."""
    recommender = LocalRecommender()
    candidate = {
        'genres': ['Action', 'Drama'],
        'authors': ['Author A'],
    }
    profile = _make_profile(avg_score=80.0)
    score = recommender._score_candidate(candidate, profile)
    assert isinstance(score, float)
    assert score > 0


def test_score_candidate_with_zero_score():
    """Score of 0 is valid and should not be replaced by avg_score."""
    recommender = LocalRecommender()
    candidate = {
        'genres': ['Action'],
        'authors': [],
        'score': 0,
    }
    profile = _make_profile(avg_score=75.0)
    score = recommender._score_candidate(candidate, profile)
    assert isinstance(score, float)
    expected_score_sim = 1.0 - abs(0 - 75.0) / 100.0
    assert expected_score_sim == 0.25
    assert score == pytest.approx(0.5 * 0.5 + 0.0 * 0.3 + 0.25 * 0.2, abs=0.01)


def test_score_candidate_with_none_avg_score_in_profile():
    """If profile avg_score is also None, should not crash."""
    recommender = LocalRecommender()
    candidate = {
        'genres': ['Action'],
        'authors': [],
        'score': None,
    }
    profile = _make_profile(avg_score=None)
    profile['avg_score'] = None
    score = recommender._score_candidate(candidate, profile)
    assert isinstance(score, float)


def test_score_candidate_normal_values():
    """Normal case with valid scores should produce expected result."""
    recommender = LocalRecommender()
    candidate = {
        'genres': ['Action', 'Drama'],
        'authors': ['Author A'],
        'score': 80,
    }
    profile = _make_profile(avg_score=80.0)
    score = recommender._score_candidate(candidate, profile)
    genre_overlap = 2 / 2  # both genres match
    author_match = 1.0
    score_sim = 1.0 - abs(80 - 80.0) / 100.0  # perfect match
    expected = genre_overlap * 0.5 + author_match * 0.3 + score_sim * 0.2
    assert score == pytest.approx(expected, abs=0.01)
