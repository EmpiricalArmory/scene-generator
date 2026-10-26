"""Scene settings and the prompts made from them.

Every setting has a short label for the page and the words that go into the prompt.

Two ways to put the product in a scene:
  natural  the model draws the product from its photos (the first pictures it is given), at the angle,
           size and light the scene needs; a detail pass then redraws the product against the photos.
  exact    the photo itself, at its own angle: the model makes the scene around it, a relight pass lets the
           scene's light fall on it, and the photo's fine detail is put back on top.
"""
import json

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
        ('worn-hands', 'Worn: hands and forearms'),
        ('worn-head', 'Worn: head and shoulders'),
        ('worn-torso', 'Worn: the torso'),
        ('worn-guard', 'Worn: in a guard, full figure'),
    ],
}

# Poses where the gear is worn: only the natural way works (a photo cannot be bent onto a body).
WORN = {'worn-hands', 'worn-head', 'worn-torso', 'worn-guard'}
MODES = ('natural', 'exact')

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

# (no "HEMA" here: models print the word on the jacket)
KIT = ('plain black fencing kit with no lettering: a padded black fencing jacket, black padded gloves, and a black fencing mask '
       'whose mesh hides the whole face')

NEGATIVE = ('face, uncovered face, eyes, text, letters, watermark, logo, signature, a second sword, extra blade, '
            'duplicate gear, bent or broken blade, warped or melted metal, distorted gear, deformed hands, extra fingers, '
            'fused fingers, cartoon, illustration, painting, 3D render, CGI, plastic look, oversaturated colours, '
            'colour cast, vignette, frame, border, collage, split screen, diptych, two panels, grid of photos, inset picture')

# The parts whose detail matters most, by kind.
DETAIL_PARTS = {
    'instrument': ' of the blade, cross guard, grip and pommel',
    'gloves': ' of the cuffs, padding, panels and stitching',
    'mask': ' of the mesh, bib, padding and straps',
    'jacket': ' of the panels, padding, seams and fastenings',
}

# Presets set a pose, people and a layout; the rest of the settings stay as the person left them.
# The layout is where the product starts on the frame (used by "Exact photo", and by "Natural" as a rough guide).
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
    {'id': 'worn-hands', 'label': 'Worn: hands', 'kind': 'gloves', 'worn': True,
     'scene': {'pose': 'worn-hands', 'people': 'fencer', 'place': 'paper', 'light': 'studio', 'height': 'eye', 'lens': '85', 'aperture': '5.6'},
     'layout': {'aspect': '1:1'}},
    {'id': 'worn-head', 'label': 'Worn: head and shoulders', 'kind': 'mask', 'worn': True,
     'scene': {'pose': 'worn-head', 'people': 'fencer', 'place': 'paper', 'light': 'studio', 'height': 'eye', 'lens': '85', 'aperture': '5.6'},
     'layout': {'aspect': '1:1'}},
    {'id': 'worn-torso', 'label': 'Worn: the torso', 'kind': 'jacket', 'worn': True,
     'scene': {'pose': 'worn-torso', 'people': 'fencer', 'place': 'paper', 'light': 'studio', 'height': 'eye', 'lens': '85', 'aperture': '5.6'},
     'layout': {'aspect': '1:1'}},
    {'id': 'worn-guard', 'label': 'Worn: in a guard', 'kind': 'worn', 'worn': True,
     'scene': {'pose': 'worn-guard', 'people': 'fencer', 'place': 'salle', 'light': 'window', 'height': 'eye', 'lens': '50', 'aperture': '2.8', 'framing': 'full'},
     'layout': {'aspect': '4:5'}},
    {'id': 'studio', 'label': 'Studio, cream paper', 'kind': 'any',
     'scene': {'pose': 'lying', 'people': 'none', 'place': 'paper', 'light': 'studio', 'height': 'overhead', 'lens': '85', 'aperture': '11'},
     'layout': {'aspect': '1:1', 'cx': 0.5, 'cy': 0.5, 'length': 0.7, 'point': 'keep'}},
]

# Views the multiple-angles LoRA can make: (id, label, the words it was trained on).
ANGLES = [
    ('back', 'The other face', 'back view eye-level shot medium shot'),
    ('front-left', 'Turned left', 'front-left quarter view eye-level shot medium shot'),
    ('front-right', 'Turned right', 'front-right quarter view eye-level shot medium shot'),
    ('elevated', 'From above', 'front view elevated shot medium shot'),
    ('low', 'From below', 'front view low-angle shot medium shot'),
    ('left', 'Left side', 'left side view eye-level shot medium shot'),
    ('close', 'Close up', 'front view eye-level shot close-up'),
]

WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']
ORDINALS = ['', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth']


def cap(text):
    return text[:1].upper() + text[1:]


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
        'angles': [{'id': a, 'label': b} for a, b, _ in ANGLES],
        'negative': NEGATIVE,
    }


def noun_of(product):
    n = (product.get('noun') or '').strip()
    if n:
        return n
    return {'instrument': 'sword', 'gloves': 'pair of gloves', 'mask': 'fencing mask', 'jacket': 'jacket'}.get(product.get('kind'), 'piece of gear')


def _strip_article(noun):
    for a in ('a ', 'an ', 'the '):
        if noun.lower().startswith(a):
            return noun[len(a):]
    return noun


def _a(word):
    return 'an' if word[:1].lower() in 'aeiou8' else 'a'


def _ordinals(first, count):
    """'the third picture', 'the third and fourth pictures', 'the third to fifth pictures'."""
    if count <= 0:
        return ''
    if count == 1:
        return f'the {ORDINALS[first]} picture'
    last = first + count - 1
    if count == 2:
        return f'the {ORDINALS[first]} and {ORDINALS[last]} pictures'
    return f'the {ORDINALS[first]} to {ORDINALS[last]} pictures'


def _product_pictures(views):
    return 'the first picture' if views <= 1 else f'the first {WORDS[min(views, 10)]} pictures'


def _shows(shows):
    """A list of what each product picture shows ('whole' or 'detail'), from a list or a count."""
    if isinstance(shows, int):
        return ['whole'] * max(1, shows)
    return list(shows) or ['whole']


def describe_pictures(noun, shows, first=1):
    """'The first picture shows the whole longsword; the second and third pictures are close-ups of its details.'
    Empty when there is one picture only."""
    shows = _shows(shows)
    if len(shows) <= 1:
        return ''
    runs = []
    for i, k in enumerate(shows):
        if runs and runs[-1][0] == k:
            runs[-1][2] += 1
        else:
            runs.append([k, first + i, 1])
    parts = []
    for k, start, n in runs:
        o = _ordinals(start, n)
        if k == 'detail':
            parts.append(f'{o} {"is a close-up" if n == 1 else "are close-ups"} of its details')
        else:
            parts.append(f'{o} {"shows" if n == 1 else "show"} the whole {noun}' + (' from different sides' if n > 1 else ''))
    return cap('; '.join(parts))


def _whole_pictures(shows):
    """The pictures that show the whole product, when close-ups follow them ('the first picture')."""
    shows = _shows(shows)
    if 'detail' not in shows or shows[0] != 'whole':
        return ''
    n = 0
    while n < len(shows) and shows[n] == 'whole':
        n += 1
    return _ordinals(1, n)


def _camera(s, default_aperture='2.8'):
    height = _pick(HEIGHTS, s.get('height', 'eye'))[2]
    lens = _pick(LENSES, s.get('lens', '85'))[1]
    aperture = _pick(APERTURES, s.get('aperture', default_aperture))[2]
    return f'Shot {height} with {_a(lens)} {lens} lens {aperture}'


def kit_for(kind):
    """The fencer's kit, leaving out the piece that is the product."""
    parts = {'jacket': 'a padded black fencing jacket', 'gloves': 'black padded gloves',
             'mask': 'a black fencing mask whose mesh hides the whole face'}
    keep = [v for k, v in parts.items() if k != kind]
    if len(keep) == 1:
        return 'plain black fencing kit with no lettering: ' + keep[0]
    if len(keep) == 2:
        return 'plain black fencing kit with no lettering: ' + keep[0] + ' and ' + keep[1]
    return 'plain black fencing kit with no lettering: ' + ', '.join(keep[:-1]) + ', and ' + keep[-1]


def _natural_subject(s, noun, kind, views):
    """What the photograph shows, with the product named by the pictures it comes from."""
    src = f'the {noun} from the first picture' if views <= 1 else f'the {noun} shown in the first {WORDS[min(views, 10)]} pictures'
    pose = s.get('pose', 'held-up' if kind == 'instrument' else 'lying')
    people = s.get('people', 'none')
    side = s.get('side', 'right')
    framing = {'close': 'framed close', 'half': 'framed from the waist up', 'full': 'the whole figure in the frame'}.get(s.get('framing', 'half'))
    whole = (f'the whole {noun}, from pommel to point, is in the frame, with a little space beyond the point and the pommel'
             if kind == 'instrument' else f'the whole {noun} is in the frame')
    kit = kit_for(kind)
    if pose == 'held-up':
        if people in ('hand', 'hands', 'none'):
            return (f'{src}, held upright in one hand: the blade points straight up toward the top of the frame, a black '
                    f'padded fencing glove that comes in from the {side} edge of the frame grips the handle just below the cross '
                    f'guard, and the pommel shows below the fist; only the gloved hand and the forearm, in the sleeve of a black '
                    f'fencing jacket, come into the frame, and {whole}')
        return (f'a fencer in {KIT} holding {src} upright in front of the body, the blade pointing straight up and the gloved '
                f'hands on the handle, {framing}')
    if pose == 'guard':
        who = 'two fencers, each in ' + KIT + ',' if people == 'pair' else 'a fencer in ' + KIT + ','
        return (f'{who} standing in a fencing guard and holding {src} out in front of the body with both gloved hands on '
                f'the handle, the blade angled up and away at about 45 degrees so that its whole length shows, {framing}')
    if pose == 'shoulder':
        return f'a fencer in {KIT} resting {src} on the shoulder, one gloved hand on the handle, {framing}'
    if pose == 'palms':
        return f'{src} lying across two open hands in black padded fencing gloves, presented to the camera; only the hands and forearms are in the frame, and {whole}'
    if pose == 'leaning':
        return f'{src} leaning against the wall, point up, its pommel resting on the floor; nobody is in the frame, and {whole}'
    if pose == 'hanging':
        return f'{src} hanging from a wooden peg on the wall; nobody is in the frame'
    if pose == 'in-hand':
        return f'{src} held in one bare hand that comes in from the {side} edge of the frame; only the hand and the wrist are in the frame'
    if pose == 'with-kit':
        return f'{src} lying on a wooden bench beside a black fencing mask and a rolled black fencing jacket; nobody is in the frame'
    if pose == 'worn-hands':
        return (f'the hands and forearms of a fencer in {kit}, wearing {src}, both hands closed on the handle of a steel '
                f'training sword held in front of the body; the frame cropped to the hands and forearms')
    if pose == 'worn-head':
        return f'the head and shoulders of a fencer in {kit}, wearing {src}, turned three-quarters to the camera'
    if pose == 'worn-torso':
        return f'a fencer in {kit}, wearing {src}, framed from the hips to the top of the head, standing turned slightly to the camera'
    if pose == 'worn-guard':
        return f'a fencer in {kit}, wearing {src}, standing in a fencing guard with a steel training sword, the whole figure in the frame'
    # lying
    if people in ('hand', 'hands'):
        return f'{src} lying on the surface, one gloved hand resting beside it, and {whole}'
    return f'{src} lying on the surface with a soft natural shadow under it; nobody is in the frame, and {whole}'


def fidelity(product, views):
    """The sentence that holds the product to its photos. views: a count, or what each picture shows."""
    noun = noun_of(product)
    kind = product.get('kind') or 'other'
    shows = _shows(views)
    whole = _whole_pictures(shows)
    shape = f'the same shape and proportions as in {whole}, the same colours' if whole else 'the same shape, proportions, colours'
    text = (f'The {noun} must be exactly the one in {_product_pictures(len(shows))}: {shape}, '
            f'materials and every detail{DETAIL_PARTS.get(kind, "")}, seen at the angle and size this photograph needs '
            f'and lit by its light')
    mats = (product.get('materials') or '').strip().rstrip('.')
    if mats:
        text += f'. It is made of {mats}, and takes the light the way those materials do'
    if kind != 'gloves':
        text += f'. There is only one {_strip_article(noun)}'
    return text


def layout_phrase(product, box, angle=None, cite=''):
    """Where the product sits in the frame, from a rough guide. box: (x0, y0, x1, y1) in fractions of the frame;
    angle: the direction of a sword's point in degrees (0 right, -90 up)."""
    noun = noun_of(product)
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    h = 'left' if cx < 0.4 else 'right' if cx > 0.6 else ''
    v = 'top' if cy < 0.4 else 'bottom' if cy > 0.6 else ''
    where = 'in the centre of the frame' if not h and not v else f'in the {"-".join(x for x in (v, h) if x)} part of the frame'
    hp, wp = int(round(100 * (y1 - y0))), int(round(100 * (x1 - x0)))
    text = f'The {noun}{" " + cite if cite else ""} is {where}, about {hp}% of the frame\'s height and {wp}% of its width'
    if angle is not None and (product.get('kind') == 'instrument'):
        a = ((angle + 180) % 360) - 180
        if -112 <= a <= -68:
            d = 'its point up'
        elif -158 < a < -112:
            d = 'its point up and to the left'
        elif -68 < a < -22:
            d = 'its point up and to the right'
        elif -22 <= a <= 22:
            d = 'its point to the right'
        elif a >= 158 or a <= -158:
            d = 'its point to the left'
        elif 22 < a < 68:
            d = 'its point down and to the right'
        elif 112 < a < 158:
            d = 'its point down and to the left'
        else:
            d = 'its point down'
        text += ', ' + d
    return text


def flux_layout(prompt_text, product, box, views):
    """FLUX 3's own layout table: the product's box on a 0..1000 grid, cited as <obj_1> in the prompt."""
    x0, y0, x1, y1 = box
    q = lambda v: max(0, min(1000, int(round(v * 1000))))
    rows = [{'id': 'obj_1', 'bbox': [q(y0), q(x0), q(y1), q(x1)],
             'desc': f'the {noun_of(product)} from {_product_pictures(len(_shows(views)))}'}]
    return prompt_text.rstrip() + ' ' + json.dumps(rows, ensure_ascii=False)


def natural_prompt(s, product, views=1, refs=0, layout=None):
    """For the model drawing the product from its photos: the first pictures show the product (views: a
    count, or what each shows, 'whole' or 'detail'), the next `refs` are style references."""
    noun = noun_of(product)
    kind = product.get('kind') or 'other'
    shows = _shows(views)
    views = len(shows)
    pose = s.get('pose', 'held-up' if kind == 'instrument' else 'lying')
    place = s.get('place_text') or _pick(PLACES, s.get('place', 'brick'))[2]
    light = s.get('light_text') or _pick(LIGHTS, s.get('light', 'overcast'))[2]
    parts = [
        f'Create a photograph of {_natural_subject(s, noun, kind, views)}',
        'It is one single photograph, taken in one shot, that fills the whole frame',
        describe_pictures(noun, shows),
        f'The setting: {place}',
        'Light: ' + light,
        _camera(s, '5.6' if pose in WORN else '2.8'),
    ]
    if layout:
        parts.append(layout)
    parts.append('Natural, muted colours and true-to-life textures, as in an unretouched photograph; no text')
    if refs:
        parts.append(f'Take the photographic look, light and colour from {_ordinals(views + 1, refs)}, not {"its" if refs == 1 else "their"} content')
    if s.get('extra'):
        parts.append(s['extra'].strip().rstrip('.'))
    parts.append(fidelity(product, shows))
    if pose in WORN:
        parts.append('The face stays hidden behind ' + ('that fencing mask' if kind == 'mask' else 'a black fencing mask'))
    elif s.get('people', 'none') in ('fencer', 'pair'):
        parts.append('Every face stays hidden behind a black fencing mask')
    return '. '.join(p.strip().rstrip('.') for p in parts if p) + '.'


def _subject_exact(s, noun, kind):
    pose = s.get('pose', 'held-up' if kind == 'instrument' else 'lying')
    people = s.get('people', 'none')
    side = s.get('side', 'right')
    framing = {'close': 'framed close', 'half': 'framed from the waist up', 'full': 'the whole figure in the frame'}.get(s.get('framing', 'half'))
    the = 'the ' + noun
    if pose == 'held-up':
        if people in ('hand', 'hands', 'none'):
            return (f'{cap(the)} stands upright where it is, point up, held by one hand in a black padded fencing glove '
                    f'that comes in from the {side} edge of the frame and grips the handle just below the cross guard; only the '
                    f'gloved hand and the forearm, in the sleeve of a black fencing jacket, come into the frame')
        return f'A fencer in {KIT} holds {the} upright where it is, point up, the gloved hands on the handle, {framing}'
    if pose == 'guard':
        who = 'two fencers, each in ' + KIT + ',' if people == 'pair' else 'a fencer in ' + KIT + ','
        return (f'{cap(who)} holds {the} where it is with both gloved hands on the handle, in a fencing guard, '
                f'{framing}; the body turned to match the angle of the blade')
    if pose == 'shoulder':
        return f'A fencer in {KIT} rests {the} on the shoulder where it is, one gloved hand on the handle, {framing}'
    if pose == 'palms':
        return f'{cap(the)} lies across two open hands in black padded fencing gloves, presented to the camera, only the hands and forearms in the frame'
    if pose == 'leaning':
        return f'{cap(the)} leans against the wall where it is, point up, its pommel resting on the floor, nobody in the frame'
    if pose == 'hanging':
        return f'{cap(the)} hangs from a wooden peg on the wall where it is, nobody in the frame'
    if pose == 'in-hand':
        return f'{cap(the)} is held where it is by one bare hand that comes in from the {side} edge of the frame, only the hand and the wrist in the frame'
    if pose == 'with-kit':
        return f'{cap(the)} lies where it is on a wooden bench, beside a black fencing mask and a rolled black fencing jacket, nobody in the frame'
    if people in ('hand', 'hands'):
        return f'{cap(the)} lies where it is on the surface, one gloved hand resting beside it'
    return f'{cap(the)} lies where it is on the surface, with a soft natural shadow under it, nobody in the frame'


def exact_prompt(s, product, refs=0):
    """For "Exact photo": an edit of the first picture, which shows the product alone on a plain backdrop
    where it will be; the product stays as photographed."""
    noun = noun_of(product)
    kind = product.get('kind') or 'other'
    place = s.get('place_text') or _pick(PLACES, s.get('place', 'brick'))[2]
    light = s.get('light_text') or _pick(LIGHTS, s.get('light', 'overcast'))[2]
    backdrop = 'light' if sum(product.get('backdrop') or [0.9, 0.9, 0.9]) / 3 > 0.6 else 'plain'
    parts = [
        f'Replace the plain {backdrop} background with a real photograph taken in front of {place}' if s.get('pose') not in ('lying', 'with-kit')
        else f'Replace the plain {backdrop} background with a real photograph of {place}',
        _subject_exact(s, noun, kind),
        'Light: ' + light,
        _camera(s),
        'Natural, muted colours and true-to-life textures, as in an unretouched photograph; no text',
    ]
    if refs:
        parts.append(f'Take the photographic look, light and colour from {_ordinals(2, refs)}, not {"its" if refs == 1 else "their"} content')
    if s.get('people', 'none') in ('fencer', 'pair'):
        parts.append('Every face stays hidden behind a black fencing mask')
    if s.get('extra'):
        parts.append(s['extra'].strip().rstrip('.'))
    parts.append(f'Keep the {noun} exactly as it is in the picture: the same position, size, angle, shape, colours and every detail')
    return '. '.join(p.strip().rstrip('.') for p in parts if p) + '.'


def detail_prompt(product, views=1):
    """For the detail pass: the first picture is a crop of the made photograph around the product; the
    next pictures are the product's own photos (views: a count, or what each shows)."""
    noun = noun_of(product)
    kind = product.get('kind') or 'other'
    shows = _shows(views)
    others = _ordinals(2, len(shows))
    mats = (product.get('materials') or '').strip().rstrip('.')
    text = f'The first picture is part of a photograph showing the {noun} from {others}. '
    desc = describe_pictures(noun, shows, first=2)
    if desc:
        text += desc + '. '
    text += (f'Redraw only the {noun} in the first picture so that it is exactly the one in {others}: the same shape, '
             f'proportions, colours, materials and every detail{DETAIL_PARTS.get(kind, "")}, sharp and clear')
    if mats:
        text += f', made of {mats}'
    text += ('. Keep its position, angle, size and perspective in the first picture, the hands holding it, everything '
             'around it, and the photograph\'s light, shadows, reflections and colours as they are.')
    return text


def hilt_prompt(product, views=1):
    """For the closer look at a sword's hilt: the first picture is a close crop of the made photograph around
    the hilt; the next are the product's own photos, close-ups first."""
    noun = noun_of(product)
    shows = _shows(views)
    others = _ordinals(2, len(shows))
    mats = (product.get('materials') or '').strip().rstrip('.')
    text = f'The first picture is a close crop of a photograph, showing the hilt of the {noun} from {others}: its cross guard, grip and pommel. '
    desc = describe_pictures(noun, shows, first=2)
    if desc:
        text += desc + '. '
    text += (f'Redraw only the hilt in the first picture so that it is exactly the one in {others}: the same cross guard and '
             f'the shape of its ends, the same grip with its wrap and any ring or collar on it, and the same pommel, its shape '
             f'and every facet, sharp and clear')
    if mats:
        text += f', made of {mats}'
    text += ('. Keep its position, angle, size and perspective in the first picture, the hand holding it, the blade and '
             'everything around it, and the photograph\'s light, shadows and reflections as they are.')
    return text


def harmonize_prompt(s, product):
    """For "Exact photo": let the scene's light fall on the photographed product, which keeps its form."""
    noun = noun_of(product)
    light = s.get('light_text') or _pick(LIGHTS, s.get('light', 'overcast'))[2]
    mats = (product.get('materials') or '').strip().rstrip('.') or 'its materials'
    return (f'The {noun} in the first picture was photographed apart and put into this scene; it is the {noun} in the second '
            f'picture. Relight only the {noun} so that it belongs here: {light}, falling on it as it would on {mats}, with '
            f'highlights, reflections of the surroundings and shading that match the rest of the photograph, and natural '
            f'contact shadows where it touches the hands or the surface. Keep the {noun}\'s shape, position, size, angle, '
            f'colours and every detail exactly, and keep everything else in the picture as it is.')


def angle_prompt(angle_id):
    """The multiple-angles LoRA's own words for a view."""
    words = _pick(ANGLES, angle_id)[2]
    return '<sks> ' + words


def prompt(s, product, family='qwen', refs=0, mode='natural', views=1, layout=None):
    """The prompt for a scene `s` (a dict of setting ids) and a product (its json). views: how many of the
    product's pictures the model gets, or what each shows ('whole' or 'detail')."""
    if s.get('custom'):
        return s['custom'].strip()
    if mode == 'exact' and s.get('pose') not in WORN:
        return exact_prompt(s, product, refs)
    return natural_prompt(s, product, views, refs, layout)


def negative(s):
    return s.get('negative') if s.get('negative') is not None else NEGATIVE
