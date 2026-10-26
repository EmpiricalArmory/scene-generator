"""Empirical Armory scene generator, a ComfyUI extension.

Serves the generator at http://127.0.0.1:8188/ea/ and the API it uses under /ea/api/.
The product photo is never redrawn: the model makes the place, the people and the light
around it, and the original pixels are put back on top.
"""
from .ea_scene import VERSION
from .ea_scene import routes  # noqa: F401  (registers the API, then the page)
from .ea_scene.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'VERSION']
