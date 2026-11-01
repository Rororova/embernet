"""Generate one EMBERNET film clip through Higgsfield Seedance 2.5. Each run is billable."""

import argparse
import json
import sys
from pathlib import Path
from urllib.request import urlopen

import higgsfield_client
from dotenv import load_dotenv

OUTPUT = Path("artifacts/film")
DRONE = (
    "matte-black heavy-lift multirotor drone with long slim carbon arms, a compact body topped by a "
    "grey ribbed rectangular payload box, tall thin black landing legs with rounded feet, an "
    "underslung gimbal with a multi-lens sensor head, and one green and one red LED, exactly "
    "matching the reference image"
)
STYLE = (
    "Photoreal cinematic film, anamorphic lens, natural motion, deep blue night tones and orange "
    "firelight. No on-screen text, subtitles, logos or watermarks."
)
CLIPS = {
    "1": {
        "model": "bytedance/seedance-2.5/reference-to-video",
        "duration": 6,
        "prompt": (
            "Night in Los Angeles. A slow horizontal camera move, far from the scene, shows an empty "
            "road with a large warehouse beyond it and an orange glow rising behind the hills. Red "
            "fire trucks race past with flashing lights and wailing sirens. As the move continues, "
            "the image bends at its edges and the camera pulls back to reveal the whole scene was a "
            "reflection on the curved glass of a camera lens. End on an extreme close-up of the "
            f"powered-down gimbal camera of a {DRONE}, with the street still reflected in its lens. "
            f"{STYLE}"
        ),
    },
    "2": {
        "model": "bytedance/seedance-2.5/image-to-video",
        "duration": 5,
        "prompt": (
            "The camera drifts sideways off the lens. A green LED blinks on, the gimbal lifts and snaps "
            "level, and the rotors spin up. The camera rises to reveal a dark open asphalt apron with "
            "dozens of identical drones in rows, their LEDs lighting up in a wave. The whole swarm "
            "lifts off together and flies toward the orange glow on the horizon. Same drone design "
            f"and same night lighting throughout. {STYLE}"
        ),
    },
    "3": {
        "model": "bytedance/seedance-2.5/reference-to-video",
        "duration": 5,
        "prompt": (
            "Top-down view of a dark holographic 3D map of the Los Angeles coast and hills, with a thin "
            "glowing orange fire line. Dozens of cyan points form overlapping circles that shift and "
            "resize to cover the whole area. The map dissolves seamlessly into a real overhead night "
            f"view of the city, and the cyan points become real {DRONE}s with glowing LEDs, flying "
            f"apart in every direction. {STYLE}"
        ),
    },
    "3v2": {
        "model": "bytedance/seedance-2.5/reference-to-video",
        "duration": 5,
        "resolution": "1080p",
        "prompt": (
            "Night on a dark hilltop overlooking Los Angeles, matching the fire reference image: the "
            "downtown skyline on the right, a huge orange fire with rising smoke on the left, and city "
            "lights spread below.\n"
            "Camera: low to the ground at about 1 metre, wide lens, facing the fire and drifting slowly "
            "forward. One continuous shot with no cuts.\n"
            "Action: for the first second, only the city and fire are visible. Then three matte-black "
            "drones with green LEDs, matching the references, fly past the camera from behind, one "
            "after another and about a second apart. The first passes on the left, the second on the "
            "right, and the third just overhead. They form a loose line and fly toward the fire, "
            "getting smaller against the flames.\n"
            "Sound: steady buzzing motors, with one fast whoosh as each drone passes the camera.\n"
            "Exactly three drones, keeping their shape throughout, with smooth, weighty flight. "
            "Photoreal cinematic night footage. No on-screen text, logos or watermarks."
        ),
    },
    "4": {
        "model": "bytedance/seedance-2.5/reference-to-video",
        "duration": 5,
        "resolution": "1080p",
        "prompt": (
            "Stabilized aerial view from a drone's gimbal camera, with no drone body visible, at night "
            "over a wildfire in a Los Angeles neighbourhood. Camera: about 120 metres high, 35mm lens, "
            "tilted about 30 degrees down, with the horizon in the upper third. The camera drifts "
            "slightly left while pushing forward. Palm trees bend in violent wind, embers streak "
            "sideways past the lens, and thick orange smoke rolls through the frame, adding deep "
            "foreground parallax.\n"
            "0-2s: steady forward push toward the largest area of flame.\n"
            "2-4s: the camera stops and holds still, with the largest fire exactly centred.\n"
            "4-5s: four distant matte-black drones with green LEDs enter from the right edge and fly "
            "toward the fire.\n"
            "Keep the top-right corner and bottom edge visually simple. Match the reference image's "
            "colour, wind and ember density. No on-screen text, logos or watermarks."
        ),
    },
    "5": {
        "model": "bytedance/seedance-2.5/reference-to-video",
        "duration": 6,
        "prompt": (
            "Stabilized aerial view from a drone's gimbal camera, with no drone body visible, at night "
            "in the same wildfire as the reference image. Camera: hovering about 80 metres from a "
            "burning two-storey house, angled about 20 degrees down, with the upstairs balcony exactly "
            "centred throughout.\n"
            "0-2s: wide, steady view of the whole house, with flames on the far side of the roof and "
            "embers drifting past.\n"
            "2-4.5s: a smooth continuous zoom into the balcony.\n"
            "4.5-6s: the zoom stops. A mother and her teenage son are clearly visible and unhurt, "
            "standing together, looking up at the camera and waving a phone flashlight.\n"
            "Keep the flames behind them and away from them. Keep the top-right corner and bottom edge "
            "visually simple. Photoreal cinematic night footage. No on-screen text, logos or watermarks."
        ),
    },
    "6": {
        "model": "bytedance/seedance-2.5/reference-to-video",
        "duration": 6,
        "prompt": (
            "Morning on the same asphalt apron with the same warehouse behind it. Soft gold sunrise, "
            "clear pale sky and light haze, with no fire. Camera: low angle about 30cm above the ground, "
            "24mm lens, facing the sunrise, with long shadows stretching toward the camera. A slow "
            "forward dolly runs throughout.\n"
            "0-4s: identical matte-black drones with green LEDs, exactly matching the references, "
            "descend out of the sun in sequence and land one by one in neat rows, each rotor slowing to "
            "a stop as dust settles.\n"
            "4-5s: the last drone lands closest to the camera, filling the frame, with its landing legs "
            "touching down in sharp foreground detail.\n"
            "5-6s: the camera pushes into its gimbal lens, which reflects the sunrise, and holds still.\n"
            "Calm, quiet motion with warm lens flare. Keep the sky in the upper half clear. No on-screen "
            "text, logos or watermarks."
        ),
    },
    "3B": {
        "model": "bytedance/seedance-2.5/reference-to-video",
        "duration": 5,
        "prompt": (
            "Night, on the same dark asphalt apron beside the warehouse. Camera: extreme low-angle "
            "worm's-eye shot from ground level, 14mm ultra-wide lens, tilted steeply up at the sky. The "
            "warehouse roofline runs along the bottom edge of the frame, with an orange wildfire glow "
            "and drifting smoke low on the left. The camera pushes slowly upward and rolls about 20 "
            "degrees clockwise throughout, with no cuts.\n"
            "0-1.5s: 24 identical matte-black heavy-lift drones hover in one tight ring directly "
            "overhead, seen from underneath. Their landing legs, underslung gimbals, long carbon arms "
            "and blurred rotors are silhouetted against the deep blue-black sky, with green LEDs "
            "flaring softly in the lens. Rotor wash blows dust and embers across the foreground.\n"
            "1.5-3s: the rotors surge and the ring bursts outward from the centre like a flower "
            "opening. It splits into six clear groups of four. Each group tilts hard and accelerates "
            "in its own direction: top, top-right, bottom-right, bottom, bottom-left and top-left of "
            "the frame.\n"
            "3-5s: the groups streak toward the edges of the frame, leaving faint green light trails "
            "and shrinking rapidly. One drone passes low and very close over the lens, its dark "
            "underside sweeping through the foreground. The shot ends on open night sky with six "
            "distant clusters of green lights, embers drifting upward.\n"
            "Epic scale, strong parallax, fast and powerful motion, real depth between near and far "
            "drones. All drones match the references exactly. No drones hovering in a line. Photoreal "
            "cinematic film. No on-screen text, logos or watermarks."
        ),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clip", choices=CLIPS)
    parser.add_argument("--reference", type=Path, action="append", default=[])
    parser.add_argument("--start", type=Path, help="start frame for image-to-video clips")
    args = parser.parse_args()

    load_dotenv(".env.local")
    clip = CLIPS[args.clip]
    arguments = {
        "prompt": clip["prompt"],
        "duration": clip["duration"],
        "resolution": clip.get("resolution", "720p"),
        "output_format": "mp4",
        "generate_audio": True,
    }
    try:
        if clip["model"].endswith("image-to-video"):
            if not args.start:
                parser.error("this clip needs --start")
            arguments["image_url"] = higgsfield_client.upload_file(args.start)
        else:
            if not args.reference:
                parser.error("this clip needs --reference")
            arguments["image_urls"] = [higgsfield_client.upload_file(path) for path in args.reference]
            arguments["aspect_ratio"] = "16:9"
        result = higgsfield_client.subscribe(
            clip["model"],
            arguments=arguments,
            on_enqueue=lambda request_id: print(f"Queued request {request_id}", file=sys.stderr),
        )
    except higgsfield_client.CredentialsMissedError:
        print("HF_KEY is not set; add it to .env.local as key-id:key-secret.", file=sys.stderr)
        return 2
    except higgsfield_client.HiggsfieldClientError as error:
        print(f"Higgsfield rejected the request: {error}", file=sys.stderr)
        return 1

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"clip{args.clip}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    status = result.get("status")
    url = (result.get("video") or {}).get("url")
    if status != "completed" or not url:
        print(f"No video: status {status!r}, error {result.get('error')!r}.", file=sys.stderr)
        return 1

    video = OUTPUT / f"clip{args.clip}.mp4"
    with urlopen(url) as response:
        video.write_bytes(response.read())
    print(url)
    print(video)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
