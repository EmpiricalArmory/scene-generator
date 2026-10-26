"""Scene settings and the prompts made from them.

Every setting has a short label for the page and the words that go into the prompt. The prompt is
written as an edit of the model's input picture, which shows the product alone on a plain backdrop.
It ends by naming what stays: the product, which is held in place and later pasted back as photographed.
"""

PLACES = [
    ('brick', 'Old brick wall', 'an old red-brick wall with worn lime mortar'),
    ('plaster', 'Lime plaster', 'a lime-washed plaster wall, warm off-white and patchy with age'),
    ('oak-door', 'Oak door', 'a weathered oak plank door with dark iron studs'),
    ('stone', 'Stone wall', 'a rough wall of grey and ochre fieldstone'),
    ('reeds', 'Reeds and sky', 'tall dry reeds under a pale overcast sky'),
    ('hedge', 'Yew hedge', 'a dark green clipped yew hedge'),
    ('winter', 'Winter wood', 'a winter wood with snow on the ground and bare trees'),
    ('grass', 'Autumn field', 'a field of dry autumn grass'),
    ('salle', 'Fencing hall', 'an old fencing hall with a worn wooden floor and tall windows'),
    ('workshop', 'Workshop', "a sword-maker's workshop: an oak workbench, hand tools and leather offcuts"),
    ('oak-table', 'Oak table', 'an old oak table, its grain worn smooth'),
    ('linen', 'Linen cloth', 'a rumpled cloth of natural, undyed linen'),
    ('paper', 'Cream paper', 'a seamless cream paper backdrop that curves down into the floor, as in a studio'),
]

LIGHTS = [
    ('overcast', 'Overcast daylight', 'soft overcast daylight from the left, with gentle shadows'),
    ('window', 'Window light', 'soft window light from the left; the far side falls gently into shade'),
    ('late-sun', 'Late sun behind', 'low late-afternoon sun from behind and to the left, a warm rim of light, the front in open shade'),
    ('shade', 'Open shade', 'open shade on a bright day, soft and even'),
    ('studio', 'Studio softbox', 'one large softbox high on the left and a white card filling from the right, as in a studio product photograph'),
]

PEOPLE = [
    ('none', 'Nobody'),
    ('hand', 'One gloved hand'),
    ('hands', 'Two gloved hands'),
    ('fencer', 'A masked fencer'),
    ('pair', 'Two masked fencers'),
]

POSES = {
    'instrument': [
        ('held-up', 'Held up, like SIGI\'s covers'),
        ('guard', 'In a guard'),
        ('shoulder', 'On the shoulder'),
        ('palms', 'Across the palms'),
        ('leaning', 'Leaning on a wall'),
        ('lying', 'Lying on a surface'),
    ],
    'worn': [
        ('lying', 'Lying on a surface'),
        ('hanging', 'Hanging on a peg'),
        ('in-hand', 'Held in a hand'),
        ('with-kit', 'With other kit on a bench'),
    ],
}

HEIGHTS = [
    ('low', 'Low', 'from a low angle, looking slightly up'),
    ('eye', 'Eye level', 'at eye level'),
    ('high', 'From above', 'from slightly above, looking down at about 30 degrees'),
    ('overhead', 'Overhead', 'from directly above, looking straight down'),
]
LENSES = [('35', '35 mm'), ('50', '50 mm'), ('85', '85 mm'), ('135', '135 mm')]
APERTURES = [
    ('1.8', 'f/1.8', 'at f/1.8, the background very soft'),
    ('2.8', 'f/2.8', 'at f/2.8, the background softly out of focus'),
    ('5.6', 'f/5.6', 'at f/5.6, the background a little soft'),
    ('11', 'f/11', 'at f/11, sharp from front to back'),
]
FRAMINGS = [('close', 'Close'), ('half', 'Waist up'), ('full', 'Full figure')]

KIT = ('black HEMA kit: a padded black fencing jacket, black padded gloves, and a black fencing mask '
       'whose mesh hides the whole face')

NEGATIVE = ('face, uncovered face, eyes, text, letters, watermark, logo, signature, a second sword, extra blade, '
            'duplicate gear, bent or broken blade, deformed hands, extra fingers, fused fingers, cartoon, illustration, '
            'painting, 3D render, CGI, plastic look, oversaturated colours, colour cast, vignette, frame, border')

# Presets set a pose, people and a layout; the rest of the settings stay as the person left them.
PRESETS = [
    {'id': 'cover', 'label': 'Held up, like SIGI\'s covers', 'kind': 'instrument',
     'scene': {'pose': 'held-up', 'people': 'hand', 'place': 'brick', 'light': 'overcast', 'height': 'eye', 'lens': '85', 'aperture': '2.8', 'side': 'right'},
     'layout': {'aspect': '4:5', 'cx': 0.5, 'cy': 0.5, 'length': 0.9, 'point': 'up'}},
    {'id': 'guard', 'label': 'In a guard', 'kind': 'instrument',
     'scene': {'pose': 'guard', 'people': 'fencer', 'place': 'salle', 'light': 'window', 'height': 'eye', 'lens': '50', 'aperture': '2.8', 'framing': 'half'},
     'layout': {'aspect': '4:5', 'cx': 0.44, 'cy': 0.44, 'length': 0.78, 'point': 'up-left'}},
    {'id': 'leaning', 'label': 'Leaning on a wall', 'kind': 'instrument',
     'scene': {'pose': 'leaning', 'people': 'none', 'place': 'plaster', 'light': 'window', 'height': 'eye', 'lens': '50', 'aperture': '5.6'},
     'layout': {'aspect': '4:5', 'cx': 0.5, 'cy': 0.5, 'length': 0.9, 'point': 'up', 'tilt': 6}},
    {'id': 'table', 'label': 'On the table', 'kind': 'any',
     'scene': {'pose': 'lying', 'people': 'none', 'place': 'oak-table', 'light': 'window', 'height': 'overhead', 'lens': '50', 'aperture': '11'},
     'layout': {'aspect': '4:5', 'cx': 0.5, 'cy': 0.5, 'length': 0.82, 'point': 'diagonal'}},
    {'id': 'studio', 'label': 'Studio, cream paper', 'kind': 'any',
     'scene': {'pose': 'lying', 'people': 'none', 'place': 'paper', 'light': 'studio', 'height': 'overhead', 'lens': '85', 'aperture': '11'},
     'layout': {'aspect': '1:1', 'cx': 0.5, 'cy': 0.5, 'length': 0.7, 'point': 'keep'}},
]


def _pick(table, key, default=None):
    for row in table:
        if row[0] == key:
            return row
    return default or table[0]


def options():
    return {
        'places': [{'id': a, 'label': b, 'text': c} for a, b, c in PLACES],
        'lights': [{'id': a, 'label': b, 'text': c} for a, b, c in LIGHTS],
        'people': [{'id': a, 'label': b} for a, b in PEOPLE],
        'poses': {k: [{'id': a, 'label': b} for a, b in v] for k, v in POSES.items()},
        'heights': [{'id': a, 'label': b} for a, b, _ in HEIGHTS],
        'lenses': [{'id': a, 'label': b} for a, b in LENSES],
        'apertures': [{'id': a, 'label': b} for a, b, _ in APERTURES],
        'framings': [{'id': a, 'label': b} for a, b in FRAMINGS],
        'presets': PRESETS,
        'negative': NEGATIVE,
    }


def noun_of(product):
    n = (product.get('noun') or '').strip()
    if n:
        return n
    return {'instrument': 'sword', 'gloves': 'pair of gloves', 'mask': 'fencing mask', 'jacket': 'jacket'}.get(product.get('kind'), 'piece of gear')


def _subject(s, noun, kind):
    pose = s.get('pose', 'held-up' if kind == 'instrument' else 'lying')
    people = s.get('people', 'none')
    side = s.get('side', 'right')
    framing = {'close': 'framed close', 'half': 'framed from the waist up', 'full': 'the whole figure in the frame'}.get(s.get('framing', 'half'))
    the = 'the ' + noun
    if pose == 'held-up':
        if people in ('hand', 'hands', 'none'):
            return (f'{the.capitalize()} stands upright where it is, point up, held by one hand in a black padded fencing glove '
                    f'that comes in from the {side} edge of the frame and grips the handle just below the cross guard; only the '
                    f'gloved hand and the forearm, in the sleeve of a black fencing jacket, come into the frame')
        return f'A fencer in {KIT} holds {the} upright where it is, point up, the gloved hands on the handle, {framing}'
    if pose == 'guard':
        who = 'two fencers, each in ' + KIT + ',' if people == 'pair' else 'a fencer in ' + KIT + ','
        return (f'{who[0].upper() + who[1:]} holds {the} where it is with both gloved hands on the handle, in a fencing guard, '
                f'{framing}; the body turned to match the angle of the blade')
    if pose == 'shoulder':
        return f'A fencer in {KIT} rests {the} on the shoulder where it is, one gloved hand on the handle, {framing}'
    if pose == 'palms':
        return f'{the.capitalize()} lies across two open hands in black padded fencing gloves, presented to the camera, only the hands and forearms in the frame'
    if pose == 'leaning':
        return f'{the.capitalize()} leans against the wall where it is, point up, its pommel resting on the floor, nobody in the frame'
    if pose == 'hanging':
        return f'{the.capitalize()} hangs from a wooden peg on the wall where it is, nobody in the frame'
    if pose == 'in-hand':
        return f'{the.capitalize()} is held where it is by one bare hand that comes in from the {side} edge of the frame, only the hand and the wrist in the frame'
    if pose == 'with-kit':
        return f'{the.capitalize()} lies where it is on a wooden bench, beside a black fencing mask and a rolled black fencing jacket, nobody in the frame'
    # lying
    if people in ('hand', 'hands'):
        return f'{the.capitalize()} lies where it is on the surface, one gloved hand resting beside it'
    return f'{the.capitalize()} lies where it is on the surface, with a soft natural shadow under it, nobody in the frame'


def prompt(s, product, family='qwen'):
    """The prompt for a scene `s` (a dict of setting ids) and a product (its json)."""
    if s.get('custom'):
        return s['custom'].strip()
    noun = noun_of(product)
    kind = product.get('kind') or 'other'
    place = s.get('place_text') or _pick(PLACES, s.get('place', 'brick'))[2]
    light = s.get('light_text') or _pick(LIGHTS, s.get('light', 'overcast'))[2]
    height = _pick(HEIGHTS, s.get('height', 'eye'))[2]
    lens = _pick(LENSES, s.get('lens', '85'))[1]
    aperture = _pick(APERTURES, s.get('aperture', '2.8'))[2]
    backdrop = 'light' if sum(product.get('backdrop') or [0.9, 0.9, 0.9]) / 3 > 0.6 else 'plain'
    parts = [
        f'Replace the plain {backdrop} background with a real photograph taken in front of {place}' if s.get('pose') not in ('lying', 'with-kit')
        else f'Replace the plain {backdrop} background with a real photograph of {place}',
        _subject(s, noun, kind),
        'Light: ' + light,
        f'Shot {height} with {"an" if lens.startswith("8") else "a"} {lens} lens {aperture}',
        'Natural, muted colours and true-to-life textures, as in an unretouched photograph; no text',
    ]
    if s.get('people', 'none') in ('fencer', 'pair'):
        parts.append('Every face stays hidden behind a black fencing mask')
    if s.get('extra'):
        parts.append(s['extra'].strip().rstrip('.'))
    parts.append(f'Keep the {noun} exactly as it is in the picture: the same position, size, angle, shape, colours and every detail')
    text = '. '.join(p.strip().rstrip('.') for p in parts if p) + '.'
    if family == 'flux3':
        # FLUX 3 reads frame-relative directions and plain description best; its prompts carry no quality words anyway.
        return text
    return text


def negative(s):
    return s.get('negative') if s.get('negative') is not None else NEGATIVE
