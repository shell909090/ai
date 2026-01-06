# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a ComfyUI-based wallpaper generation toolkit that uses AI image generation workflows to create wallpapers for multiple device resolutions. The project uses a modular architecture where each ComfyUI workflow is embedded as a string in its own Python module.

## Architecture

### Code Standards

1. Use `logging` module for all output
2. Each workflow is a separate Python file with embedded JSON workflow string
3. Each workflow module provides function(s) for external calls
4. All shared logic goes in `libs.py`
5. All functions must have complete type annotations
6. All public functions must have detailed docstrings (Args, Returns, Raises)

### Script Organization

The codebase follows a **modular workflow architecture**:

1. **libs.py**: Shared library containing all reusable functions
   - Image I/O: `save_image()`, `read_img_from_byte()`, `resize_image()`, `convert_to_jpg()`
   - Device resolution utilities: `get_device_resolution()`, `calculate_generation_size()`, `get_all_devices()`, `filter_devices_by_ratio()`
   - ComfyUI wrapper: `ComfyWorkflow` class

2. **Workflow modules** (each contains embedded JSON workflow as string):
   - **zit.py**: z-image-turbo image generation - `zit(api, prompt, seed, width, height) -> bytes`
   - **usdu.py**: Ultimate SD Upscale - `usdu(api, input_file, upscale_by) -> bytes`
   - **upscale.py**: 4x model upscale - `upscale(api, input_file) -> bytes`
   - **outpaint.py**: Image extension - `outpaint(api, input_file, left, top, right, bottom) -> bytes`

3. **Entry point scripts**:
   - **wf.py**: CLI entry point - calls workflow modules based on `--workflow` parameter
   - **gen-images.py**: Batch generation - generates wallpapers for all devices using `zit.py`
   - **resize.py**: Batch resize - adjusts existing images to all device resolutions

### Key Design Patterns

**Device Resolution Calculation**: The `calculate_generation_size()` function in libs.py ensures generated images maintain device aspect ratios while keeping total pixels ≈ 1024×1024 (SDXL training size):
```python
gen_width = int(math.sqrt(1048576 * aspect_ratio))
gen_height = int(math.sqrt(1048576 / aspect_ratio))
```

**File Naming Convention**:
- Generated images with devices: `{counter:03d}_{batch:02d}_{device_id}.png` (gen-images.py)
- Generated images without devices: `{counter:03d}_{batch:02d}.png` (gen-images.py)
- Device-specific resized: `{counter:03d}_{device_id}.png` (resize.py)

**ComfyUI Integration**:
- Uses `comfy-api-simplified` library
- `ComfyApiWrapper(url)`: API client for queuing and retrieving results
- `ComfyWorkflow`: Custom wrapper class in libs.py extending `ComfyWorkflowWrapper`
- Workflows are embedded as JSON strings in Python files, loaded via `json.loads()`

### Workflow Modules Implementation Pattern

Each workflow module follows this pattern:

```python
import json
from libs import ComfyApiWrapper, ComfyWorkflow

WORKFLOW_STR = '''
{
  "node_id": {
    "inputs": {...},
    "class_type": "NodeType",
    "_meta": {"title": "节点名称"}
  }
}
'''

def workflow_function(api: ComfyApiWrapper, ...) -> bytes:
    wf = ComfyWorkflow(json.loads(WORKFLOW_STR))
    wf.set_node_param("节点名称", "param_name", value)
    results = api.queue_and_wait_images(wf, "预览图像")
    return next(iter(results.values()))
```

Node names in workflows are in Chinese (e.g., "CLIP文本编码", "K采样器", "空Latent图像（SD3）", "预览图像")

## Development Commands

### Setup
```bash
# Install dependencies (using uv)
uv sync

# Or using pip
pip install comfy-api-simplified pillow websockets
```

### Running Scripts

**Set ComfyUI API URL** (to avoid repeating --url):
```bash
export COMFYUI_API_URL=http://192.168.33.4:8188/
```

**Generate wallpapers**:
```bash
# Generate for all devices
./gen-images.py -t theme.txt -v variations.txt -o output/ --pixels-csv pixels.csv

# Generate without device specification (default 1024x1024)
./gen-images.py -t theme.txt -v variations.txt -o output/

# Generate multiple batches per variation
./gen-images.py -t theme.txt -v variations.txt -o output/ --pixels-csv pixels.csv --batches 5

# Batch resize existing images to all devices
./resize.py --input-dir output/ --pixels-csv pixels.csv --jpg

# Use individual workflows
./wf.py --workflow zit --prompt "prompt text" --output output.png
./wf.py --workflow usdu --input input.png --output output.png --upscale-by 2.0
```

### Device Resolution Table Format

The `pixels.csv` file defines target devices:
```csv
device_id,width,height
iphone_15_16,1179,2556
win_hd_monitor,1920,1080
```

## Important Implementation Details

### gen-images.py Core Logic

The script implements this workflow:
1. Read theme from `--theme` file
2. Read variations from `--variations` file (one per line)
3. Combine theme + variation to create final prompt
4. Assign sequential counter ID to each variation
5. For each variation, generate multiple batches (specified by `--batches`, default 1)
6. For each counter+batch combination, generate a random seed
7. If `--pixels-csv` specified, generate images for all device resolutions; otherwise generate default 1024x1024
8. Output filename: `{counter:03d}_{batch:02d}_{device_id}.png` (with devices) or `{counter:03d}_{batch:02d}.png` (without devices)

**Device Filtering**:
- When `--pixels-csv` is provided, the script filters devices by aspect ratio via `filter_devices_by_ratio()` to avoid generating duplicate aspect ratios
- Only the highest resolution device for each unique aspect ratio is kept

**Key behavior**: Same counter+batch uses identical seed across all devices to ensure visual consistency, but different batches have different seeds to provide variety

### Resize Strategy (resize.py)

The script intelligently chooses between AI upscaling and PIL downscaling:
```python
if device_pixels > gen_pixels:
    # AI upscale via ComfyUI
    upscale_by = math.sqrt(device_pixels / gen_pixels)
    image_data = upscale(api, wf, input_file, upscale_by)
else:
    # PIL downscale
    resize_image(input_file, output_file, device_width, device_height)
```

### Seed Handling

- **gen-images.py**: Same counter+batch combination uses identical seed across all devices to ensure visual consistency
- Different batches of the same variation get different seeds to provide variety
- Seeds are generated using `random.randint(2**20, 2**64)`

### Batch Generation

The `--batches` parameter allows generating multiple variations of each prompt:
- counter: Sequence ID for each variation (0, 1, 2, ...)
- batch: Batch ID for each generation of a variation (0, 1, 2, ..., batches-1)
- Each counter+batch pair gets a unique random seed
- All devices for the same counter+batch use the same seed

## Code Modification Guidelines

When adding new scripts or modifying existing ones:

1. **Put shared logic in libs.py** - All reusable functions belong in libs.py, not individual scripts
2. **Embed workflows as strings** - Workflow JSON should be embedded as `WORKFLOW_STR` in Python files, not separate JSON files
3. **Follow the import pattern**: `from libs import function1, function2, ...`
4. **Use consistent arg parsing**: Entry point scripts follow the same pattern with `--url/-u`, `--output/-o`, etc.
5. **Maintain file naming conventions**:
   - gen-images.py uses `{counter:03d}_{batch:02d}_{device_id}.png` or `{counter:03d}_{batch:02d}.png`
   - counter = variation sequence ID, batch = batch number within that variation
6. **ComfyUI node names are Chinese**: The workflow JSON files use Chinese node names - preserve these when modifying workflows
7. **Use logging module**: Always use `logging.info()`, `logging.error()`, etc. instead of `print()`
8. **Type annotations**: All function parameters and return types must have type hints
9. **Documentation**: All public functions must have docstrings with Args, Returns, and Raises sections

## File Organization

- **Input files**: `theme.txt` (main prompt), `variations.txt` (per-image variations), `pixels.csv` (device table)
- **Output files**: Generated in user-specified directories with automatic naming
- **Workflow definitions**: Embedded as strings in workflow Python modules (zit.py, usdu.py, upscale.py, outpaint.py)
