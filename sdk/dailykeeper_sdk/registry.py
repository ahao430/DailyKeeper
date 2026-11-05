"""Plugin registry for discovering and storing DailyKeeper platform plugins."""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

from dailykeeper_sdk.base import PlatformPlugin

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "dailykeeper.plugins"


class PluginRegistry:
    """Registry that stores platform plugin instances, keyed by ``plugin_id``."""

    def __init__(self) -> None:
        self._plugins: dict[str, PlatformPlugin] = {}

    def register(self, plugin: PlatformPlugin | type[PlatformPlugin]) -> PlatformPlugin:
        """Register a plugin instance (a plugin class is instantiated automatically).

        Usable as a class decorator; returns the plugin instance.
        """
        if isinstance(plugin, type):
            plugin = plugin()
        plugin_id = getattr(plugin, "plugin_id", "")
        if not plugin_id:
            raise ValueError(f"{type(plugin).__name__} 缺少 plugin_id，无法注册")
        existing = self._plugins.get(plugin_id)
        if existing is not None and type(existing) is not type(plugin):
            logger.warning("plugin_id %s 重复注册，覆盖旧插件 %s", plugin_id, type(existing).__name__)
        self._plugins[plugin_id] = plugin
        return plugin
        self._plugins[plugin_id] = plugin
        return plugin

    def get(self, plugin_id: str) -> PlatformPlugin | None:
        """Return the registered plugin instance for ``plugin_id``, or None."""
        return self._plugins.get(plugin_id)

    def all(self) -> dict[str, PlatformPlugin]:
        """Return a copy of all registered plugin classes keyed by plugin_id."""
        return dict(self._plugins)

    def has(self, plugin_id: str) -> bool:
        """Return True if ``plugin_id`` is registered."""
        return plugin_id in self._plugins

    def load_entry_points(self, group: str = ENTRY_POINT_GROUP) -> list[PlatformPlugin]:
        """Load and register plugin instances advertised via importlib entry points.

        Broken or invalid entry points are skipped with a warning log instead of
        failing the whole scan. Returns the list of newly loaded plugin instances.
        """
        loaded: list[type[PlatformPlugin]] = []
        try:
            eps = entry_points(group=group)
        except TypeError:  # Python < 3.10: entry_points() accepts no kwargs
            eps = entry_points().get(group, [])
        for entry_point in eps:
            try:
                plugin_class = entry_point.load()
            except Exception:
                logger.warning(
                    "跳过无法加载的插件入口点 %s (%s)", entry_point.name, entry_point.value, exc_info=True
                )
                continue
            if not (isinstance(plugin_class, type) and issubclass(plugin_class, PlatformPlugin)):
                logger.warning("跳过非 PlatformPlugin 的插件入口点 %s (%s)", entry_point.name, entry_point.value)
                continue
            self.register(plugin_class)
            loaded.append(plugin_class)
        return loaded


plugin_registry = PluginRegistry()
