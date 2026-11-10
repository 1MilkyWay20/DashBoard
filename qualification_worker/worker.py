#!/usr/bin/env python3
"""轮询看板 API，领取 pending 资质任务，调用本机 Playwright 脚本并回报结果。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api").rstrip("/")
WORKER_USERNAME = os.getenv("WORKER_USERNAME", "").strip()
WORKER_PASSWORD = os.getenv("WORKER_PASSWORD", "").strip()
# 运行中可刷新；启动时可用 .env 里的旧 token 作初始值
TOKEN = os.getenv("WORKER_TOKEN", "").strip()
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "5"))
SCRIPT = HERE / "run_qualification.py"
TMP = HERE / "tmp"  # 任务 JSON 临时文件
LICENSES = HERE / "licenses"  # 证件照片：下载与 Playwright 上传都用这里
TMP.mkdir(exist_ok=True)
LICENSES.mkdir(exist_ok=True)


def login() -> str:
    """用账号密码换 JWT。"""
    if not WORKER_USERNAME or not WORKER_PASSWORD:
        raise RuntimeError("未配置 WORKER_USERNAME / WORKER_PASSWORD，无法自动登录")
    r = requests.post(
        f"{API_BASE}/auth/login",
        json={"username": WORKER_USERNAME, "password": WORKER_PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    token = (r.json().get("token") or "").strip()
    if not token:
        raise RuntimeError("登录成功但未返回 token")
    return token


def ensure_token(*, force: bool = False) -> str:
    """保证内存里有可用 token；force=True 或当前为空时重新登录。"""
    global TOKEN
    if force or not TOKEN:
        if WORKER_USERNAME and WORKER_PASSWORD:
            TOKEN = login()
            print(f"[worker] 已{'刷新' if force else '登录'} token（用户 {WORKER_USERNAME}）")
        elif not TOKEN:
            raise SystemExit(
                "请在 .env 中配置 WORKER_USERNAME/WORKER_PASSWORD（推荐），"
                "或手动填写 WORKER_TOKEN"
            )
    return TOKEN


def headers() -> dict:
    return {"Authorization": f"Bearer {ensure_token()}"}


def api_request(method: str, url: str, **kwargs) -> requests.Response:
    """带一次 401 自动重登重试。"""
    kwargs.setdefault("timeout", 30)
    extra_headers = kwargs.pop("headers", None) or {}

    def _do() -> requests.Response:
        return requests.request(
            method, url, headers={**headers(), **extra_headers}, **kwargs
        )

    r = _do()
    if r.status_code == 401 and WORKER_USERNAME and WORKER_PASSWORD:
        print("[worker] token 失效，正在重新登录…")
        ensure_token(force=True)
        r = _do()
    return r


def list_pending() -> list[dict]:
    r = api_request(
        "GET",
        f"{API_BASE}/qualification/jobs",
        params={"status": "pending"},
    )
    r.raise_for_status()
    return r.json()


def claim(job_id: int) -> dict:
    r = api_request("POST", f"{API_BASE}/qualification/jobs/{job_id}/claim")
    if r.status_code == 409:
        return {}
    r.raise_for_status()
    return r.json()


def download_license(job_id: int, dest: Path) -> Path:
    r = api_request(
        "GET",
        f"{API_BASE}/qualification/jobs/{job_id}/license",
        timeout=120,
        stream=True,
    )
    r.raise_for_status()
    # 尽量保留扩展名
    ctype = (r.headers.get("content-type") or "").lower()
    ext = ".jpg"
    if "png" in ctype:
        ext = ".png"
    elif "webp" in ctype:
        ext = ".webp"
    elif "bmp" in ctype:
        ext = ".bmp"
    cd = r.headers.get("content-disposition") or ""
    if ".png" in cd.lower():
        ext = ".png"
    elif ".webp" in cd.lower():
        ext = ".webp"
    path = dest.with_suffix(ext)
    with path.open("wb") as f:
        for chunk in r.iter_content(64 * 1024):
            if chunk:
                f.write(chunk)
    return path


def patch_result(job_id: int, status: str, error_message: str = "") -> None:
    r = api_request(
        "PATCH",
        f"{API_BASE}/qualification/jobs/{job_id}",
        headers={"Content-Type": "application/json"},
        json={"status": status, "error_message": error_message[:2000]},
    )
    r.raise_for_status()


def _job_store_label(job: dict) -> str:
    """证件文件名用的门店标识：优先美团 → 饿了么 → 京东 → 团购。"""
    for key in ("mt_store_id", "elm_store_id", "jd_store_id", "tg_store_id"):
        v = str(job.get(key) or "").strip()
        if v:
            return v
    # 兼容旧任务
    return str(job.get("store_id") or "unknown").strip() or "unknown"


def run_script(job: dict, license_path: Path) -> None:
    job_file = TMP / f"job_{job['id']}.json"
    payload = {
        "id": job["id"],
        "brand": job.get("brand", "xj"),
        "mt_store_id": job.get("mt_store_id", ""),
        "elm_store_id": job.get("elm_store_id", ""),
        "jd_store_id": job.get("jd_store_id", ""),
        "tg_store_id": job.get("tg_store_id", ""),
        "operator_name": job["operator_name"],
        "credit_code": job["credit_code"],
        "legal_person": job["legal_person"],
        "address": job["address"],
        "main_business_type": job["main_business_type"],
        "business_scope": job["business_scope"],
        "valid_until": job["valid_until"],
        "license_no": job["license_no"],
        "approved_at": job["approved_at"],
    }
    job_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    env = os.environ.copy()
    # 把 USER_DATA_DIR 透传给脚本
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--job", str(job_file), "--license", str(license_path)],
        cwd=str(HERE),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        raise RuntimeError(msg or f"脚本退出码 {proc.returncode}")


def process_one(job_meta: dict) -> bool:
    job_id = job_meta["id"]
    print(f"[worker] claim #{job_id} stores={_job_store_label(job_meta)}")
    job = claim(job_id)
    if not job:
        print(f"[worker] #{job_id} 已被他人领取，跳过")
        return False

    store_id = _job_store_label(job)
    # 证件图落 licenses/，文件名带任务号和门店 ID，方便排查
    license_path = LICENSES / f"job{job_id}_{store_id}"
    try:
        license_path = download_license(job_id, license_path)
        print(f"[worker] 证件已保存: {license_path}")
        run_script(job, license_path)
        patch_result(job_id, "success")
        print(f"[worker] #{job_id} success")
    except Exception as e:
        print(f"[worker] #{job_id} failed: {e}", file=sys.stderr)
        try:
            patch_result(job_id, "failed", str(e))
        except Exception as pe:
            print(f"[worker] 回报失败: {pe}", file=sys.stderr)
    return True


def loop() -> None:
    ensure_token()
    print(f"[worker] API_BASE={API_BASE} poll={POLL_INTERVAL}s")
    if WORKER_USERNAME:
        print(f"[worker] 自动刷新已开启（用户 {WORKER_USERNAME}）")
    else:
        print("[worker] 仅使用 WORKER_TOKEN，过期需手动更新")
    print("[worker] 等待 pending 任务…（Ctrl+C 退出）")
    while True:
        try:
            pending = list_pending()
            if not pending:
                time.sleep(POLL_INTERVAL)
                continue
            # 先处理最老的
            pending.sort(key=lambda x: x["id"])
            process_one(pending[0])
        except requests.HTTPError as e:
            detail = ""
            try:
                detail = e.response.text[:300]
            except Exception:
                pass
            print(f"[worker] HTTP 错误: {e} {detail}", file=sys.stderr)
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("\n[worker] 已停止")
            break
        except Exception as e:
            print(f"[worker] 异常: {e}", file=sys.stderr)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    loop()
