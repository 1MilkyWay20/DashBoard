"""京东秒送：只换食品经营许可证照片并提交。

前端 job 只需 jd_store_id；证件图走 --license。不填表单字段。

用法：
  python changeFileJd.py --job ../tmp/job_1.json --license ../licenses/xxx.jpg --hold
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from openChrom import closeChrom, openChrom

JD_URL = "https://store.jddj.com/"


def _pause(page, ms: int = 300) -> None:
    page.wait_for_timeout(ms)


def _visible(loc) -> bool:
    try:
        return loc.count() > 0 and loc.first.is_visible()
    except Exception:
        return False


def _wait_visible_click(locator, *, timeout_ms: int, on_click_log: str) -> bool:
    """限时等待 locator 可见并点第一个；超时返回 False。"""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if _visible(locator):
            locator.first.click()
            print(on_click_log)
            return True
        locator.page.wait_for_timeout(250)
    return False


def dismiss_autoplay_dialog(page, *, timeout_ms: int = 10000) -> None:
    """登录/开新页后：若出现自动播放提示则点「取消」，否则继续。"""
    box = page.locator(".jd-message-box").filter(has_text="自动播放")
    btn = box.get_by_role("button", name="取消", exact=True)
    if _wait_visible_click(
        btn, timeout_ms=timeout_ms, on_click_log="[changeFileJD] 已关闭自动播放提示（取消）"
    ):
        _pause(page, 300)
        return
    print(f"[changeFileJD] {timeout_ms // 1000}s 内无自动播放弹窗，继续")


def open_store_qualification(page, store_id: str):
    """首页 → 门店列表 → 按门店编号查询 → 操作栏「修改」（新标签编辑页）。"""
    # 1) 营业门店
    item = page.locator(".bsi-item").filter(has_text="营业门店")
    item.first.wait_for(state="visible", timeout=15000)
    item.first.click()
    page.get_by_role("button", name="查询").first.wait_for(state="visible", timeout=15000)
    _pause(page, 500)
    print(f"[changeFileJD] 已进入门店列表: {page.url}")
    dismiss_autoplay_dialog(page)

    # 2) 门店编号查询
    inp = page.get_by_placeholder("支持输入多个门店编号，用英文逗号隔开")
    inp.wait_for(state="visible", timeout=10000)
    inp.click()
    inp.fill(store_id)
    page.get_by_role("button", name="查询").first.click()
    _pause(page, 800)
    print(f"[changeFileJD] 已按门店编号查询: {store_id}")

    # 3) 结果必须唯一，只点操作栏「修改」（绝不点删除）
    page.get_by_text(re.compile(r"共\s*1\s*条")).wait_for(state="visible", timeout=15000)
    row = page.locator("tbody tr").filter(has_text=store_id).filter(
        has=page.locator("td.fixed-right.last")
    )
    if row.count() != 1:
        raise RuntimeError(
            f"[changeFileJD] 期望查询结果仅 1 条，实际 {row.count()} 条 (jd_store_id={store_id})"
        )
    ops = row.first.locator("td.fixed-right.last")
    if ops.get_by_role("button", name="删除", exact=True).count() == 0:
        raise RuntimeError("[changeFileJD] 操作栏未找到「删除」，选择器可能错位，中止")
    edit_btn = ops.get_by_role("button", name="修改", exact=True)
    if edit_btn.count() != 1:
        raise RuntimeError(f"[changeFileJD] 操作栏「修改」数量异常: {edit_btn.count()}")

    with page.expect_popup(timeout=15000) as popup_info:
        edit_btn.click()
    edit_page = popup_info.value
    edit_page.wait_for_load_state("domcontentloaded")
    dismiss_autoplay_dialog(edit_page)
    edit_page.get_by_text("编辑门店信息").first.wait_for(state="visible", timeout=15000)
    _pause(edit_page, 500)
    print(f"[changeFileJD] 已进入门店编辑: {edit_page.url}")
    return edit_page


def upload_license(ctx, page, license_path: Path) -> None:
    """食品资质 → 删旧图 → 上传新图 → 等「上传图片成功」。"""
    edit = ctx
    section = edit.locator(".aptitude").filter(
        has=edit.locator("h2", has_text=re.compile(r"食品资质"))
    )
    section.first.wait_for(state="visible", timeout=15000)
    section.first.scroll_into_view_if_needed()
    item = section.locator(".dj-form-item").filter(
        has=edit.locator(".dj-form-item_label", has_text=re.compile(r"^食品经营许可证"))
    )
    item = item.first
    item.wait_for(state="visible", timeout=10000)
    item.scroll_into_view_if_needed()
    _pause(edit, 300)

    thumbs = item.locator("li.dj-upload-imgs")
    for _ in range(5):
        if thumbs.count() == 0:
            break
        thumb = thumbs.first
        thumb.hover()
        _pause(edit, 400)
        trash = thumb.locator("i.iconfont.garbage")
        if trash.count() == 0:
            print("[changeFileJD] 未找到垃圾桶，尝试直接上传")
            break
        trash.first.click(force=True)
        _pause(edit, 600)
        print("[changeFileJD] 已删除原食品经营许可证照片")

    file_input = item.locator(".dj-upload input[type='file']")
    if file_input.count() == 0:
        raise RuntimeError("[changeFileJD] 未找到食品经营许可证 file input")
    file_input.first.set_input_files(str(license_path))
    print(f"[changeFileJD] 已选择上传: {license_path.name}")

    toast = edit.get_by_text("上传图片成功")
    toast.first.wait_for(state="visible", timeout=30000)
    _pause(edit, 400)
    print("[changeFileJD] 已出现「上传图片成功」")


def _confirm_continue_submit(edit_page, *, timeout_ms: int = 15000) -> None:
    """住所不一致提示（.dj-modal-background.dj-message-box）：有则点「继续提交」。"""
    box = edit_page.locator(
        ".dj-modal-background.dj-message-box, .dj-modal-background.subConfirm"
    ).filter(has_text=re.compile(r"继续提交|住所和营业执照"))
    btn = box.locator("button").filter(has_text=re.compile(r"^\s*继续提交\s*$"))
    if _wait_visible_click(
        btn, timeout_ms=timeout_ms, on_click_log="[changeFileJD] 已点提示框「继续提交」"
    ):
        _pause(edit_page, 800)
        return
    print("[changeFileJD] 未出现继续提交提示，继续")


def _assert_submit_success(edit_page, *, timeout_ms: int = 20000) -> None:
    """成功标志：.ui.modal「已提交审核」→ 点「确定」；超时则失败。"""
    modal = edit_page.locator(".ui.modal.mini.alert, .ui.modal.alert, .ui.modal").filter(
        has_text="已提交审核"
    )
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if _visible(modal):
            ok = modal.locator(".ui.ok.blue.button, .ok.button").filter(
                has_text=re.compile(r"^\s*确定\s*$")
            )
            if ok.count() == 0:
                ok = modal.get_by_text("确定", exact=True)
            if ok.count() == 0:
                raise RuntimeError("[changeFileJD] 找到成功弹窗但没有「确定」")
            ok.first.click()
            print("[changeFileJD] 提交成功：已点「确定」")
            _pause(edit_page, 500)
            return
        edit_page.wait_for_timeout(250)
    raise RuntimeError(
        f"[changeFileJD] {timeout_ms // 1000}s 内未出现「已提交审核」弹窗，判定失败"
    )


def submit_qualification(ctx, page) -> None:
    """点「提交」→ 可选「继续提交」→ 必须出现成功弹窗。"""
    edit = ctx
    wrap = edit.locator(".button-wrap").filter(
        has=edit.get_by_role("button", name="提交", exact=True)
    )
    btn = wrap.last.get_by_role("button", name="提交", exact=True)
    btn.wait_for(state="visible", timeout=15000)
    btn.click()
    print("[changeFileJD] 已点「提交」")
    _pause(edit, 400)
    _confirm_continue_submit(edit)
    _assert_submit_success(edit)


def run(
    job: dict,
    license_path: Path,
    *,
    hold: bool = False,
    skip_photo: bool = False,
    skip_submit: bool = False,
) -> None:
    """供 run_qualification / worker 调用；未填 jd_store_id 时跳过。"""
    store_id = str(job.get("jd_store_id") or "").strip()
    if not store_id:
        print("[changeFileJD] 跳过：未填 jd_store_id")
        return
    if not skip_photo and not license_path.is_file():
        raise FileNotFoundError(f"证件图不存在: {license_path}")

    print(
        f"[changeFileJD] jd_store_id={store_id} "
        f"skip_photo={skip_photo} skip_submit={skip_submit}"
    )

    page = openChrom(JD_URL)
    try:
        _pause(page, 2500)
        print(f"[changeFileJD] 已打开 {JD_URL}")
        dismiss_autoplay_dialog(page)

        edit = open_store_qualification(page, store_id)
        if skip_photo:
            print("[changeFileJD] 跳过资质照片更换")
        else:
            upload_license(edit, page, license_path)

        if skip_submit:
            print("[changeFileJD] 跳过提交")
        else:
            submit_qualification(edit, page)
            print("[changeFileJD] 流程成功")

        if hold:
            input("京东页面已停住（可核对），按回车关闭...")
    finally:
        closeChrom(page)


def main() -> int:
    parser = argparse.ArgumentParser(description="京东资质换图提交（门店ID + 证件图）")
    parser.add_argument("--job", required=True, help="job.json（需含 jd_store_id）")
    parser.add_argument("--license", required=True, help="证件图片路径")
    parser.add_argument("--hold", action="store_true", help="结束后定格浏览器")
    parser.add_argument("--skip-photo", action="store_true")
    parser.add_argument("--skip-submit", action="store_true")
    args = parser.parse_args()

    job_path, license_path = Path(args.job), Path(args.license)
    if not job_path.is_file():
        print(f"找不到 job 文件: {job_path}", file=sys.stderr)
        return 2
    if not args.skip_photo and not license_path.is_file():
        print(f"找不到证件图: {license_path}", file=sys.stderr)
        return 2

    try:
        run(
            json.loads(job_path.read_text(encoding="utf-8")),
            license_path,
            hold=args.hold,
            skip_photo=args.skip_photo,
            skip_submit=args.skip_submit,
        )
    except Exception as e:
        print(f"[changeFileJD] failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
