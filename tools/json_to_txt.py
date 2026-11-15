import os
import json

src_dir = os.environ.get("LABELME_DIR", ".")

for fname in sorted(os.listdir(src_dir)):
    if not fname.endswith(".json"):
        continue
    json_path = os.path.join(src_dir, fname)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    lines = []
    lines.append(f"path: {data.get('path')}")
    lines.append(f"labeled: {data.get('labeled')}")
    lines.append(f"time_labeled: {data.get('time_labeled')}")
    size = data.get("size", {})
    lines.append(
        f"size: width={size.get('width')}, height={size.get('height')}, depth={size.get('depth')}"
    )
    outputs = data.get("outputs", {})
    objects = outputs.get("object", [])
    lines.append(f"object_count: {len(objects)}")
    for i, obj in enumerate(objects, 1):
        name = obj.get("name", "")
        polygon = obj.get("polygon", {})
        points = " ".join(
            f"{k}={v}" for k, v in polygon.items()
        )
        lines.append(f"object_{i}: name={name}, polygon: {points}")

    txt_path = os.path.join(src_dir, fname.replace(".json", ".txt"))
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"converted: {fname} -> {os.path.basename(txt_path)}")