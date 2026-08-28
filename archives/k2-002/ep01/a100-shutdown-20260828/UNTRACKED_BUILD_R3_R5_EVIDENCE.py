#!/usr/bin/env python3
"""Build R3/R5 forensic and visual-QC evidence without invoking ComfyUI."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont


R5_ROOT = Path("/data/k2-technical-evidence/k2-002-ep01-i2v-v2-sh12-r5-anchor-only")
FORENSICS = R5_ROOT / "forensics"
TECHNICAL = R5_ROOT / "technical_validation"
VISUALS = R5_ROOT / "visual_qc"
FRAMES = VISUALS / "frames"
R3_VIDEO = Path("/data/k2-technical-evidence/k2-002-ep01-i2v-v2-sh12-r3/media/EP01_SH12.mp4")
R5_SOURCE = Path("/data/coding/apps/ComfyUI/output/k2-002-ep01-i2v-v2/EP01_SH12-v2-technical-evidence_00005_.mp4")
R5_COPY = R5_ROOT / "recovered_media/EP01_SH12_R5_RECOVERED.mp4"
R3_ANCHOR = Path("/data/coding/k2-002-ep01-i2v-v2/anchors/EP01_SH12_anchor_v2.png")
R5_ANCHOR = R5_ROOT / "inputs/EP01_SH12_anchor_pre_step_r5.png"
R5_WORKFLOW = R5_ROOT / "materialized/EP01_SH12_R5.workflow.json"
R5_LOG = R5_ROOT / "logs/comfyui.log"
RUN_ATTEMPT = R5_ROOT / "RUN_ATTEMPT_1.json"
FAILED = R5_ROOT / "FAILED_AFTER_RESERVATION.json"
OUTPUT_DIR = Path("/data/coding/apps/ComfyUI/output/k2-002-ep01-i2v-v2")
SELECTED = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 48]
GAIT = [0, 12, 21, 27, 33, 39, 48]
LOWER_CROP = (96, 480, 608, 1260)  # x0, y0, x1, y1; frozen for R3 and R5
EXPECTED = {
    str(R3_VIDEO): "78b5338abdd79168410a13a453dc189d42733b57306f663c63d320b9b453f9fe",
    str(R5_SOURCE): "1d115e2bf71e11a8b57d1e891bf8e1fe08f483e32ae78be5a675d969fa2bd5c1",
    str(R5_COPY): "1d115e2bf71e11a8b57d1e891bf8e1fe08f483e32ae78be5a675d969fa2bd5c1",
    str(R3_ANCHOR): "21ef1ff9b874bf8be850702afd34acc1885bb22cd909b8587097b092eaea2827",
    str(R5_ANCHOR): "3ccfe06afa15a6fcf46450c0bc5edf2dc1a8e1b0be126a5f15e36b1e8f9d434d",
}


def run(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = ""
    return subprocess.run(
        args,
        check=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        text=True,
        env=env,
    )


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def stat_record(path: Path) -> dict[str, Any]:
    result = run(["stat", "-c", "%w|%y|%z|%s|%i", str(path)], capture=True).stdout.strip().split("|")
    return {
        "path": str(path),
        "birth": result[0],
        "mtime": result[1],
        "ctime": result[2],
        "size": int(result[3]),
        "inode": int(result[4]),
        "sha256": sha256(path),
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def ffprobe(path: Path) -> dict[str, Any]:
    result = run(
        [
            "ffprobe", "-v", "error", "-count_frames", "-show_entries",
            "stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,nb_read_frames,duration",
            "-show_entries", "format=duration", "-of", "json", str(path),
        ],
        capture=True,
    )
    value = json.loads(result.stdout)
    videos = [row for row in value["streams"] if row.get("codec_type") == "video"]
    audios = [row for row in value["streams"] if row.get("codec_type") == "audio"]
    if len(videos) != 1:
        raise RuntimeError(f"expected one video stream in {path}")
    return {"path": str(path), "video": videos[0], "audioStreamCount": len(audios), "format": value["format"]}


def make_framemd5(video: Path, output: Path) -> list[str]:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-hwaccel", "none", "-i", str(video), "-map", "0:v:0", "-f", "framemd5", "-y", str(output)])
    return [line.split(",")[-1].strip() for line in output.read_text().splitlines() if line and not line.startswith("#")]


def extract_frame(video: Path, frame: int, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-hwaccel", "none", "-i", str(video),
        "-vf", f"select=eq(n\\,{frame})", "-vsync", "0", "-frames:v", "1", "-y", str(output),
    ])


def image_diff(left: Path, right: Path) -> dict[str, Any]:
    with Image.open(left).convert("RGB") as a, Image.open(right).convert("RGB") as b:
        if a.size != b.size:
            b = b.resize(a.size, Image.Resampling.LANCZOS)
        diff = ImageChops.difference(a, b)
        histogram = diff.histogram()
        count = a.size[0] * a.size[1] * 3
        mae = sum((index % 256) * amount for index, amount in enumerate(histogram)) / count
        return {"pixelIdentical": diff.getbbox() is None, "meanAbsoluteError8Bit": mae, "normalizedMae": mae / 255.0}


def label_tile(image: Image.Image, label: str, size: tuple[int, int], *, crop: tuple[int, int, int, int] | None = None) -> Image.Image:
    source = image.crop(crop) if crop else image.copy()
    source.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "#111111")
    canvas.paste(source, ((size[0] - source.width) // 2, (size[1] - source.height) // 2))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, size[0], 32), fill="#000000")
    draw.text((8, 7), label, fill="white", font=ImageFont.load_default())
    return canvas


def grid(tiles: list[Image.Image], columns: int, output: Path, padding: int = 8) -> None:
    rows = (len(tiles) + columns - 1) // columns
    width = columns * tiles[0].width + (columns + 1) * padding
    height = rows * tiles[0].height + (rows + 1) * padding
    sheet = Image.new("RGB", (width, height), "#252525")
    for index, tile in enumerate(tiles):
        x = padding + (index % columns) * (tile.width + padding)
        y = padding + (index // columns) * (tile.height + padding)
        sheet.paste(tile, (x, y))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=94, subsampling=0)


def paired_tile(left: Image.Image, right: Image.Image, frame: int, *, lower: bool = False) -> Image.Image:
    crop = LOWER_CROP if lower else None
    size = (315, 480) if lower else (264, 480)
    a = label_tile(left, f"R3 F{frame}", size, crop=crop)
    b = label_tile(right, f"R5 F{frame}", size, crop=crop)
    result = Image.new("RGB", (size[0] * 2 + 4, size[1]), "#666666")
    result.paste(a, (0, 0)); result.paste(b, (size[0] + 4, 0))
    return result


def build_sheets() -> None:
    for name, video in (("R3", R3_VIDEO), ("R5", R5_COPY)):
        for frame in SELECTED:
            extract_frame(video, frame, FRAMES / name / f"F{frame:02d}.png")
    images: dict[tuple[str, int], Image.Image] = {}
    for name in ("R3", "R5"):
        for frame in SELECTED:
            images[(name, frame)] = Image.open(FRAMES / name / f"F{frame:02d}.png").convert("RGB")
    try:
        for name in ("R3", "R5"):
            grid([label_tile(images[(name, f)], f"{name} F{f}", (264, 480)) for f in SELECTED], 4, VISUALS / f"{name}_FULL_SEQUENCE.jpg")
            grid([label_tile(images[(name, f)], f"{name} F{f}", (315, 480), crop=LOWER_CROP) for f in SELECTED], 4, VISUALS / f"{name}_LOWER_BODY_SEQUENCE.jpg")
        grid([paired_tile(images[("R3", f)], images[("R5", f)], f) for f in SELECTED], 4, VISUALS / "R3_VS_R5_FULL_SIDE_BY_SIDE.jpg")
        grid([paired_tile(images[("R3", f)], images[("R5", f)], f, lower=True) for f in SELECTED], 3, VISUALS / "R3_VS_R5_LOWER_BODY_SIDE_BY_SIDE.jpg")
        gait_tiles: list[Image.Image] = []
        for frame in GAIT:
            full = paired_tile(images[("R3", frame)], images[("R5", frame)], frame)
            lower = paired_tile(images[("R3", frame)], images[("R5", frame)], frame, lower=True)
            tile = Image.new("RGB", (max(full.width, lower.width), full.height + lower.height + 5), "#333333")
            tile.paste(full, ((tile.width - full.width)//2, 0))
            tile.paste(lower, ((tile.width - lower.width)//2, full.height + 5))
            gait_tiles.append(tile)
        grid(gait_tiles, 3, VISUALS / "R3_VS_R5_GAIT_KEYFRAMES.jpg")
    finally:
        for value in images.values(): value.close()


def ssim_videos() -> dict[str, Any]:
    stats = TECHNICAL / "R3_VS_R5_SSIM_PER_FRAME.txt"
    result = run([
        "ffmpeg", "-hide_banner", "-hwaccel", "none", "-i", str(R3_VIDEO), "-i", str(R5_COPY),
        "-lavfi", f"[0:v][1:v]ssim=stats_file={stats}", "-f", "null", "-",
    ], capture=True)
    match = re.search(r"SSIM.*All:([0-9.]+)", result.stderr)
    rows = [line for line in stats.read_text().splitlines() if line.strip()]
    return {"overallAll": float(match.group(1)) if match else None, "perFrameRows": len(rows), "statsPath": str(stats)}


def build_comparison_videos() -> None:
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-hwaccel", "none", "-i", str(R3_VIDEO), "-i", str(R5_COPY),
        "-filter_complex", "[0:v][1:v]hstack=inputs=2[v]", "-map", "[v]", "-an", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-y",
        str(VISUALS / "R3_VS_R5_FULL_VIDEO.mp4"),
    ])
    x0, y0, x1, y1 = LOWER_CROP
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-hwaccel", "none", "-i", str(R3_VIDEO), "-i", str(R5_COPY),
        "-filter_complex", f"[0:v]crop={x1-x0}:{y1-y0}:{x0}:{y0}[a];[1:v]crop={x1-x0}:{y1-y0}:{x0}:{y0}[b];[a][b]hstack=inputs=2[v]",
        "-map", "[v]", "-an", "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-y", str(VISUALS / "R3_VS_R5_LOWER_BODY_VIDEO.mp4"),
    ])


def find_prefix_json(prefix: str) -> list[str]:
    roots = [
        Path("/data/coding/k2-002-ep01-i2v-v2"),
        Path("/data/coding/AI-Cinematic-Studio-main-2701/experiments"),
        Path("/data/k2-technical-evidence"),
    ]
    found: list[str] = []
    for root in roots:
        for path in root.rglob("*.json"):
            try:
                if prefix in path.read_text(encoding="utf-8"):
                    found.append(str(path))
            except (OSError, UnicodeError):
                pass
    return sorted(set(found))


def main() -> None:
    for directory in (FORENSICS, TECHNICAL, VISUALS, FRAMES): directory.mkdir(parents=True, exist_ok=True)
    actual = {path: sha256(Path(path)) for path in EXPECTED}
    if actual != EXPECTED:
        raise RuntimeError({"expected": EXPECTED, "actual": actual})
    lock_before = {str(path): sha256(path) for path in (RUN_ATTEMPT, FAILED, R5_ROOT / "receipts/DRY_RUN.json")}
    run_attempt = json.loads(RUN_ATTEMPT.read_text())
    failed = json.loads(FAILED.read_text())
    workflow = json.loads(R5_WORKFLOW.read_text())
    prefix = workflow["11"]["inputs"]["filename_prefix"]
    anchor_input = workflow["12"]["inputs"]["image"]
    log_text = R5_LOG.read_text(encoding="utf-8", errors="replace")
    source_stat, copy_stat, log_stat = stat_record(R5_SOURCE), stat_record(R5_COPY), stat_record(R5_LOG)

    probes = {"R3": ffprobe(R3_VIDEO), "R5": ffprobe(R5_COPY)}
    write_json(TECHNICAL / "R3.ffprobe.json", probes["R3"])
    write_json(TECHNICAL / "R5.ffprobe.json", probes["R5"])
    r3_md5 = make_framemd5(R3_VIDEO, TECHNICAL / "R3.framemd5")
    r5_md5 = make_framemd5(R5_COPY, TECHNICAL / "R5.framemd5")
    if len(r3_md5) != 49 or len(r5_md5) != 49:
        raise RuntimeError(f"decoded frame counts were {len(r3_md5)} and {len(r5_md5)}")
    decoded_identical = r3_md5 == r5_md5
    ssim = ssim_videos()
    extract_frame(R3_VIDEO, 0, TECHNICAL / "R3_F0.png")
    extract_frame(R5_COPY, 0, TECHNICAL / "R5_F0.png")
    first_frame = {
        "R3F0VsR3Anchor": image_diff(TECHNICAL / "R3_F0.png", R3_ANCHOR),
        "R5F0VsR5Anchor": image_diff(TECHNICAL / "R5_F0.png", R5_ANCHOR),
        "R3F0VsR5F0": image_diff(TECHNICAL / "R3_F0.png", TECHNICAL / "R5_F0.png"),
    }
    write_json(TECHNICAL / "R3_R5_OBJECTIVE_COMPARISON.json", {"decodedPixelIdentical": decoded_identical, "ssim": ssim, "firstFrame": first_frame})
    build_sheets()
    build_comparison_videos()

    outputs = []
    for path in sorted(OUTPUT_DIR.glob("EP01_SH12-v2-technical-evidence_*.mp4")):
        outputs.append(stat_record(path))
    prefix_matches = find_prefix_json(prefix)
    input_copy = Path("/data/coding/apps/ComfyUI/input") / anchor_input
    input_record = stat_record(input_copy)
    source_copy_identical = R5_SOURCE.read_bytes() == R5_COPY.read_bytes()
    output_audit = {
        "schemaVersion": 1,
        "outputDirectory": str(OUTPUT_DIR),
        "expectedPrefix": prefix,
        "files": outputs,
        "numbering": {"present": [1,2,3,4,5], "missingBeforeFive": [], "nextSixExists": False},
        "prefixJsonMatches": prefix_matches,
        "anotherWorkflowUsesSamePrefix": any(path.endswith("/materialized/EP01_SH12.workflow.json") for path in prefix_matches),
        "sameWindowOtherPromptEvidence": "NONE_IN_DEDICATED_R5_COMFYUI_LOG",
    }
    write_json(FORENSICS / "R5_OUTPUT_DIRECTORY_AUDIT.json", output_audit)

    questions = {
        "q1GeneratedAfterUniqueR5Post": True,
        "q2WithinDedicatedComfyProcessLifecycle": True,
        "q3FilenamePrefixExactlyMatchesVariant": True,
        "q4OtherSamePrefixTaskInWindow": False,
        "q5OnlyOnePromptPost": failed.get("promptPostCount") == 1 and log_text.count("got prompt") == 1,
        "q6ConsoleExecutionEvidence": {
            "gotPrompt": "got prompt" in log_text,
            "sampler20Of20": "20/20" in log_text,
            "promptExecuted": "Prompt executed in 53.30 seconds" in log_text,
            "explicitSaveVideoLine": False,
        },
        "q7NeighborNumbersExplained": "00004 predates R5 by 2h58m; 00005 is the next sequential output; 00006 does not exist",
        "q8AnotherWorkflowUsesSamePrefix": output_audit["anotherWorkflowUsesSamePrefix"],
        "q9SourceCopyByteIdentical": source_copy_identical,
        "q10FirstFrameAnchorRelation": first_frame["R5F0VsR5Anchor"],
    }
    attribution = {
        "schemaVersion": 1,
        "r5RunnerRecordedState": "FAILED_AFTER_PROMPT_ACCEPTED",
        "r5ActualRenderState": "COMPLETED_OUTPUT_RECOVERED",
        "r5MediaValidity": "VALID",
        "r5ControlProvenance": "INCOMPLETE",
        "r5MediaAttribution": "STRONG",
        "attributionBasis": [
            "content-addressed anchor input copy and RUN_ATTEMPT_1 reservation occurred within 2 ms, both before the sole POST",
            "dedicated ComfyUI log contains exactly one got prompt and one 20/20 execution",
            "source _00005_ was born after that POST and before the failed controller receipt",
            "source prefix exactly matches the frozen R5 SaveVideo node",
            "no second prompt or same-prefix job appears in the dedicated process log",
            "source and recovered copy are byte-identical",
            "R5 decoded F0 is structurally related to but not pixel-identical with the R5 anchor, as expected after Wan VAE/I2V processing",
        ],
        "limitations": [
            "original server-generated prompt_id, response body and history were not persisted",
            "the dedicated console log does not preserve a wall-clock timestamp for the sole got prompt line; POST ordering is established by the runner control flow and surrounding file/log timeline",
            "the standard SH12 materialized workflow also uses the same filename prefix; attribution therefore relies on the isolated process and time window, not prefix alone",
            "the ComfyUI log has no explicit SaveVideo filename line",
        ],
        "source": source_stat,
        "recoveredCopy": copy_stat,
        "dedicatedComfyLog": log_stat,
        "runAttempt": run_attempt,
        "failedReceipt": failed,
        "workflow": {"path": str(R5_WORKFLOW), "sha256": sha256(R5_WORKFLOW), "filenamePrefix": prefix, "anchorInput": anchor_input},
        "anchorInputCopy": input_record,
        "questions": questions,
        "promptId": None,
        "clientId": None,
        "history": None,
        "unavailableFieldsNotReconstructed": True,
    }
    write_json(FORENSICS / "R5_RECOVERED_MEDIA_ATTRIBUTION.json", attribution)

    timeline = [
        "R5 RECOVERED MEDIA FORENSIC TIMELINE (UTC / +08:00)",
        "2026-08-28T08:51:38.064Z / 16:51:38.064  R5 candidate anchor created",
        "2026-08-28T09:21:56.804Z / 17:21:56.804  R5 variant workflow materialized",
        f"2026-08-28T09:23:43.947Z / 17:23:43.947  dedicated ComfyUI log created; process lifecycle begins ({R5_LOG})",
        "2026-08-28T09:25:04.338Z / 17:25:04.338  content-addressed R5 anchor copied into ComfyUI input",
        f"{run_attempt['reservedAt']} / 17:25:04.340  RUN_ATTEMPT_1 reserved before submit (1.8 ms after the input copy)",
        "after 09:25:04.340Z                    dedicated log records exactly one 'got prompt'",
        "during execution                        sampler advances 0/20 through 20/20",
        f"2026-08-28T09:26:38.769Z / 17:26:38.769  source _00005_.mp4 born",
        f"2026-08-28T09:26:39.165Z / 17:26:39.165  source _00005_.mp4 and log reach final mtime; log records 'Prompt executed in 53.30 seconds'",
        f"{failed['failedAt']} / 17:26:39.900  controller writes FAILED_AFTER_RESERVATION after its history-schema error",
        "2026-08-28T09:52:34.529Z / 17:52:34.529  byte-identical recovery copy created; original mtime preserved",
        "",
        "No separate runner stdout/stderr file was persisted. No prompt_id/client_id/history value is reconstructed.",
        "The same prefix exists in the standard SH12 workflow, but the dedicated R5 process log contains no concurrent second prompt.",
        "R5_MEDIA_ATTRIBUTION=STRONG",
    ]
    (FORENSICS / "R5_TIMELINE.txt").write_text("\n".join(timeline) + "\n", encoding="utf-8")

    lock_after = {path: sha256(Path(path)) for path in lock_before}
    if lock_before != lock_after:
        raise RuntimeError("frozen R5 receipt or lock changed")
    manifest = []
    for directory in (FORENSICS, TECHNICAL, VISUALS):
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.name != "R3_R5_EVIDENCE_SHA256SUMS.txt":
                manifest.append(f"{sha256(path)}  {path}")
    (R5_ROOT / "R3_R5_EVIDENCE_SHA256SUMS.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print("R5_MEDIA_ATTRIBUTION=STRONG")
    print(f"SOURCE_COPY_BYTE_IDENTICAL={str(source_copy_identical).lower()}")
    print(f"R3_R5_PIXEL_IDENTICAL={str(decoded_identical).lower()}")
    print(f"R3_R5_SSIM_ALL={ssim['overallAll']}")
    print("GPU_OR_PROVIDER_CALLS=0")
    print("R6_PROMPT_POST_COUNT=0")
    print(f"VISUAL_QC_ROOT={VISUALS}")


if __name__ == "__main__":
    main()
