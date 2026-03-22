from __future__ import annotations

from app.models import PresetRule, WatermarkPreset
from app.utils.ids import new_id


def builtin_presets(default_text: str, default_image: str = "") -> list[PresetRule]:
    return [
        PresetRule(preset_id=WatermarkPreset.FULL_FIXED.value, name="Full Fixed", mode="full", watermark_type="image" if default_image else "text", text=default_text, image_path=default_image, position_mode="bottom_right", opacity=0.18, scale=0.12, is_builtin=True),
        PresetRule(preset_id=WatermarkPreset.FIRST_2_MIN.value, name="First 2 Min", mode="window", watermark_type="image" if default_image else "text", text=default_text, image_path=default_image, start_at=0, end_at=120, position_mode="top_right", opacity=0.18, scale=0.12, is_builtin=True),
        PresetRule(preset_id=WatermarkPreset.AFTER_3_MIN.value, name="After 3 Min", mode="after", watermark_type="image" if default_image else "text", text=default_text, image_path=default_image, start_at=180, position_mode="bottom_right", opacity=0.18, scale=0.12, is_builtin=True),
        PresetRule(preset_id=WatermarkPreset.LAST_2_MIN.value, name="Last 2 Min", mode="tail", watermark_type="image" if default_image else "text", text=default_text, image_path=default_image, end_at=120, position_mode="center", opacity=0.16, scale=0.12, is_builtin=True),
        PresetRule(preset_id=WatermarkPreset.EVERY_3_MIN.value, name="Every 3 Min", mode="interval", watermark_type="image" if default_image else "text", text=default_text, image_path=default_image, repeat_every=180, show_for=15, position_mode="random_corners", opacity=0.18, scale=0.12, is_builtin=True),
        PresetRule(preset_id=WatermarkPreset.RANDOM_5.value, name="Random 5 Times", mode="random", watermark_type="image" if default_image else "text", text=default_text, image_path=default_image, random_count=5, show_for=12, position_mode="random_corners", opacity=0.20, scale=0.12, is_builtin=True),
        PresetRule(preset_id=WatermarkPreset.MIXED_SMART.value, name="Mixed Smart", mode="mixed", watermark_type="image" if default_image else "text", text=default_text, image_path=default_image, repeat_every=210, show_for=12, moving=True, position_mode="moving", opacity=0.18, scale=0.12, is_builtin=True),
        PresetRule(preset_id=WatermarkPreset.NONE.value, name="No Watermark", mode="none", watermark_type="text", text="", image_path="", opacity=0.0, scale=0.0, is_builtin=True),
    ]


def build_saved_preset(name: str, template: PresetRule) -> PresetRule:
    return PresetRule(**{**template.to_dict(), "preset_id": new_id("preset"), "name": name, "is_builtin": False})
