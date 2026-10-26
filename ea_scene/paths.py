"""Where things live.

Installed by Install.bat, the folder looks like this:

    <root>/ComfyUI_windows_portable/   ComfyUI itself
    <root>/models/                      the model files
    <root>/nodes/scene-generator/       this package
    <root>/data/                        products, references, results, settings
    <root>/setup/                       installer, model list, logs
"""
import os

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(APP, 'web')


def _find_root():
    d = APP
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.isfile(os.path.join(d, 'setup', 'models.json')):
            return d
    return None


ROOT = _find_root()
BASE = ROOT or APP
DATA = os.path.join(BASE, 'data')
MODELS = os.path.join(BASE, 'models')
SETUP = os.path.join(BASE, 'setup')
MANIFEST = os.path.join(SETUP, 'models.json') if ROOT else os.path.join(APP, 'setup', 'models.json')

for _d in (DATA,):
    os.makedirs(_d, exist_ok=True)
