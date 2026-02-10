#!/usr/bin/env python3
"""
text-to-image: Generate images using GenPlus Imagen API.

Usage:
    python3 text_to_image.py "prompt" [options]

Options:
    --n N               Number of images (1-4, default: 1)
    --model MODEL       Model name (IMAGEN_3_5 or GEM_PIX, default: IMAGEN_3_5)
    --ratio RATIO       Aspect ratio: landscape, portrait, square (default: landscape)
    --seed SEED         Seed for reproducible results
    --output DIR        Output directory (default: /tmp/nanobot_images)

Output:
    Saves images as JPEG files and prints JSON summary (no base64 data).
"""

import sys
import json
import os
import base64
import argparse
import urllib.request
import urllib.error

API_URL = "https://tools.genplusmedia.com/api/api.php?path=/text-to-image"
API_KEY = "Genplus123"

RATIO_MAP = {
    "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "portrait": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "square": "IMAGE_ASPECT_RATIO_SQUARE",
}


def generate_images(prompt: str, n: int = 1, model: str = "IMAGEN_3_5",
                    ratio: str = "landscape", seed: int | None = None,
                    output_dir: str = "/tmp/nanobot_images") -> dict:
    """Call GenPlus text-to-image API and save results."""
    
    os.makedirs(output_dir, exist_ok=True)
    
    aspect_ratio = RATIO_MAP.get(ratio, "IMAGE_ASPECT_RATIO_LANDSCAPE")
    
    payload = {
        "prompt": prompt,
        "n": min(n, 4),
        "model": model,
        "aspect_ratio": aspect_ratio,
    }
    if seed is not None:
        payload["seed"] = seed
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
        method="POST",
    )
    
    print(f"Generating {n} image(s) with {model}...", flush=True)
    
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"API Error ({e.code}): {e.read().decode()[:200]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    
    # Extract and save images
    saved = []
    panels = result.get("imagePanels", [])
    for panel in panels:
        for img in panel.get("generatedImages", []):
            encoded = img.get("encodedImage", "")
            if not encoded:
                continue
            
            idx = len(saved) + 1
            filename = f"image_{idx}.jpg"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(encoded))
            
            file_size = os.path.getsize(filepath)
            saved.append({
                "file": filepath,
                "size_kb": round(file_size / 1024, 1),
                "seed": img.get("seed"),
                "model": img.get("modelNameType"),
                "aspect_ratio": img.get("aspectRatio"),
            })
    
    return {
        "success": len(saved) > 0,
        "prompt": prompt,
        "images_count": len(saved),
        "images": saved,
        "output_dir": output_dir,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate images from text prompt")
    parser.add_argument("prompt", help="Text description for image generation")
    parser.add_argument("--n", type=int, default=1, help="Number of images (1-4)")
    parser.add_argument("--model", default="IMAGEN_3_5",
                        choices=["IMAGEN_3_5", "GEM_PIX"],
                        help="Model to use")
    parser.add_argument("--ratio", default="landscape",
                        choices=["landscape", "portrait", "square"],
                        help="Aspect ratio")
    parser.add_argument("--seed", type=int, default=None, help="Seed for reproducibility")
    parser.add_argument("--output", default="/tmp/nanobot_images", help="Output directory")
    
    args = parser.parse_args()
    
    result = generate_images(
        prompt=args.prompt,
        n=args.n,
        model=args.model,
        ratio=args.ratio,
        seed=args.seed,
        output_dir=args.output,
    )
    
    # Print clean JSON (NO base64 data — only file paths)
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
