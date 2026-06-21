---
library_name: transformers
license: apache-2.0
license_link: https://huggingface.co/Qwen/Qwen3.5-2B/blob/main/LICENSE
pipeline_tag: image-text-to-text
base_model:
- Qwen/Qwen3.5-2B-Base
tags:
- mlx
---

# mlx-community/Qwen3.5-2B-4bit
This model was converted to MLX format from [`Qwen/Qwen3.5-2B`]() using mlx-vlm version **0.3.12**.
Refer to the [original model card](https://huggingface.co/Qwen/Qwen3.5-2B) for more details on the model.
## Use with mlx

```bash
pip install -U mlx-vlm
```

```bash
python -m mlx_vlm.generate --model mlx-community/Qwen3.5-2B-4bit --max-tokens 100 --temperature 0.0 --prompt "Describe this image." --image <path_to_image>
```
