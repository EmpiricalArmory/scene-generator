"""ComfyUI workflows (API format) for each model.

All three work the same way: the model sees the product on a plain backdrop (and any style references),
is told what to make around it, and draws only where draw.png allows; the product's area is held to its
own pixels at every step. EA Finish then pastes the photo's pixels back at the output size.
"""
from .models import FAMILIES

FLUX3_UPSAMPLER_SYSTEM = (
    "You are the prompt upsampler of an image-editing model. You see the reference image(s), attached in order "
    "(the first image, the second image, ...), and the user's short request. Expand it into ONE detailed, "
    "self-contained instruction: the caption the editing model receives together with the same images. Output only "
    "the instruction as one continuous English prose block, with no greetings, explanations, Markdown, JSON, "
    "coordinates, ids or angle-bracket tokens. Read a vague or conversational request as the most plausible edit of "
    "the supplied images.\n\nPick the voice by task shape. When one reference stays and gets bounded changes, write an "
    "imperative editing instruction on it (\"Remove the ...\", \"Change the ... to ...\", \"Zoom in on ...\"); a "
    "whole-image transformation opens with its scope (\"Convert the entire image into ...\", \"Apply a ... filter over "
    "the entire scene\", \"Horizontally flip the entire image so that ...\", \"Shift the camera viewpoint to ...\", then "
    "where the major elements should now be). When the references are drawn into a newly composed frame (combining "
    "subjects, a new scene, a garment, object or style donor), write a generation request (\"Create a photograph of "
    "...\", \"Create an anime-style illustration of ...\", \"Generate a new image featuring ...\") that says what to take "
    "from each image, by ordinal, and what is newly generated.\n\nKeep every explicit edit, constraint, count, "
    "position, style cue and piece of wording, and decide what is left open as one concrete plan. Ground everything in "
    "what is actually visible: identify each referent unambiguously by its real appearance, never mention content that "
    "is not there, and use every image the user attached. State every end state concretely (which color, how large, "
    "which pose, which material) and give new content enough appearance to be generated. Cover the knock-on effects of "
    "the change (shadows, reflections, occlusion, perspective, scale, lighting) and say what fills a removed region. A "
    "zoom-in names what stays in frame and which neighbors are cropped out; an outpainting continues the scene in the "
    "same medium. Describe the change, not the whole scene, and close an editing instruction with one compact clause "
    "naming what stays unchanged; transferred people keep their identity, face and accessories unless asked "
    "otherwise. Transcribe on-image text verbatim in its original language inside double quotes, with line breaks as "
    "\\n, and match the original font, size and color when replacing it. Name recognizable public figures, brands and "
    "landmarks you can see. Directions are frame-relative; use no evaluative or quality words. Typical length is 50 to "
    "150 words.\n\nOutput only the instruction.")


class Graph:
    def __init__(self):
        self.nodes = {}
        self.n = 0

    def add(self, cls, **inputs):
        self.n += 1
        key = str(self.n)
        self.nodes[key] = {'class_type': cls, 'inputs': inputs}
        return key


def out(key, slot=0):
    return [key, slot]


def build(job, variation=0, status=None):
    """The API prompt for one picture of a job. status: models.status(), to use optional files when present."""
    fam = job['family']
    F = FAMILIES[fam]
    q = F['quality']['draft' if job.get('quality') == 'draft' else 'final']
    seed = int(job['seed']) + int(variation)
    g = Graph()
    jid = job['id']
    worn = job.get('product_mode') == 'reference'
    fw, fh = job['frame']
    if worn:
        canvas = g.add('EAJobImage', job=jid, name='product')      # the product, for the model to draw from
        draw = None
    else:
        canvas = g.add('EAJobImage', job=jid, name='canvas')
        draw = g.add('EAJobMask', job=jid, name='draw')
    refs = [g.add('EAJobImage', job=jid, name=f'ref{i + 1}') for i in range(len(job.get('refs') or []))]
    opt = (status or {}).get(fam, {}).get('optional', {})

    style = job.get('style') or None

    def with_style(model):
        if not style or not style.get('lora'):
            return model
        return out(g.add('LoraLoaderModelOnly', model=model, lora_name=style['lora'], strength_model=float(style.get('strength', 0.8))))

    def latent(vae, empty_cls):
        if worn:
            return g.add(empty_cls, width=int(fw), height=int(fh), batch_size=1)
        lat = g.add('VAEEncode', pixels=out(canvas), vae=vae)
        return g.add('SetLatentNoiseMask', samples=out(lat), mask=out(draw))

    if fam == 'qwen':
        unet = g.add('UNETLoader', unet_name=F['files']['unet'][1], weight_dtype='default')
        clip = g.add('CLIPLoader', clip_name=F['files']['clip'][1], type='qwen_image', device='default')
        vae = g.add('VAELoader', vae_name=F['files']['vae'][1])
        m = g.add('ModelSamplingAuraFlow', model=with_style(out(unet)), shift=3.1)
        m = g.add('CFGNorm', model=out(m), strength=1.0)
        cfg = q.get('cfg', 4.0)
        if job.get('quality') == 'draft' and opt.get('lightning'):
            m = g.add('LoraLoaderModelOnly', model=out(m), lora_name=F['optional']['lightning'][1], strength_model=1.0)
        else:
            q = F['quality']['final']
            cfg = q.get('cfg', 4.0)
        m = g.add('DifferentialDiffusion', model=out(m), strength=1.0)
        images = {'image1': out(canvas)}
        for i, r in enumerate(refs[:2]):
            images[f'image{i + 2}'] = out(r)
        mp = 1.0 if worn else 0.0
        pos = g.add('EAQwenEditEncode', clip=out(clip), prompt=job['prompt'], ref_megapixels=mp, vae=out(vae), **images)
        neg = g.add('EAQwenEditEncode', clip=out(clip), prompt=job.get('negative') or '', ref_megapixels=mp, vae=out(vae), **images)
        pos = g.add('FluxKontextMultiReferenceLatentMethod', conditioning=out(pos), reference_latents_method='index_timestep_zero')
        neg = g.add('FluxKontextMultiReferenceLatentMethod', conditioning=out(neg), reference_latents_method='index_timestep_zero')
        lat = latent(out(vae), 'EmptySD3LatentImage')
        s = g.add('KSampler', model=out(m), seed=seed, steps=int(q['steps']), cfg=float(cfg), sampler_name='euler',
                  scheduler='simple', positive=out(pos), negative=out(neg), latent_image=out(lat), denoise=1.0)
        img = g.add('VAEDecode', samples=out(s), vae=out(vae))

    elif fam == 'flux3':
        unet_name = F['files']['unet'][1]
        steps, cfg = int(q['steps']), 1.0
        unet = g.add('UNETLoader', unet_name=unet_name, weight_dtype='default')
        clip = g.add('CLIPLoader', clip_name=F['files']['clip'][1], type='flux3', device='default')
        vae = g.add('VAELoader', vae_name=F['files']['vae'][1])
        m = g.add('DifferentialDiffusion', model=out(unet), strength=1.0)
        text = job['prompt']
        if job.get('upsample_prompt') and opt.get('upsampler'):
            up = g.add('CLIPLoader', clip_name=F['optional']['upsampler'][1], type='flux3', device='default')
            batch_inputs = {'images.image0': out(canvas)}
            for i, r in enumerate(refs):
                batch_inputs[f'images.image{i + 1}'] = out(r)
            batch = g.add('BatchImagesNode', **batch_inputs)
            system = g.add('PrimitiveStringMultiline', value=FLUX3_UPSAMPLER_SYSTEM)
            gen = g.add('TextGenerate', clip=out(up), prompt=text, image=out(batch), max_length=3584,
                        sampling_mode='on', **{'sampling_mode.temperature': 1.0, 'sampling_mode.top_k': 1,
                                               'sampling_mode.top_p': 0.95, 'sampling_mode.min_p': 0.0,
                                               'sampling_mode.repetition_penalty': 1.05, 'sampling_mode.seed': 0,
                                               'sampling_mode.presence_penalty': 0.0},
                        thinking=False, use_default_template=True, mtp='off', system_prompt=out(system))
            text = out(gen)
        pos = g.add('CLIPTextEncode', clip=out(clip), text=text)
        neg = g.add('ConditioningZeroOut', conditioning=out(pos))
        ref_inputs = {'images.image0': out(canvas)}
        for i, r in enumerate(refs):
            ref_inputs[f'images.image{i + 1}'] = out(r)
        if worn:
            ref = g.add('ReferenceMultiLatent', positive=out(pos), negative=out(neg), vae=out(vae),
                        resolution='resize', **{'resolution.megapixels': 1.5}, **ref_inputs)
        else:
            ref = g.add('ReferenceMultiLatent', positive=out(pos), negative=out(neg), vae=out(vae),
                        resolution='keep resolution', **ref_inputs)
        lat = latent(out(vae), 'EmptyFlux2LatentImage')
        s = g.add('KSampler', model=out(m), seed=seed, steps=steps, cfg=cfg, sampler_name='euler', scheduler='simple',
                  positive=out(ref, 0), negative=out(ref, 1), latent_image=out(lat), denoise=1.0)
        img = g.add('VAEDecode', samples=out(s), vae=out(vae))

    elif fam == 'hidream':
        ck = g.add('CheckpointLoaderSimple', ckpt_name=F['files']['ckpt'][1])
        ns = g.add('ModelNoiseScale', model=with_style(out(ck, 0)), noise_scale=8.0)
        m = g.add('HiDreamO1PatchSeamSmoothing', model=out(ns), start_percent=0.8, end_percent=1.0,
                  pattern='single_shift', passes='ramp_2_4', blend='median', strength=1.0)
        m = g.add('DifferentialDiffusion', model=out(m), strength=1.0)
        pos = g.add('CLIPTextEncode', clip=out(ck, 1), text=job['prompt'])
        neg = g.add('CLIPTextEncode', clip=out(ck, 1), text=job.get('negative') or '')
        ref_inputs = {'images.image_1': out(canvas)}
        for i, r in enumerate(refs):
            ref_inputs[f'images.image_{i + 2}'] = out(r)
        refd = g.add('HiDreamO1ReferenceImages', positive=out(pos), negative=out(neg), **ref_inputs)
        lat = latent(out(ck, 2), 'EmptyHiDreamO1LatentImage')
        sampler = g.add('KSamplerSelect', sampler_name='dpmpp_2m_sde_gpu')
        sig = g.add('BasicScheduler', model=out(ns), scheduler='normal', steps=int(q['steps']), denoise=1.0)
        s = g.add('SamplerCustom', model=out(m), add_noise=True, noise_seed=seed, cfg=float(q.get('cfg', 5.0)),
                  positive=out(refd, 0), negative=out(refd, 1), sampler=out(sampler), sigmas=out(sig), latent_image=out(lat))
        img = g.add('VAEDecode', samples=out(s, 0), vae=out(ck, 2))
    else:
        raise ValueError('Unknown model family: ' + fam)

    g.add('EAFinish', images=out(img), job=jid, variation=int(variation))
    return g.nodes


def cutout_graph(product_id, method='auto'):
    g = Graph()
    g.add('EAProductCutout', product=product_id, method=method)
    return g.nodes
