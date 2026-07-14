#!/usr/bin/env python3
"""
LLM 定价自动更新脚本
====================
从各厂商官方定价页抓取最新价格，更新 data/pricing.json。

设计思路：
- 每个厂商一个独立的 fetch 函数，失败不影响其他厂商
- 优先抓取结构化数据（JSON API），退而求其次解析 HTML
- 保留手动维护的模型条目，仅更新可自动获取的字段
- 所有变更记录到 git commit message

使用方式：
    python3 scripts/update_pricing.py            # 抓取并更新
    python3 scripts/update_pricing.py --dry-run  # 仅显示变更，不写入
    python3 scripts/update_pricing.py --vendor openai  # 仅更新指定厂商

依赖：requests, beautifulsoup4（pip install requests beautifulsoup4）
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("缺少依赖，请运行: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "pricing.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LLMPricingBot/1.0; +https://github.com/llm-pricing-tracker)"
}
TIMEOUT = 30


def fetch_url(url: str) -> str:
    """获取网页内容"""
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


def fetch_json(url: str) -> dict:
    """获取 JSON API"""
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ==================== 各厂商抓取函数 ====================

def fetch_openai(models: list) -> list:
    """
    OpenAI 定价页：https://platform.openai.com/docs/pricing
    页面为 JS 渲染，尝试通过 API 或解析静态内容。
    """
    updates = []
    url = "https://platform.openai.com/docs/pricing"
    try:
        html = fetch_url(url)
        # OpenAI 页面包含 JSON-LD 或内联数据，尝试正则匹配价格
        # 匹配模式：模型名 + $X.XX per 1M tokens
        soup = BeautifulSoup(html, "html.parser")

        # 尝试从页面文本中提取已知模型的价格
        text = soup.get_text() if soup else html
        openai_models = [m for m in models if m["vendor"] == "OpenAI"]

        # 匹配 "$X.XX / 1M tokens" 或 "$X.XX per 1M" 格式
        price_pattern = r'\$(\d+\.?\d*)\s*/?\s*(?:per\s*)?1M\s*tokens?'

        for m in openai_models:
            if m["type"] not in ("text", "multimodal"):
                continue
            # 在模型名附近查找价格
            model_pattern = re.compile(
                rf'{re.escape(m["model"])}.{{0,500}}?(\$[\d.]+)\s*/?\s*(?:per\s*)?1M',
                re.IGNORECASE | re.DOTALL
            )
            match = model_pattern.search(text)
            if match:
                price = float(match.group(1).replace('$', ''))
                if "input" in text[max(0, match.start()-100):match.start()].lower() or \
                   "prompt" in text[max(0, match.start()-100):match.start()].lower():
                    if m.get("input_price_usd_per_mtok") != price:
                        updates.append({
                            "model": m["model"],
                            "field": "input_price_usd_per_mtok",
                            "old": m.get("input_price_usd_per_mtok"),
                            "new": price,
                        })
                        m["input_price_usd_per_mtok"] = price
                else:
                    if m.get("output_price_usd_per_mtok") != price:
                        updates.append({
                            "model": m["model"],
                            "field": "output_price_usd_per_mtok",
                            "old": m.get("output_price_usd_per_mtok"),
                            "new": price,
                        })
                        m["output_price_usd_per_mtok"] = price

    except Exception as e:
        print(f"  ⚠ OpenAI 抓取失败: {e}", file=sys.stderr)
    return updates


def fetch_anthropic(models: list) -> list:
    """Anthropic 定价页"""
    updates = []
    try:
        html = fetch_url("https://platform.claude.com/docs/en/about-claude/pricing")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()

        anthropic_models = [m for m in models if m["vendor"] == "Anthropic"
                           and m["type"] in ("text", "multimodal")]

        for m in anthropic_models:
            # 查找模型名附近的价格
            pattern = re.compile(
                rf'{re.escape(m["model"])}.*?\$(\d+\.?\d*).*?\$(\d+\.?\d*)',
                re.DOTALL
            )
            match = pattern.search(text)
            if match:
                inp, out = float(match.group(1)), float(match.group(2))
                if m.get("input_price_usd_per_mtok") != inp:
                    updates.append({"model": m["model"], "field": "input",
                                   "old": m.get("input_price_usd_per_mtok"), "new": inp})
                    m["input_price_usd_per_mtok"] = inp
                if m.get("output_price_usd_per_mtok") != out:
                    updates.append({"model": m["model"], "field": "output",
                                   "old": m.get("output_price_usd_per_mtok"), "new": out})
                    m["output_price_usd_per_mtok"] = out
    except Exception as e:
        print(f"  ⚠ Anthropic 抓取失败: {e}", file=sys.stderr)
    return updates


def fetch_deepseek(models: list) -> list:
    """DeepSeek 定价页（JSON API 或 HTML）"""
    updates = []
    try:
        html = fetch_url("https://api-docs.deepseek.com/quick_start/pricing-details-usd/")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()

        ds_models = [m for m in models if m["vendor"] == "DeepSeek"]
        for m in ds_models:
            # DeepSeek 页面通常有表格结构
            pattern = re.compile(
                rf'{re.escape(m["model"])}.*?\$(\d+\.?\d*).*?\$(\d+\.?\d*)',
                re.DOTALL
            )
            match = pattern.search(text)
            if match:
                inp, out = float(match.group(1)), float(match.group(2))
                if m.get("input_price_usd_per_mtok") != inp:
                    updates.append({"model": m["model"], "field": "input",
                                   "old": m.get("input_price_usd_per_mtok"), "new": inp})
                    m["input_price_usd_per_mtok"] = inp
                if m.get("output_price_usd_per_mtok") != out:
                    updates.append({"model": m["model"], "field": "output",
                                   "old": m.get("output_price_usd_per_mtok"), "new": out})
                    m["output_price_usd_per_mtok"] = out
    except Exception as e:
        print(f"  ⚠ DeepSeek 抓取失败: {e}", file=sys.stderr)
    return updates


def fetch_google(models: list) -> list:
    """Google Gemini 定价页"""
    updates = []
    try:
        html = fetch_url("https://ai.google.dev/gemini-api/docs/pricing")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()

        google_models = [m for m in models if m["vendor"] == "Google"
                        and m["type"] in ("text", "multimodal")]
        for m in google_models:
            pattern = re.compile(
                rf'{re.escape(m["model"])}.*?\$(\d+\.?\d*).*?\$(\d+\.?\d*)',
                re.DOTALL
            )
            match = pattern.search(text)
            if match:
                inp, out = float(match.group(1)), float(match.group(2))
                if m.get("input_price_usd_per_mtok") != inp:
                    updates.append({"model": m["model"], "field": "input",
                                   "old": m.get("input_price_usd_per_mtok"), "new": inp})
                    m["input_price_usd_per_mtok"] = inp
                if m.get("output_price_usd_per_mtok") != out:
                    updates.append({"model": m["model"], "field": "output",
                                   "old": m.get("output_price_usd_per_mtok"), "new": out})
                    m["output_price_usd_per_mtok"] = out
    except Exception as e:
        print(f"  ⚠ Google 抓取失败: {e}", file=sys.stderr)
    return updates


def fetch_mistral(models: list) -> list:
    """Mistral AI 定价页"""
    updates = []
    try:
        html = fetch_url("https://mistral.ai/pricing/")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()

        mistral_models = [m for m in models if m["vendor"] == "Mistral AI"]
        for m in mistral_models:
            pattern = re.compile(
                rf'{re.escape(m["model"])}.*?\$?(\d+\.?\d*).*?\$?(\d+\.?\d*)',
                re.DOTALL
            )
            match = pattern.search(text)
            if match:
                inp, out = float(match.group(1)), float(match.group(2))
                if inp > 0 and out > 0 and out > inp:  # 合理性校验
                    if m.get("input_price_usd_per_mtok") != inp:
                        updates.append({"model": m["model"], "field": "input",
                                       "old": m.get("input_price_usd_per_mtok"), "new": inp})
                        m["input_price_usd_per_mtok"] = inp
                    if m.get("output_price_usd_per_mtok") != out:
                        updates.append({"model": m["model"], "field": "output",
                                       "old": m.get("output_price_usd_per_mtok"), "new": out})
                        m["output_price_usd_per_mtok"] = out
    except Exception as e:
        print(f"  ⚠ Mistral 抓取失败: {e}", file=sys.stderr)
    return updates


def fetch_xai(models: list) -> list:
    """xAI Grok 定价"""
    updates = []
    try:
        html = fetch_url("https://lmmarketcap.com/xai-grok-pricing")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()

        xai_models = [m for m in models if m["vendor"] == "xAI"]
        for m in xai_models:
            pattern = re.compile(
                rf'{re.escape(m["model"])}.*?\$(\d+\.?\d*).*?\$(\d+\.?\d*)',
                re.DOTALL
            )
            match = pattern.search(text)
            if match:
                inp, out = float(match.group(1)), float(match.group(2))
                if m.get("input_price_usd_per_mtok") != inp:
                    updates.append({"model": m["model"], "field": "input",
                                   "old": m.get("input_price_usd_per_mtok"), "new": inp})
                    m["input_price_usd_per_mtok"] = inp
                if m.get("output_price_usd_per_mtok") != out:
                    updates.append({"model": m["model"], "field": "output",
                                   "old": m.get("output_price_usd_per_mtok"), "new": out})
                    m["output_price_usd_per_mtok"] = out
    except Exception as e:
        print(f"  ⚠ xAI 抓取失败: {e}", file=sys.stderr)
    return updates


# 厂商抓取函数注册表
FETCHERS = {
    "openai": ("OpenAI", fetch_openai),
    "anthropic": ("Anthropic", fetch_anthropic),
    "google": ("Google", fetch_google),
    "deepseek": ("DeepSeek", fetch_deepseek),
    "mistral": ("Mistral AI", fetch_mistral),
    "xai": ("xAI", fetch_xai),
}


def re_normalize(models: list) -> list:
    """更新后重新计算规范化字段"""
    for m in models:
        mtype = m.get("type", "text")
        if mtype in ("text", "multimodal"):
            out = m.get("output_price_usd_per_mtok")
            inp = m.get("input_price_usd_per_mtok")
            m["price_input"] = inp
            m["price_output"] = out
            m["price_sort_value"] = out if out is not None else (inp or 0)
            m["price_sort_label"] = f"${out}/Mtok out" if out else f"${inp}/Mtok in"
    return models


def main():
    parser = argparse.ArgumentParser(description="更新 LLM 定价数据")
    parser.add_argument("--dry-run", action="store_true", help="仅显示变更，不写入文件")
    parser.add_argument("--vendor", type=str, default=None, help="仅更新指定厂商（小写）")
    args = parser.parse_args()

    print(f"📋 加载数据: {DATA_FILE}")
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)

    models = data["models"]
    all_updates = []

    fetchers = FETCHERS
    if args.vendor:
        fetchers = {k: v for k, v in FETCHERS.items() if k == args.vendor.lower()}
        if not fetchers:
            print(f"❌ 未知厂商: {args.vendor}。可选: {', '.join(FETCHERS.keys())}")
            sys.exit(1)

    for key, (vendor_name, fetcher) in fetchers.items():
        print(f"\n🔍 抓取 {vendor_name}...")
        time.sleep(1)  # 礼貌延迟
        try:
            updates = fetcher(models)
            if updates:
                print(f"  ✓ 发现 {len(updates)} 处变更:")
                for u in updates:
                    print(f"    {u['model']}: {u['field']} {u['old']} → {u['new']}")
                all_updates.extend(updates)
            else:
                print(f"  ✓ 无变更")
        except Exception as e:
            print(f"  ❌ 抓取失败: {e}", file=sys.stderr)

    # 重新规范化
    models = re_normalize(models)

    # 更新 meta
    data["_meta"]["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 重新统计
    from collections import Counter
    vendor_counts = Counter(m["vendor"] for m in models)
    type_counts = Counter(m["type"] for m in models)
    data["_meta"]["stats"] = {
        "total_models": len(models),
        "by_vendor": dict(vendor_counts.most_common()),
        "by_type": dict(type_counts.most_common()),
    }

    # 写入或预览
    if args.dry_run:
        print(f"\n📝 [Dry Run] 共 {len(all_updates)} 处变更，未写入文件")
    else:
        if all_updates:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n✅ 已更新 {len(all_updates)} 处变更 → {DATA_FILE}")
            print(f"   更新日期: {data['_meta']['last_updated']}")
        else:
            print(f"\n✅ 无价格变更，仅更新日期 → {DATA_FILE}")
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    # 输出变更摘要供 GitHub Actions 使用
    if all_updates:
        summary = "\n".join(
            f"- {u['model']}: {u['field']} {u['old']} → {u['new']}"
            for u in all_updates
        )
        summary_file = PROJECT_ROOT / "data" / "update_summary.txt"
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(summary)
        print(f"\n📄 变更摘要 → {summary_file}")


if __name__ == "__main__":
    main()
