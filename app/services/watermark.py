from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Awaitable, Callable

from app.models import PresetRule

ProgressCb = Callable[[str, float, str, str], Awaitable[None]]


def _enable_expr(rule: PresetRule) -> str | None:
    if rule.mode == "none":
        return None
    if rule.mode == "full":
        return None
    if rule.mode == "window":
        return f"between(t,{rule.start_at},{rule.end_at})"
    if rule.mode == "after":
        return f"gte(t,{rule.start_at})"
    if rule.mode == "tail":
        return f"gte(t,duration-{rule.end_at})"
    if rule.mode == "interval":
        return f"between(mod(t,{max(rule.repeat_every,1)}),0,{max(rule.show_for,1)})"
    if rule.mode == "random":
        interval = max(rule.repeat_every or 45, rule.show_for * 3 or 30)
        return f"between(mod(t,{interval}),0,{max(rule.show_for,8)})"
    if rule.mode == "mixed":
        interval = max(rule.repeat_every or 210, 60)
        show_for = max(rule.show_for or 12, 8)
        return f"if(lt(t,20),1,between(mod(t,{interval}),0,{show_for}))"
    return None


def _position(rule: PresetRule) -> tuple[str, str]:
    mode = rule.position_mode
    margin = 20
    if mode == "top_right":
        return f"W-w-{margin}", f"{margin}"
    if mode == "top_left":
        return f"{margin}", f"{margin}"
    if mode == "bottom_left":
        return f"{margin}", f"H-h-{margin}"
    if mode == "center":
        return "(W-w)/2", "(H-h)/2"
    if mode == "random_corners":
        return (
            f"if(lt(mod(t,40),10),{margin}, if(lt(mod(t,40),20),W-w-{margin}, if(lt(mod(t,40),30),{margin}, W-w-{margin})))",
            f"if(lt(mod(t,40),20),{margin},H-h-{margin})",
        )
    if mode == "random_anywhere":
        x = f"{margin}+(W-w-{margin*2})*(0.5+0.5*sin(floor(t/5)*13.13))"
        y = f"{margin}+(H-h-{margin*2})*(0.5+0.5*sin(floor(t/5)*17.71+1.7))"
        return x, y
    if mode == "smooth_anywhere":
        x = f"{margin}+(W-w-{margin*2})*(0.5+0.5*sin(t/3.7))"
        y = f"{margin}+(H-h-{margin*2})*(0.5+0.5*cos(t/4.9))"
        return x, y
    if mode == "moving":
        x = f"{margin}+(W-w-{margin*2})*(0.5+0.5*sin(t/3.2))"
        y = f"{margin}+(H-h-{margin*2})*(0.5+0.5*sin(t/5.1+0.7))"
        return x, y
    return f"W-w-{margin}", f"H-h-{margin}"


def build_filter(rule: PresetRule) -> str:
    enable = _enable_expr(rule)
    x, y = _position(rule)
    if rule.watermark_type == "image" and rule.image_path:
        alpha = max(0.0, min(rule.opacity, 1.0))
        overlay = f"[1:v]format=rgba,colorchannelmixer=aa={alpha}[wm];[0:v][wm]overlay={x}:{y}"
        if enable:
            overlay += f":enable='{enable}'"
        return overlay
    text = (rule.text or "").replace("'", "\\'").replace(":", "\\:")
    alpha = max(0.05, min(rule.opacity, 1.0))
    size = max(rule.scale, 0.03)
    draw = (
        f"drawtext=text='{text}':fontsize=h*{size:.3f}:fontcolor=white@{alpha}:"
        f"x={x}:y={y}:box=1:boxcolor=black@0.25:boxborderw=10"
    )
    if enable:
        draw += f":enable='{enable}'"
    return draw


async def probe_duration(ffprobe_bin: str, input_path: Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(input_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        return 0.0
    try:
        return float(out.decode().strip() or 0)
    except ValueError:
        return 0.0


def _format_clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


async def run_ffmpeg(cmd: list[str], duration: float = 0.0, progress_cb: ProgressCb | None = None, stage: str = "Processing") -> None:
    full_cmd = list(cmd)
    if "-progress" not in full_cmd:
        full_cmd[1:1] = ["-progress", "pipe:1", "-nostats"]
    proc = await asyncio.create_subprocess_exec(*full_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stderr_task = asyncio.create_task(proc.stderr.read())
    out_time = 0.0
    last_percent = -1.0
    if progress_cb:
        await progress_cb(stage, 0.0, "00:00", _format_clock(duration))
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="ignore").strip()
        if not text or "=" not in text:
            continue
        key, value = text.split("=", 1)
        if key == "out_time_ms":
            try:
                out_time = int(value) / 1_000_000
            except ValueError:
                out_time = 0.0
        elif key == "progress" and progress_cb:
            percent = min(100.0, (out_time / duration * 100.0) if duration > 0 else 0.0)
            if int(percent) != int(last_percent) or value == "end":
                last_percent = percent
                await progress_cb(stage, percent, _format_clock(out_time), _format_clock(duration))
    stderr = (await stderr_task).decode("utf-8", errors="ignore")
    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(stderr[-1200:])
    if progress_cb:
        await progress_cb(stage, 100.0, _format_clock(duration), _format_clock(duration))


async def preview_clip(ffmpeg_bin: str, ffprobe_bin: str, input_path: Path, output_path: Path, progress_cb: ProgressCb | None = None) -> None:
    duration = min(20.0, await probe_duration(ffprobe_bin, input_path) or 20.0)
    await run_ffmpeg([ffmpeg_bin, "-y", "-i", str(input_path), "-t", "20", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(output_path)], duration, progress_cb, stage="Preview")


async def watermark_video(ffmpeg_bin: str, ffprobe_bin: str, input_path: Path, output_path: Path, rule: PresetRule, progress_cb: ProgressCb | None = None) -> None:
    filter_expr = build_filter(rule)
    cmd = [ffmpeg_bin, "-y", "-i", str(input_path)]
    if rule.watermark_type == "image" and rule.image_path:
        cmd.extend(["-i", str(rule.image_path), "-filter_complex", filter_expr])
    else:
        cmd.extend(["-vf", filter_expr])
    cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", str(output_path)])
    duration = await probe_duration(ffprobe_bin, input_path)
    await run_ffmpeg(cmd, duration, progress_cb, stage="Watermarking")
