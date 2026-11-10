"""本机 Chrome + chrome_debug_profile（从日常配置复制）启动，CDP 接入。

用法::
    from openChrom import openChrom, closeChrom
    page = openChrom("https://example.com")
    closeChrom(page)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent
DEBUG_PROFILE = ROOT / "chrome_debug_profile"
CDP_PORT = 9222
_refs: dict[int, tuple] = {}  # page_id -> (playwright, browser, proc|None)

_SKIP = {
    "Cache", "Code Cache", "GPUCache", "ShaderCache", "GrShaderCache",
    "GraphiteDawnCache", "Service Worker", "Crashpad", "BrowserMetrics",
    "optimization_guide_model_store",
}


def _chrome_path() -> Path:
    candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google/Chrome/Application/chrome.exe",
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/google-chrome-stable"),
    ]
    for p in candidates:
        if p.is_file():
            return p
    raise FileNotFoundError("未找到 Google Chrome")


def _real_profile() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library/Application Support/Google/Chrome"
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "Google/Chrome/User Data"
    return home / ".config/google-chrome"


def _copy_profile(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    def ignore(dirpath: str, names: list[str]) -> set[str]:
        skip = set()
        for n in names:
            if n in _SKIP or n.startswith(("Singleton", "lockfile", "RunningChromeVersion")):
                skip.add(n)
        return skip

    # 逐文件复制，单个失败跳过（Chrome 开着时部分文件会锁）
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ignore(root, dirs)]
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for name in files:
            if name in ignore(root, [name]):
                continue
            try:
                s = Path(root) / name
                if s.exists() and not s.is_symlink():
                    shutil.copy2(s, dst / rel / name)
            except OSError:
                pass


def _ensure_profile() -> Path:
    if not (DEBUG_PROFILE / "Default").is_dir():
        src = _real_profile()
        if not src.is_dir():
            raise FileNotFoundError(f"未找到日常 Chrome 配置: {src}")
        print(f"首次复制 Chrome 配置到 {DEBUG_PROFILE} …")
        _copy_profile(src, DEBUG_PROFILE)
    return DEBUG_PROFILE


def _wait_cdp(port: int, timeout: float = 25) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.4)
            return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError(f"Chrome 调试端口 :{port} 未就绪")


def openChrom(url: str) -> Page:
    """启动本机 Chrome（调试配置）并打开 url。"""
    profile = _ensure_profile()
    pw = sync_playwright().start()
    proc = None
    try:
        # 已有调试实例则直接接入
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=0.3)
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
            proc = None
        except Exception:
            proc = subprocess.Popen(
                [
                    str(_chrome_path()),
                    f"--remote-debugging-port={CDP_PORT}",
                    f"--user-data-dir={profile}",
                    "--profile-directory=Default",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "about:blank",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _wait_cdp(CDP_PORT)
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")

        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, wait_until="domcontentloaded")
        _refs[id(page)] = (pw, browser, proc)
        return page
    except Exception:
        if proc and proc.poll() is None:
            proc.terminate()
        pw.stop()
        raise


def closeChrom(page: Page) -> None:
    """断开并关闭脚本拉起的 Chrome。"""
    ref = _refs.pop(id(page), None)
    if not ref:
        return
    pw, browser, proc = ref
    try:
        browser.close()
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        pw.stop()
