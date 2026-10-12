"""CLAP zero-shot classifier (open-vocabulary, contrastive language-audio).

Lets you classify a soundscape against *arbitrary text prompts* with no training
— the "swappable / hackable" open-model story in action. Heavy optional deps
(transformers + torch), imported lazily; the app falls back if unavailable.
"""

from __future__ import annotations

from .. import audio
from ..classify import Label, register

MODEL_ID = "laion/clap-htsat-unfused"
BANDS = 12


@register
class ClapClassifier:
    name = "clap"

    PROMPTS: dict[str, str] = {
        "Wind": "wind blowing through trees",
        "Rain": "rain falling on leaves and ground",
        "Leaves": "dry leaves rustling in the wind",
        "Stream": "a stream or creek of flowing water",
        "Birdsong": "birds singing and chirping",
        "Insects": "insects buzzing and chirping at night",
        "Frogs": "frogs croaking",
        "Thunder": "distant thunder rumbling",
        "Silence": "silence with no distinct sound",
        "Human voices": "people talking in the distance",
        "Traffic": "cars and traffic noise",
    }

    def __init__(self) -> None:
        try:
            import torch
            from transformers import ClapModel, ClapProcessor
        except ImportError as exc:
            raise RuntimeError("clap needs 'transformers' and 'torch'") from exc

        self._torch = torch
        self._processor = ClapProcessor.from_pretrained(MODEL_ID)
        self._model = ClapModel.from_pretrained(MODEL_ID)
        self._model.eval()

    def classify(self, buffer: audio.AudioBuffer, top_n: int = 5) -> list[Label]:
        import numpy as np

        labels = list(self.PROMPTS)
        prompts = [self.PROMPTS[k] for k in labels]

        audio_inputs = self._processor(
            audios=np.asarray(buffer.samples, dtype="float32"),
            sampling_rate=buffer.sample_rate,
            return_tensors="pt",
        )
        text_inputs = self._processor(text=prompts, return_tensors="pt", padding=True)
        with self._torch.no_grad():
            out = self._model(**audio_inputs, **text_inputs)
            probs = out.logits_per_audio.softmax(dim=1)[0]

        ranked = sorted(zip(labels, probs.tolist(), strict=False), key=lambda p: p[1], reverse=True)
        return [Label(name, round(float(score), 3)) for name, score in ranked[:top_n]]