"""ComfyUI settings the generator needs, applied when ComfyUI loads it.

ComfyUI 0.42's model compiler (CUDA graphs recorded over its dynamic VRAM) can stop at the first step of a
pass whose picture size it hasn't seen, "Model Initializing ..." for good: seen twice in a row on FLUX 3's
closer look at a sword's hilt. The generator turns the compiler off, the same as starting ComfyUI with
--disable-comfy-compiler, unless data/settings.json says {"comfy_compiler": true}.
"""
import logging
import os

from .paths import DATA
from .util import read_json


def settings():
    return read_json(os.path.join(DATA, 'settings.json')) or {}


def apply():
    if settings().get('comfy_compiler'):
        return
    try:
        from comfy.cli_args import args
    except Exception:  # outside ComfyUI
        return
    if hasattr(args, 'disable_comfy_compiler') and not args.disable_comfy_compiler:
        args.disable_comfy_compiler = True
        args.disable_cuda_graphs = True
        logging.info('[EA] The Comfy model compiler is off for the scene generator '
                     '(data/settings.json with "comfy_compiler": true turns it back on).')
