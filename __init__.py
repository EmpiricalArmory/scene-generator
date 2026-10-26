"""Empirical Armory scene generator, a ComfyUI extension.

Serves the generator at http://127.0.0.1:8188/ea/ and the API it uses under /ea/api/.
The model draws the product into each scene from its photos, then a detail pass redraws it
against them; "Exact photo" keeps the photo as taken and builds the scene around it.
"""
from .ea_scene import VERSION, runtime
from .ea_scene import api  # noqa: F401  the API first,
from .ea_scene import page  # noqa: F401  then the page and data files, whose routes catch the rest of /ea/
from .ea_scene.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

runtime.apply()

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'VERSION']
