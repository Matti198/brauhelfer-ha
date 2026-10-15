from custom_components.brauhelfer.const import DOMAIN  # noqa
import shutil
from pathlib import Path
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
import pytest

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield

async def test_de_ids(hass: HomeAssistant, tmp_path):
    hass.config.language = "de"
    p = tmp_path / "kb.sqlite"; shutil.copy(Path(__file__).parent / "kb_daten.sqlite", p)
    e = MockConfigEntry(domain="brauhelfer", data={"path": str(p)}); e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id); await hass.async_block_till_done()
    print(sorted(hass.states.async_entity_ids()))
