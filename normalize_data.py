#!/usr/bin/env python3
"""
规范化原始定价数据，生成 dashboard 使用的 pricing.json。
为异构的模型类型（文本/图片/视频/音频）添加统一的展示字段。
"""
import json
import os
from datetime import datetime, timezone

SRC = os.path.join(os.path.dirname(__file__), "..", "llm_pricing_data.json")
DST = os.path.join(os.path.dirname(__file__), "..", "data", "pricing.json")


def normalize_model(m: dict) -> dict:
    """为每个模型添加规范化字段，供前端统一渲染。"""
    mtype = m.get("type", "text")
    normalized = {
        "model": m["model"],
        "vendor": m["vendor"],
        "type": mtype,
        "status": m.get("status", "current"),
        "is_open_source": m.get("is_open_source", False),
        "context_window": m.get("context_window"),
        "pricing_url": m.get("pricing_url", ""),
        "notes": m.get("notes", ""),
    }

    # 保留原始价格字段
    for k, v in m.items():
        if k not in normalized and k not in ("model", "vendor", "type"):
            if v is not None:
                normalized[k] = v

    # --- 根据类型生成统一的展示价格 ---
    if mtype in ("text", "multimodal"):
        inp = m.get("input_price_usd_per_mtok")
        out = m.get("output_price_usd_per_mtok")
        cache = m.get("input_price_cache_hit_usd_per_mtok")
        normalized["price_input"] = inp
        normalized["price_output"] = out
        normalized["price_cache_hit"] = cache
        normalized["price_unit"] = "$/Mtok"
        # 排序值：用输出价格（推理成本通常是瓶颈）
        normalized["price_sort_value"] = out if out is not None else (inp or 0)
        normalized["price_sort_label"] = f"${out}/Mtok out" if out else f"${inp}/Mtok in"

    elif mtype == "image":
        # 取标准画质价格作为主排序值
        primary = (
            m.get("price_standard_1024")
            or m.get("price_per_image_usd")
            or m.get("price_per_generation_usd")
            or m.get("price_per_image_usd_720p")
        )
        normalized["price_primary"] = primary
        normalized["price_unit"] = m.get("unit", "USD per image")
        normalized["price_sort_value"] = primary or 0
        normalized["price_sort_label"] = f"${primary}/image" if primary else "—"

    elif mtype == "video":
        primary = (
            m.get("price_per_second_usd")
            or m.get("price_per_second_usd_720p")
            or m.get("price_per_second_usd_720p_1080p")
            or m.get("price_per_second_usd_720p_1280p")
            or m.get("price_per_second_usd_1080p")
            or m.get("price_per_second_usd_4k")
        )
        normalized["price_primary"] = primary
        normalized["price_unit"] = m.get("unit", "USD per second")
        normalized["price_sort_value"] = primary or 0
        normalized["price_sort_label"] = f"${primary}/sec" if primary else "—"

    elif mtype == "audio":
        primary = m.get("price_per_1k_chars_usd") or m.get("price_per_minute_usd")
        normalized["price_primary"] = primary
        normalized["price_unit"] = m.get("unit", "USD per 1K characters")
        normalized["price_sort_value"] = primary or 0
        normalized["price_sort_label"] = (
            f"${primary}/1K chars" if primary and "char" in (m.get("unit") or "") else
            f"${primary}/min" if primary else "—"
        )

    else:
        normalized["price_sort_value"] = 0
        normalized["price_sort_label"] = "—"

    return normalized


def main():
    with open(SRC, encoding="utf-8") as f:
        raw = json.load(f)

    meta = raw.get("_meta", {})
    meta["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    meta["generator"] = "scripts/normalize_data.py"

    models = [normalize_model(m) for m in raw.get("models", [])]

    # 按厂商分组统计
    from collections import Counter
    vendor_counts = Counter(m["vendor"] for m in models)
    type_counts = Counter(m["type"] for m in models)
    meta["stats"] = {
        "total_models": len(models),
        "by_vendor": dict(vendor_counts.most_common()),
        "by_type": dict(type_counts.most_common()),
    }

    output = {"_meta": meta, "models": models}

    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✓ 规范化完成：{len(models)} 个模型 → {DST}")
    print(f"  厂商数：{len(vendor_counts)}，类型：{dict(type_counts)}")


if __name__ == "__main__":
    main()
