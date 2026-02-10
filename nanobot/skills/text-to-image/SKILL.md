---
name: text-to-image
description: Generate AI images from text descriptions. IMPORTANT — Use the built-in `generate_image` tool directly. Do NOT use exec or scripts. Call generate_image(prompt, n, ratio, model) to create and send images to chat automatically.
---

# Text-to-Image Generation

## ⚠️ IMPORTANT: Use the `generate_image` tool directly!

Do NOT run scripts via `exec`. Instead, call the `generate_image` tool:

```
generate_image(prompt="mô tả ảnh", n=1, ratio="landscape", model="IMAGEN_3_5")
```

The tool will:
1. Call the API automatically
2. Decode base64 images
3. Send photos directly to the chat
4. Return confirmation with seeds

## Parameters

| Param | Type | Default | Options |
|-------|------|---------|---------|
| `prompt` | string | (required) | Vietnamese or English |
| `n` | int | 1 | 1-4 |
| `ratio` | string | landscape | landscape, portrait, square |
| `model` | string | IMAGEN_3_5 | IMAGEN_3_5 (best), GEM_PIX (fast) |

## Tips
- Add style keywords: "digital art", "cinematic", "anime style", "oil painting"
- Vietnamese prompts work well
- Use IMAGEN_3_5 for best quality, GEM_PIX for speed
