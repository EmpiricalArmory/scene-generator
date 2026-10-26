"""ComfyUI workflows (API format) for each model.

Natural (the default): the model is given the product's photos, each on a plain backdrop, and draws the
product into the scene at the angle, size and light the scene needs. Then the detail pass: SAM 3 finds the
product in the picture, the area around it is cut out, enlarged, and redrawn against the photos at part
strength, and blended back. Optionally SeedVR2 enlarges the picture to the output size; otherwise it is
resized. SAM 3 then finds the product once more, for the parts map.

Exact photo: the model draws only around the photo, which is held as it is (a latent noise mask with
differential diffusion); a relight pass then lets the scene's light fall on it (the product, a ring around
it for shadows, a little everywhere else), and EA Finish puts the photo's fine detail back on top.
"""
from .models import ANGLES_LORA, FAMILIES, SAM3, SEEDVR2
from . import scene

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

DETAIL_SEED = 7919          # the detail and relight passes use their own noise
EMPTY_LATENT = {'qwen': 'EmptySD3LatentImage', 'flux3': 'EmptyFlux2LatentImage', 'hidream': 'EmptyHiDreamO1LatentImage'}


class Graph:
    def __init__(self):
        self.nodes = {}
        self.n = 0
        self.shared = {}

    def add(self, cls, **inputs):
        self.n += 1
        key = str(self.n)
        self.nodes[key] = {'class_type': cls, 'inputs': inputs}
        return key

    def once(self, name, make):
        """A node shared by the whole graph (a model loader, say), made the first time it is asked for."""
        if name not in self.shared:
            self.shared[name] = make()
        return self.shared[name]


def out(key, slot=0):
    return [key, slot]


class Kit:
    """One model family's loaders and sampler, shared by every pass of a picture."""

    def __init__(self, g, job, status=None):
        self.g = g
        self.job = job
        self.fam = fam = job['family']
        F = self.F = FAMILIES[fam]
        draft = job.get('quality') == 'draft'
        q = F['quality']['draft' if draft else 'final']
        opt = (status or {}).get(fam, {}).get('optional', {})
        self.opt = opt
        style = job.get('style') or None

        def with_style(model):
            if not style or not style.get('lora'):
                return model
            return out(g.add('LoraLoaderModelOnly', model=model, lora_name=style['lora'], strength_model=float(style.get('strength', 0.8))))

        if fam == 'qwen':
            unet = g.add('UNETLoader', unet_name=F['files']['unet'][1], weight_dtype='default')
            self.clip = out(g.add('CLIPLoader', clip_name=F['files']['clip'][1], type='qwen_image', device='default'))
            self.vae = out(g.add('VAELoader', vae_name=F['files']['vae'][1]))
            m = g.add('ModelSamplingAuraFlow', model=with_style(out(unet)), shift=3.1)
            m = g.add('CFGNorm', model=out(m), strength=1.0)
            if draft and opt.get('lightning'):
                m = g.add('LoraLoaderModelOnly', model=out(m), lora_name=F['optional']['lightning'][1], strength_model=1.0)
                self.steps, self.cfg = int(q['steps']), float(q.get('cfg', 1.0))
            else:
                fq = F['quality']['final']
                self.steps, self.cfg = int(fq['steps']), float(fq.get('cfg', 4.0))
            self.model = out(g.add('DifferentialDiffusion', model=out(m), strength=1.0))
        elif fam == 'flux3':
            unet = g.add('UNETLoader', unet_name=F['files']['unet'][1], weight_dtype='default')
            self.clip = out(g.add('CLIPLoader', clip_name=F['files']['clip'][1], type='flux3', device='default'))
            self.vae = out(g.add('VAELoader', vae_name=F['files']['vae'][1]))
            self.model = out(g.add('DifferentialDiffusion', model=out(unet), strength=1.0))
            self.steps, self.cfg = int(q['steps']), 1.0
        elif fam == 'hidream':
            ck = g.add('CheckpointLoaderSimple', ckpt_name=F['files']['ckpt'][1])
            ns = g.add('ModelNoiseScale', model=with_style(out(ck, 0)), noise_scale=8.0)
            m = g.add('HiDreamO1PatchSeamSmoothing', model=out(ns), start_percent=0.8, end_percent=1.0,
                      pattern='single_shift', passes='ramp_2_4', blend='median', strength=1.0)
            self.model = out(g.add('DifferentialDiffusion', model=out(m), strength=1.0))
            self.sched_model = out(ns)
            self.clip, self.vae = out(ck, 1), out(ck, 2)
            self.steps, self.cfg = int(q['steps']), float(q.get('cfg', 5.0))
        else:
            raise ValueError('Unknown model family: ' + fam)

    def empty_latent(self, w, h):
        return out(self.g.add(EMPTY_LATENT[self.fam], width=int(w), height=int(h), batch_size=1))

    def masked_latent(self, image, mask):
        """The picture as the starting point; only where the mask allows may it change."""
        lat = self.g.add('VAEEncode', pixels=image, vae=self.vae)
        return out(self.g.add('SetLatentNoiseMask', samples=out(lat), mask=mask))

    def pass_steps(self, denoise):
        """Steps for a part-strength pass: enough to keep the full pass's step density, never fewer than 8."""
        return max(8, int(round(self.steps * max(0.6, denoise))))

    def sample(self, prompt, negative, pictures, latent, seed, denoise=1.0, aligned=False, steps=None, upsample=False):
        """Draw a picture. pictures: IMAGE outputs, in the order the prompt names them. aligned: the first
        picture is the one being changed (it lines up with the latent), so it keeps its own size."""
        g, fam = self.g, self.fam
        steps = int(steps or self.steps)
        if fam == 'qwen':
            images = {f'image{i + 1}': p for i, p in enumerate(pictures[:3])}
            mp = 0.0 if aligned else 1.0
            pos = g.add('EAQwenEditEncode', clip=self.clip, prompt=prompt, ref_megapixels=mp, vae=self.vae, **images)
            neg = g.add('EAQwenEditEncode', clip=self.clip, prompt=negative or '', ref_megapixels=mp, vae=self.vae, **images)
            pos = g.add('FluxKontextMultiReferenceLatentMethod', conditioning=out(pos), reference_latents_method='index_timestep_zero')
            neg = g.add('FluxKontextMultiReferenceLatentMethod', conditioning=out(neg), reference_latents_method='index_timestep_zero')
            s = g.add('KSampler', model=self.model, seed=int(seed), steps=steps, cfg=self.cfg, sampler_name='euler',
                      scheduler='simple', positive=out(pos), negative=out(neg), latent_image=latent, denoise=float(denoise))
            return out(g.add('VAEDecode', samples=out(s), vae=self.vae))
        if fam == 'flux3':
            text = prompt
            if upsample and self.opt.get('upsampler'):
                up = g.add('CLIPLoader', clip_name=self.F['optional']['upsampler'][1], type='flux3', device='default')
                batch = g.add('BatchImagesNode', **{f'images.image{i}': p for i, p in enumerate(pictures)})
                system = g.add('PrimitiveStringMultiline', value=FLUX3_UPSAMPLER_SYSTEM)
                gen = g.add('TextGenerate', clip=out(up), prompt=prompt, image=out(batch), max_length=3584,
                            sampling_mode='on', **{'sampling_mode.temperature': 1.0, 'sampling_mode.top_k': 1,
                                                   'sampling_mode.top_p': 0.95, 'sampling_mode.min_p': 0.0,
                                                   'sampling_mode.repetition_penalty': 1.05, 'sampling_mode.seed': 0,
                                                   'sampling_mode.presence_penalty': 0.0},
                            thinking=False, use_default_template=True, mtp='off', system_prompt=out(system))
                text = out(gen)
            pos = g.add('CLIPTextEncode', clip=self.clip, text=text)
            neg = g.add('ConditioningZeroOut', conditioning=out(pos))
            ref = g.add('ReferenceMultiLatent', positive=out(pos), negative=out(neg), vae=self.vae,
                        resolution='keep resolution', **{f'images.image{i}': p for i, p in enumerate(pictures)})
            s = g.add('KSampler', model=self.model, seed=int(seed), steps=steps, cfg=1.0, sampler_name='euler', scheduler='simple',
                      positive=out(ref, 0), negative=out(ref, 1), latent_image=latent, denoise=float(denoise))
            return out(g.add('VAEDecode', samples=out(s), vae=self.vae))
        # hidream
        pos = g.add('CLIPTextEncode', clip=self.clip, text=prompt)
        neg = g.add('CLIPTextEncode', clip=self.clip, text=negative or '')
        refd = g.add('HiDreamO1ReferenceImages', positive=out(pos), negative=out(neg),
                     **{f'images.image_{i + 1}': p for i, p in enumerate(pictures)})
        sampler = g.once('hidream-sampler', lambda: g.add('KSamplerSelect', sampler_name='dpmpp_2m_sde_gpu'))
        sig = g.add('BasicScheduler', model=self.sched_model, scheduler='normal', steps=steps, denoise=float(denoise))
        s = g.add('SamplerCustom', model=self.model, add_noise=True, noise_seed=int(seed), cfg=self.cfg,
                  positive=out(refd, 0), negative=out(refd, 1), sampler=out(sampler), sigmas=out(sig), latent_image=latent)
        return out(g.add('VAEDecode', samples=out(s, 0), vae=self.vae))


def sam_find(g, image, term, threshold=0.4):
    """SAM 3's mask of `term` in a picture (the union of what it finds)."""
    ck = g.once('sam3', lambda: g.add('CheckpointLoaderSimple', ckpt_name=SAM3[1]))
    cond = g.once('sam3-text:' + term, lambda: g.add('CLIPTextEncode', clip=out(ck, 1), text=term))
    det = g.add('SAM3_Detect', model=out(ck, 0), image=image, conditioning=out(cond), threshold=float(threshold),
                refine_iterations=2, individual_masks=False)
    return out(det, 0)


def seedvr2(g, image, width, height, seed):
    """SeedVR2 7B: enlarge to width x height, adding real detail; colours matched to the input (Lab)."""
    r = g.add('ImageScale', image=image, upscale_method='lanczos', width=int(width), height=int(height), crop='disabled')
    pre = g.add('SeedVR2Preprocess', resized_images=out(r))
    vae = g.once('seedvr2-vae', lambda: g.add('VAELoader', vae_name=SEEDVR2['vae'][1]))
    enc = g.add('VAEEncodeTiled', pixels=out(pre), vae=out(vae), tile_size=512, overlap=128, temporal_size=4096, temporal_overlap=8)
    m = g.once('seedvr2-model', lambda: g.add('UNETLoader', unet_name=SEEDVR2['unet'][1], weight_dtype='default'))
    cond = g.add('SeedVR2Conditioning', model=out(m), vae_conditioning=out(enc))
    s = g.add('KSampler', model=out(m), seed=int(seed), steps=1, cfg=1.0, sampler_name='euler', scheduler='simple',
              positive=out(cond, 0), negative=out(cond, 1), latent_image=out(enc), denoise=1.0)
    dec = g.add('VAEDecodeTiled', samples=out(s), vae=out(vae), tile_size=512, overlap=128, temporal_size=4096, temporal_overlap=8)
    return out(g.add('SeedVR2PostProcessing', images=out(dec), original_resized_images=out(r), color_correction_method='lab'))


def build(job, variation=0, status=None):
    """The API prompt for one picture of a job. status: models.status(), to use optional files when present."""
    g = Graph()
    kit = Kit(g, job, status)
    jid = job['id']
    seed = int(job['seed']) + int(variation)
    fw, fh = job['frame']
    ow, oh = job['output']
    neg = job.get('negative') or ''
    refs = [out(g.add('EAJobImage', job=jid, name=f'ref{i + 1}')) for i in range(len(job.get('refs') or []))]
    up = job.get('upscale') == 'seedvr2'

    if job.get('product_mode') in ('natural', 'reference'):
        views = [out(g.add('EAJobImage', job=jid, name=f'view{i + 1}')) for i in range(int(job.get('views') or 1))]
        first = kit.sample(job['prompt'], neg, views + refs, kit.empty_latent(fw, fh), seed,
                           upsample=bool(job.get('upsample_prompt')))
        det = job.get('detail') or {}
        if det.get('on'):
            found = sam_find(g, first, job['find'])
            crop = g.add('EADetailCrop', image=first, mask=found, megapixels=float(det['megapixels']))
            lat = kit.masked_latent(out(crop, 0), out(crop, 1))
            refined = kit.sample(det['prompt'], neg, [out(crop, 0)] + views[:int(det.get('views', 1))], lat,
                                 seed + DETAIL_SEED, denoise=float(det['strength']), aligned=True,
                                 steps=kit.pass_steps(float(det['strength'])))
            base = seedvr2(g, first, ow, oh, seed) if up else first
            final = out(g.add('EADetailPaste', base=base, refined=refined, crop_mask=out(crop, 1), info=out(crop, 2),
                              width=int(ow), height=int(oh)))
        else:
            final = seedvr2(g, first, ow, oh, seed) if up else first
        extra = {'mask': sam_find(g, final, job['find'])} if job.get('sam') else {}
        g.add('EAFinish', images=final, job=jid, variation=int(variation), raw=first, **extra)
        return g.nodes

    # exact photo
    canvas = out(g.add('EAJobImage', job=jid, name='canvas'))
    draw = out(g.add('EAJobMask', job=jid, name='draw'))
    first = kit.sample(job['prompt'], neg, [canvas] + refs, kit.masked_latent(canvas, draw), seed, aligned=True,
                       upsample=bool(job.get('upsample_prompt')))
    lit = first
    if job.get('relight'):
        view = out(g.add('EAJobImage', job=jid, name='view1'))
        harm = out(g.add('EAJobMask', job=jid, name='harmonize'))
        strength = float(job.get('harmonize_strength', 0.4))
        lit = kit.sample(job['harmonize_prompt'], neg, [first, view], kit.masked_latent(first, harm), seed + DETAIL_SEED,
                         denoise=strength, aligned=True, steps=kit.pass_steps(strength))
    final = seedvr2(g, lit, ow, oh, seed) if up else lit
    g.add('EAFinish', images=final, job=jid, variation=int(variation), raw=first)
    return g.nodes


def cutout_graph(product_id, method='auto', view=''):
    g = Graph()
    g.add('EAProductCutout', product=product_id, method=method, view=view or '')
    return g.nodes


def angles_graphs(product_id, angle_ids, source='main', quality='final', status=None, seed=0):
    """One workflow per new view: Qwen-Image-Edit-2511 with fal's multiple-angles LoRA turns the product's
    picture to another camera angle, and EA Add View keeps it as a model-made photo of the product."""
    F = FAMILIES['qwen']
    opt = (status or {}).get('qwen', {}).get('optional', {})
    labels = {a: lbl for a, lbl, _ in scene.ANGLES}
    graphs = []
    for i, aid in enumerate(angle_ids):
        g = Graph()
        pic = g.add('EAProductPicture', product=product_id, view=source or 'main')
        unet = g.add('UNETLoader', unet_name=F['files']['unet'][1], weight_dtype='default')
        m = g.add('LoraLoaderModelOnly', model=out(unet), lora_name=ANGLES_LORA[1], strength_model=1.0)
        m = g.add('ModelSamplingAuraFlow', model=out(m), shift=3.1)
        m = g.add('CFGNorm', model=out(m), strength=1.0)
        if quality == 'draft' and opt.get('lightning'):
            m = g.add('LoraLoaderModelOnly', model=out(m), lora_name=F['optional']['lightning'][1], strength_model=1.0)
            steps, cfg = 8, 1.0
        else:
            steps, cfg = 40, 4.0
        clip = g.add('CLIPLoader', clip_name=F['files']['clip'][1], type='qwen_image', device='default')
        vae = g.add('VAELoader', vae_name=F['files']['vae'][1])
        scaled = g.add('FluxKontextImageScale', image=out(pic))
        pos = g.add('TextEncodeQwenImageEditPlus', clip=out(clip), prompt=scene.angle_prompt(aid), vae=out(vae), image1=out(scaled))
        neg = g.add('TextEncodeQwenImageEditPlus', clip=out(clip), prompt='', vae=out(vae), image1=out(scaled))
        pos = g.add('FluxKontextMultiReferenceLatentMethod', conditioning=out(pos), reference_latents_method='index_timestep_zero')
        neg = g.add('FluxKontextMultiReferenceLatentMethod', conditioning=out(neg), reference_latents_method='index_timestep_zero')
        lat = g.add('VAEEncode', pixels=out(scaled), vae=out(vae))
        s = g.add('KSampler', model=out(m), seed=int(seed) + i, steps=steps, cfg=cfg, sampler_name='euler', scheduler='simple',
                  positive=out(pos), negative=out(neg), latent_image=out(lat), denoise=1.0)
        dec = g.add('VAEDecode', samples=out(s), vae=out(vae))
        g.add('EAAddView', images=out(dec), product=product_id, label=labels.get(aid, aid), source=source or 'main')
        graphs.append(g.nodes)
    return graphs
