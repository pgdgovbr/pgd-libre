"""Testes do enum ENVIRONMENT (development | demo | production)."""

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_environment_default_eh_development():
    s = Settings()
    assert s.ENVIRONMENT == "development"


def test_environment_aceita_demo(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "demo")
    s = Settings()
    assert s.ENVIRONMENT == "demo"
    assert s.is_demo() is True


def test_environment_aceita_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    s = Settings()
    assert s.ENVIRONMENT == "production"
    assert s.is_demo() is False


def test_environment_rejeita_valor_arbitrario(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    with pytest.raises(ValidationError):
        Settings()


def test_is_demo_falso_em_development():
    s = Settings()
    assert s.is_demo() is False
