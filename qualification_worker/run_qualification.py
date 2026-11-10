#!/usr/bin/env python3
"""资质更换 Playwright 入口。

约定：
  python run_qualification.py --job job.json --license /path/to.jpg

job.json 字段与看板表单 / API 一致；平台脚本在 playwright/changeFileMt.py、changeFileElm.py。
各平台用各自门店 ID；未填则跳过该平台。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 保证能 import playwright/ 下的脚本
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "playwright"))

from changeFileElm import run as run_eleme  # noqa: E402
from changeFileJd import run as run_jd  # noqa: E402
from changeFileMt import run as run_meituan  # noqa: E402

# 公共证件字段（不含门店 ID）
REQUIRED_KEYS = (
    "operator_name",
    "credit_code",
    "legal_person",
    "address",
    "main_business_type",
    "business_scope",
    "valid_until",
    "license_no",
    "approved_at",
)

# (展示名, job 字段, runner) — 团购尚未对接；京东只换证图并提交，不填字段
PLATFORM_RUNNERS = (
    ("美团", "mt_store_id", run_meituan),
    ("饿了么", "elm_store_id", run_eleme),
    ("京东", "jd_store_id", run_jd),
)


def load_job(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_KEYS if not str(data.get(k, "")).strip()]
    if missing:
        raise SystemExit(f"job.json 缺少字段: {', '.join(missing)}")
    platform_ids = [str(data.get(k, "")).strip() for _, k, _ in PLATFORM_RUNNERS]
    # 也认 tg，便于以后扩展校验「至少有一个」
    extra_ids = [str(data.get("tg_store_id", "")).strip()]
    if not any(platform_ids + extra_ids):
        raise SystemExit("job.json 至少需要一个平台门店 ID")
    return data


def run_job(job: dict, license_path: Path) -> None:
    """按 job 依次跑各平台；无对应门店 ID 或未对接时跳过。"""
    print("[qualification] start")
    print(f"  mt_store_id={job.get('mt_store_id', '')}")
    print(f"  elm_store_id={job.get('elm_store_id', '')}")
    print(f"  jd_store_id={job.get('jd_store_id', '')}")
    print(f"  tg_store_id={job.get('tg_store_id', '')}")
    print(f"  operator_name={job['operator_name']}")
    print(f"  credit_code={job['credit_code']}")
    print(f"  legal_person={job['legal_person']}")
    print(f"  address={job['address']}")
    print(f"  main_business_type={job['main_business_type']}")
    print(f"  business_scope={job['business_scope']}")
    print(f"  valid_until={job['valid_until']}")
    print(f"  license_no={job['license_no']}")
    print(f"  approved_at={job['approved_at']}")
    print(f"  license={license_path}")

    errors: list[str] = []
    for name, id_key, fn in PLATFORM_RUNNERS:
        store_id = str(job.get(id_key, "")).strip()
        if not store_id:
            print(f"[qualification] {name} 跳过（未填 {id_key}）")
            continue
        try:
            print(f"[qualification] → {name} ({id_key}={store_id})")
            fn(job, license_path, hold=False)
            print(f"[qualification] {name} ok")
        except NotImplementedError as e:
            print(f"[qualification] {name} 跳过（未对接）: {e}")
        except Exception as e:
            # 某平台失败不挡其它已填平台
            print(f"[qualification] {name} failed: {e}", file=sys.stderr)
            errors.append(f"{name}: {e}")

    if str(job.get("tg_store_id", "")).strip():
        print("[qualification] 团购 跳过（未对接）")
    if errors:
        raise RuntimeError("；".join(errors))
    print("[qualification] done")


def main() -> int:
    parser = argparse.ArgumentParser(description="更换门店线上资质（Playwright）")
    parser.add_argument("--job", required=True, help="job.json 路径")
    parser.add_argument("--license", required=True, help="证件图片路径")
    args = parser.parse_args()

    job_path = Path(args.job)
    license_path = Path(args.license)
    if not job_path.is_file():
        print(f"找不到 job 文件: {job_path}", file=sys.stderr)
        return 2
    if not license_path.is_file():
        print(f"找不到证件图: {license_path}", file=sys.stderr)
        return 2

    job = load_job(job_path)
    try:
        run_job(job, license_path)
    except Exception as e:
        print(f"[qualification] failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
