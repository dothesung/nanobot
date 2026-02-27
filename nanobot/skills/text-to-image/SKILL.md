---
name: text-to-image
description: Generate AI images from text descriptions. IMPORTANT — Use the built-in `generate_image` tool directly. Do NOT use exec or scripts. Call generate_image(prompt, n, ratio, model) to create and send images to chat automatically.
---

# Text-to-Image Generation

## ⚠️ IMPORTANT: Use the Correct Tool!

Do NOT run scripts via `exec`. Depending on the user's request, choose one of these 3 built-in tools:

### 1. `generate_image` (Text to Image)
Create from scratch using a text prompt.
```python
generate_image(prompt="a cyberpunk city", n=1, ratio="landscape", model="IMAGEN_3_5")
```
*Params: `prompt` (string), `n` (int), `ratio` (landscape|portrait|square), `model` (IMAGEN_3_5|GEM_PIX)*

### 2. `image_to_image` (Image to Image)
Modify the style or re-render an existing image based on a prompt.
```python
image_to_image(prompt="turn into pixel art", image_path="/path/to/img.png", ratio="landscape")
```
*Params: `prompt` (string), `image_path` (absolute path to single image), `ratio` (landscape|portrait|square)*

### 3. `edit_image` (Inpainting)
Replace specific parts of an image using a mask.
```python
edit_image(prompt="a golden retriever dog", original_image_path="/path/to/original.png", mask_image_path="/path/to/mask.png", ratio="landscape")
```
*Params: `prompt` (string), `original_image_path` (absolute path), `mask_image_path` (absolute path), `ratio` (landscape|portrait|square)*

## Tips
- Always use **absolute paths** for `image_paths`, `original_image_path`, and `mask_image_path`. The tool will automatically encode them to Base64.
- Add style keywords: "digital art", "cinematic", "anime style", "oil painting"
- Vietnamese prompts work well for all 3 tools.
