#!/usr/bin/python3
"""Repository fake for real M12 subprocess/stdin/stdout/fd tests only.

The fake deliberately does not import Core or any ML package.  Behaviour switches
are encoded only in a TEST-prefixed output binding and are never accepted by the
production manifest adapter.
"""

from __future__ import annotations

from array import array
from hashlib import sha256
import json
import math
import os
import sys
import time
import wave


KOKORO_OPERATION = "KOKORO_SYNTHESIZE_FIXED_VOICE"
PROFILE_OPERATION = "COSYVOICE_BUILD_VOICE_PROFILE"
DIALOGUE_OPERATION = "COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE"
KOKORO_RESPONSE = "m12.kokoro-runtime-response.v1"
PROFILE_RESPONSE = "m12.cosyvoice-profile-response.v1"
DIALOGUE_RESPONSE = "m12.cosyvoice-dialogue-response.v1"
KOKORO_COMMIT = "dfb907a02bba8152ca444717ca5d78747ccb4bec"
COSYVOICE_COMMIT = "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc"
MATCHA_COMMIT = "dd9105b34bf2be2230f4aa1e4769fb586a3c824e"
KOKORO_MODEL = "849ed6061f60a9b82ba13ff9538380fca4014fe19f1762475ab0997a2590cc92"
COSYVOICE_MODEL = "f17e288095c0514ad4bc8d7bfc976363d1bcb3f1ab5ff4e276c014740125e83d"
FAKE_DEPENDENCY_LOCK = "a" * 64
FIXED_TIME = "2026-08-30T00:00:00Z"


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value):
    return sha256(canonical(value)).hexdigest()


def seal(value):
    result = dict(value)
    result["payloadDigest"] = digest(result)
    return result


def read_transport():
    raw = sys.stdin.buffer.read(1_000_001)
    if not raw or len(raw) > 1_000_000:
        raise ValueError("transport size")
    value = json.loads(raw)
    if set(value) != {
        "schemaVersion",
        "request",
        "sourceRecordingFd",
        "voiceProfilePackageFd",
        "outputAudioArtifactFd",
        "outputProfilePackageFd",
    } or value["schemaVersion"] != "m12.isolated-runtime-transport.v1":
        raise ValueError("transport shape")
    request = value["request"]
    supplied = request.get("payloadDigest")
    unsigned = dict(request)
    unsigned.pop("payloadDigest", None)
    if supplied != digest(unsigned):
        raise ValueError("request digest")
    return value, request


def mode(request):
    binding = request["outputArtifactBindingRef"]
    marker = "test-output-"
    return binding[len(marker) :] if binding.startswith(marker) else "pass"


def wav_bytes(*, clipping=False):
    sample_rate = 48_000
    sample_count = 48_000
    samples = array("h")
    canonical_stereo = array("h")
    for index in range(sample_count):
        if clipping and index == 500:
            sample = 32_767
        else:
            sample = int(2_000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        samples.append(sample)
        canonical_stereo.extend((sample, sample))
    import io

    target = io.BytesIO()
    with wave.open(target, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(samples.tobytes())
    return (
        target.getvalue(),
        sample_count,
        sha256(canonical_stereo.tobytes()).hexdigest(),
    )


def source_wav_facts(descriptor):
    duplicate = os.dup(descriptor)
    with os.fdopen(duplicate, "rb") as source:
        with wave.open(source, "rb") as reader:
            channels = reader.getnchannels()
            sample_rate = reader.getframerate()
            sample_count = reader.getnframes()
            width = reader.getsampwidth()
            frames = reader.readframes(sample_count)
    if channels not in {1, 2} or width != 2 or sample_rate != 48_000:
        raise ValueError("source format")
    values = array("h")
    values.frombytes(frames)
    if channels == 1:
        canonical_stereo = array("h")
        for value in values:
            canonical_stereo.extend((value, value))
        canonical_pcm = canonical_stereo.tobytes()
    else:
        canonical_pcm = values.tobytes()
    return sample_rate, channels, sample_count, sha256(canonical_pcm).hexdigest()


def main():
    transport, request = read_transport()
    selected_mode = mode(request)
    if selected_mode == "timeout":
        time.sleep(30)
    if selected_mode == "nonzero":
        return 17
    if request["operationKind"] == PROFILE_OPERATION:
        source_fd = transport["sourceRecordingFd"]
        if not isinstance(source_fd, int):
            return 18
        if any(
            transport[key] is not None
            for key in ("voiceProfilePackageFd", "outputAudioArtifactFd")
        ) or not isinstance(transport["outputProfilePackageFd"], int):
            return 22
        try:
            (
                source_sample_rate,
                source_channels,
                source_sample_count,
                source_pcm_digest,
            ) = source_wav_facts(source_fd)
        except (OSError, ValueError, wave.Error):
            return 19
        if (
            source_pcm_digest
            != request["inputLineageRefsAndDigests"]["audioPcmContentDigest"]
        ):
            return 25
    elif request["operationKind"] == DIALOGUE_OPERATION:
        if (
            transport["sourceRecordingFd"] is not None
            or not isinstance(transport["voiceProfilePackageFd"], int)
            or not isinstance(transport["outputAudioArtifactFd"], int)
            or transport["outputProfilePackageFd"] is not None
        ):
            return 23
        profile_fd = transport["voiceProfilePackageFd"]
        os.lseek(profile_fd, 0, os.SEEK_SET)
        if not os.read(profile_fd, 1):
            return 24
    elif (
        transport["sourceRecordingFd"] is not None
        or transport["voiceProfilePackageFd"] is not None
        or not isinstance(transport["outputAudioArtifactFd"], int)
        or transport["outputProfilePackageFd"] is not None
    ):
        return 20

    output_fd = (
        transport["outputProfilePackageFd"]
        if request["operationKind"] == PROFILE_OPERATION
        else transport["outputAudioArtifactFd"]
    )
    if not isinstance(output_fd, int):
        return 21
    if request["operationKind"] == PROFILE_OPERATION:
        content = canonical(
            {
                "schemaVersion": "voice-profile-package.v1",
                "sourceRecordingBindingRef": request[
                    "inputLineageRefsAndDigests"
                ]["sourceRecordingBindingRef"],
                "sourceRecordingBindingDigest": request[
                    "inputLineageRefsAndDigests"
                ]["sourceRecordingBindingDigest"],
                "audioPcmContentDigest": source_pcm_digest,
                "fixtureState": "TEST_FIXTURE_ONLY",
            }
        )
        sample_rate = source_sample_rate
        channel_count = source_channels
        sample_count = source_sample_count
        pcm_digest = source_pcm_digest
    else:
        content, sample_count, pcm_digest = wav_bytes(
            clipping=selected_mode == "clipping"
        )
        sample_rate = 48_000
        channel_count = 1
    os.lseek(output_fd, 0, os.SEEK_SET)
    os.write(output_fd, content)
    os.ftruncate(output_fd, len(content))
    os.fsync(output_fd)
    file_digest = sha256(content).hexdigest()
    operation = request["operationKind"]
    duration_divisor = math.gcd(sample_count, sample_rate)
    response_schema = {
        KOKORO_OPERATION: KOKORO_RESPONSE,
        PROFILE_OPERATION: PROFILE_RESPONSE,
        DIALOGUE_OPERATION: DIALOGUE_RESPONSE,
    }[operation]
    device_semantic = {
        "deviceType": "CPU",
        "deviceCount": 1,
        "gpuUsed": False,
    }
    response = {
        "schemaVersion": response_schema,
        "requestRef": request["requestRef"],
        "requestDigest": request["payloadDigest"],
        "operationKind": operation,
        "engineCommit": (
            KOKORO_COMMIT if operation == KOKORO_OPERATION else COSYVOICE_COMMIT
        ),
        "matchaTtsCommit": (
            None if operation == KOKORO_OPERATION else MATCHA_COMMIT
        ),
        "modelBundleDigest": (
            KOKORO_MODEL if operation == KOKORO_OPERATION else COSYVOICE_MODEL
        ),
        "dependencyLockDigest": FAKE_DEPENDENCY_LOCK,
        "runtimeManifestDigest": request["runtimeManifestDigest"],
        "outputByteSize": len(content),
        "outputFileDigest": file_digest,
        "outputPcmContentDigest": (
            request["inputLineageRefsAndDigests"]["audioPcmContentDigest"]
            if operation == PROFILE_OPERATION
            else pcm_digest
        ),
        "mediaProbe": {
            "codec": "pcm_s16le",
            "sampleRate": sample_rate,
            "channelCount": channel_count,
            "sampleCount": sample_count,
            "durationRational": {
                "numerator": sample_count // duration_divisor,
                "denominator": sample_rate // duration_divisor,
            },
        },
        "deviceFacts": {
            **device_semantic,
            "deviceFactsDigest": digest(device_semantic),
        },
        "networkUsed": selected_mode == "network",
        "executionStartedAt": FIXED_TIME,
        "executionCompletedAt": FIXED_TIME,
    }
    if operation == PROFILE_OPERATION:
        response.update(
            {
                "profilePackageByteSize": len(content),
                "profilePackageFileDigest": file_digest,
                "profilePackageContentDigest": file_digest,
                "profilePackageSchemaVersion": "voice-profile-package.v1",
            }
        )
    if selected_mode == "engine-drift":
        response["engineCommit"] = "0" * 40
    elif selected_mode == "model-drift":
        response["modelBundleDigest"] = "0" * 64
    elif selected_mode == "dependency-drift":
        response["dependencyLockDigest"] = "0" * 64
    elif selected_mode == "runtime-drift":
        response["runtimeManifestDigest"] = "0" * 64
    elif selected_mode == "file-digest-drift":
        response["outputFileDigest"] = "0" * 64
    elif selected_mode == "pcm-digest-drift":
        response["outputPcmContentDigest"] = "0" * 64
    elif selected_mode == "probe-drift":
        response["mediaProbe"]["sampleCount"] = 96_000
        response["mediaProbe"]["durationRational"] = {
            "numerator": 2,
            "denominator": 1,
        }

    sealed = seal(response)
    if selected_mode == "response-digest":
        sealed["payloadDigest"] = "0" * 64
    if selected_mode == "malformed":
        sys.stdout.write("{")
    elif selected_mode == "extra-stdout":
        sys.stdout.write("unexpected\n" + canonical(sealed).decode("utf-8"))
    else:
        sys.stdout.buffer.write(canonical(sealed) + b"\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(99)
