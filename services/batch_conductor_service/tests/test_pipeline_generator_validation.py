from __future__ import annotations

"""Validation tests for :pyclass:`DefaultPipelineGenerator`.

These tests focus solely on static YAML validation – cycles and undefined
dependencies – without hitting any external systems.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from services.batch_conductor_service.implementations.pipeline_generator_impl import (
    DefaultPipelineGenerator,
)
from services.batch_conductor_service.config import Settings


@pytest.fixture()
def tmp_yaml(tmp_path: Path):
    """Utility to write YAML content to a temp file and yield the path."""

    def _factory(content: dict) -> Path:
        file_path = tmp_path / "pipelines.yaml"
        file_path.write_text(yaml.safe_dump(content))
        return file_path

    return _factory


def _make_generator(yaml_path: Path) -> DefaultPipelineGenerator:
    settings = Settings(PIPELINE_CONFIG_PATH=str(yaml_path))
    return DefaultPipelineGenerator(settings)


@pytest.mark.asyncio
async def test_validate_cycles_detected(tmp_yaml):
    """A -> B -> A should raise ValueError."""

    data = {
        "pipelines": {
            "cycle": {
                "description": "cycle",
                "steps": [
                    {
                        "name": "a",
                        "service_name": "svc_a",
                        "event_type": "evt.a",
                        "event_data_model": "M",
                        "depends_on": ["b"],
                    },
                    {
                        "name": "b",
                        "service_name": "svc_b",
                        "event_type": "evt.b",
                        "event_data_model": "M",
                        "depends_on": ["a"],
                    },
                ],
            }
        }
    }
    path = tmp_yaml(data)
    gen = _make_generator(path)

    with pytest.raises(ValueError, match="cycle detected"):
        await gen.validate_pipeline_config()


@pytest.mark.asyncio
async def test_validate_unknown_dependency(tmp_yaml):
    """Step depending on non-existent step triggers ValueError."""

    data = {
        "pipelines": {
            "invalid": {
                "description": "missing dep",
                "steps": [
                    {
                        "name": "a",
                        "service_name": "svc_a",
                        "event_type": "evt.a",
                        "event_data_model": "M",
                        "depends_on": ["ghost"],
                    }
                ],
            }
        }
    }
    path = tmp_yaml(data)
    gen = _make_generator(path)

    with pytest.raises(ValueError, match="unknown step 'ghost'"):
        await gen.validate_pipeline_config()


@pytest.mark.asyncio
async def test_validate_valid_config(tmp_yaml):
    """A simple linear pipeline passes validation."""

    data = {
        "pipelines": {
            "linear": {
                "description": "linear",
                "steps": [
                    {
                        "name": "a",
                        "service_name": "svc_a",
                        "event_type": "evt.a",
                        "event_data_model": "M",
                    },
                    {
                        "name": "b",
                        "service_name": "svc_b",
                        "event_type": "evt.b",
                        "event_data_model": "M",
                        "depends_on": ["a"],
                    },
                ],
            }
        }
    }

    path = tmp_yaml(data)
    gen = _make_generator(path)

    # Should not raise
    result = await gen.validate_pipeline_config()
    assert result is True
