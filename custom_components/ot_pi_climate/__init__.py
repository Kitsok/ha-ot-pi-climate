"""OpenTherm PI Climate integration."""

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.storage import Store

from .const import CONF_SERIAL_PORT, CONF_TEMPERATURE_ENTITY, DOMAIN, PLATFORMS
from .controller import PIController
from .coordinator import OpenThermCoordinator
from .gateway import OpenThermGateway
from .models import OpenThermConfigEntry, OpenThermRuntimeData, merged_config

STORAGE_VERSION = 1


async def async_setup_entry(hass: HomeAssistant, entry: OpenThermConfigEntry) -> bool:
    """Set up OpenTherm PI Climate from a config entry."""

    config = merged_config(entry)
    store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    controller = PIController(config)
    controller.restore(await store.async_load())
    gateway = OpenThermGateway(config[CONF_SERIAL_PORT])
    coordinator = OpenThermCoordinator(hass, gateway, controller, config[CONF_TEMPERATURE_ENTITY])
    entry.runtime_data = OpenThermRuntimeData(gateway, controller, coordinator)

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_stop(_event: Event) -> None:
        await store.async_save(controller.as_dict())
        await gateway.async_close()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop))
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OpenThermConfigEntry) -> bool:
    """Unload a config entry."""

    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
    await store.async_save(entry.runtime_data.controller.as_dict())
    await entry.runtime_data.gateway.async_close()
    return True


async def async_reload_entry(hass: HomeAssistant, entry: OpenThermConfigEntry) -> None:
    """Reload automatically after options are changed."""

    await hass.config_entries.async_reload(entry.entry_id)
