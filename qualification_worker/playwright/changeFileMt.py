"""美团闪购：按前端表单入参上传许可证并填写字段。

用法（与 worker / run_qualification 一致）：
  python changeFileMt.py --job ../tmp/job_1.json --license ../licenses/job1_xxx.jpg
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from openChrom import openChrom, closeChrom

# 前端 job.json 字段 → 美团许可证表单项（「许可证件类型」保持页面默认，不改）
JOB_TO_FORM = {
    "operator_name": "经营者名称",
    "credit_code": "社会信用代码",
    "legal_person": "法定代表人/负责人",
    "address": "经营场所",
    "main_business_type": "主体业态",
    "business_scope": "经营项目/范围",
    "valid_until": "有效期至",
    "license_no": "许可证件编号",
    "approved_at": "核准日期",
}

FIELD_PLACEHOLDERS = {
    "经营者名称": "请输入经营者名称",
    "社会信用代码": "请输入社会信用代码",
    "法定代表人/负责人": "请输入法定代表人/负责人",
    "经营场所": "请输入经营场所",
    "主体业态": "请输入主体业态",
    "经营项目/范围": "请输入经营项目/范围",
    "有效期至": "请选择有效期截止时间",
    "许可证件编号": "请输入许可证编号",
    "核准日期": "选择日期",
}
DATE_FIELDS = {"有效期至", "核准日期"}
MONTH_CN = [
    "一月", "二月", "三月", "四月", "五月", "六月",
    "七月", "八月", "九月", "十月", "十一月", "十二月",
]


def license_form_from_job(job: dict) -> dict[str, str]:
    """把前端 / API 的 job 字段转成页面填写用的中文表单。"""
    form: dict[str, str] = {}
    missing: list[str] = []
    for key, label in JOB_TO_FORM.items():
        val = str(job.get(key, "")).strip()
        if not val:
            missing.append(key)
        else:
            form[label] = val
    if missing:
        raise ValueError(f"job 缺少字段: {', '.join(missing)}")
    return form


def fill_roo_input(panel, placeholder: str, value: str) -> None:
    """文本框：清空后填入。"""
    inp = panel.get_by_placeholder(placeholder)
    inp.wait_for(state="visible", timeout=10000)
    inp.click()
    inp.fill(value)


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip())


def _read_roo_input(panel, placeholder: str) -> str:
    inp = panel.get_by_placeholder(placeholder)
    if inp.count() == 0:
        return ""
    try:
        return (inp.first.input_value() or "").strip()
    except Exception:
        return ""


def read_license_form(panel) -> dict[str, str]:
    """读美团许可证面板当前值。"""
    out: dict[str, str] = {}
    for label, ph in FIELD_PLACEHOLDERS.items():
        out[label] = _read_roo_input(panel, ph)
    return out


def diff_license_form(actual: dict[str, str], expected: dict[str, str]) -> list[str]:
    bad: list[str] = []
    for label, exp in expected.items():
        if _norm_text(actual.get(label, "")) != _norm_text(exp):
            bad.append(label)
    return bad


def fill_license_fields(page, frame, panel, license_form: dict[str, str], *, only: set[str] | None = None) -> None:
    for field, value in license_form.items():
        if only is not None and field not in only:
            continue
        ph = FIELD_PLACEHOLDERS[field]
        if field in DATE_FIELDS:
            select_roo_date(page, frame, panel, ph, value)
        else:
            fill_roo_input(panel, ph, value)
        page.wait_for_timeout(200)


def verify_and_fix_license(page, frame, panel, license_form: dict[str, str], *, rounds: int = 2) -> None:
    """填完后对照前端期望值；不一致则改对应项，通过后再保存。"""
    for round_i in range(1, rounds + 1):
        page.wait_for_timeout(400)
        actual = read_license_form(panel)
        bad = diff_license_form(actual, license_form)
        if not bad:
            print(f"[changeFileMT] 校验通过（第 {round_i} 轮）")
            return
        print(f"[changeFileMT] 校验不一致（第 {round_i} 轮）: {bad}")
        for label in bad:
            print(f"  {label}: 页面={actual.get(label)!r} 期望={license_form.get(label)!r}")
        fill_license_fields(page, frame, panel, license_form, only=set(bad))

    actual = read_license_form(panel)
    bad = diff_license_form(actual, license_form)
    if bad:
        raise RuntimeError(f"校验仍不一致，放弃保存: {bad}")
    print("[changeFileMT] 修正后校验通过")


def select_roo_date(page, frame, panel, placeholder: str, ymd: str) -> None:
    """Roo 日期只能点选：打开面板 → 年 → 月 → 日。"""
    year_s, month_s, day_s = ymd.split("-")
    year_i, month_i, day_i = int(year_s), int(month_s), int(day_s)
    month_label = MONTH_CN[month_i - 1]

    # 关掉上一次残留的日期面板，避免挡住本次点击
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    # 许可证面板内 placeholder 唯一（核准日期的「选择日期」也只此一个）
    inp = panel.get_by_placeholder(placeholder)
    inp.wait_for(state="visible", timeout=10000)
    inp.scroll_into_view_if_needed()
    inp.click()
    page.wait_for_timeout(300)

    # 取真正有尺寸的面板（残留的 .roo-datepicker 可能 display:block 但宽高为 0）
    dp = frame.locator(".roo-datepicker").last
    dp.wait_for(state="visible", timeout=10000)

    # 点标题里的年份 → 年面板
    dp.locator(".roo-datepicker-days .action-select a").first.click()
    page.wait_for_timeout(200)
    years = dp.locator(".roo-datepicker-years")
    years.wait_for(state="visible", timeout=5000)

    # 当前十年段找不到目标年时，用左右翻页
    year_cell = years.locator("td.month a", has_text=re.compile(rf"^{year_i}$"))
    for _ in range(20):
        if year_cell.count() > 0 and year_cell.first.is_visible():
            break
        header = years.locator(".action-select a").inner_text()
        start = int(header.split("-")[0])
        if year_i < start:
            years.locator(".action-pre").click()
        else:
            years.locator(".action-next").click()
        page.wait_for_timeout(200)
    year_cell.first.click()
    page.wait_for_timeout(200)

    # 选年后面板会切到月；若没有则再点标题月份
    months = dp.locator(".roo-datepicker-months")
    if not months.is_visible():
        dp.locator(".roo-datepicker-days .action-select a").nth(1).click()
        page.wait_for_timeout(200)
    months.wait_for(state="visible", timeout=5000)
    # 必须精确匹配：has_text="二月" 会误伤「十二月」
    months.locator("td.month a", has_text=re.compile(rf"^{re.escape(month_label)}$")).click()
    page.wait_for_timeout(200)

    # 点当月日期。注意：今天之前的格子往往没有 .day class（class=""），
    # 仍可点选；不能只用 td.day，否则核准日期等会卡住。
    days = dp.locator(".roo-datepicker-days")
    days.wait_for(state="visible", timeout=5000)
    days.locator("td:not(.old):not(.new) a", has_text=re.compile(rf"^{day_i}$")).click()
    page.wait_for_timeout(300)


def run(job: dict, license_path: Path, *, hold: bool = False) -> None:
    """执行美团资质填写。job 为前端表单字段；license_path 为证件图。

    供 run_qualification / worker 直接调用；未填 mt_store_id 时静默跳过。
    """
    # 优先 mt_store_id；兼容旧 job 的 store_id
    store_id = str(job.get("mt_store_id") or job.get("store_id") or "").strip()
    if not store_id:
        print("[changeFileMT] 跳过：未填 mt_store_id")
        return
    if not license_path.is_file():
        raise FileNotFoundError(f"证件图不存在: {license_path}")

    license_form = license_form_from_job(job)

    page = openChrom("https://shangoue.meituan.com/")
    try:
        page.wait_for_timeout(2500)

        # 筛选门店（依赖浏览器已登录态）
        page.locator(".current-poi").hover()
        page.wait_for_timeout(500)
        page.locator(".poilist-dropmenu-container .content[title='全部门店']").click()
        page.wait_for_timeout(500)

        page.get_by_role("menuitem", name="门店信息").click()
        page.wait_for_timeout(1500)

        store = page.frame_locator("#hashframe").frame_locator('iframe[src*="store-manager"]')
        store.locator("#poiId").fill(store_id)
        page.wait_for_timeout(1000)
        store.locator("button.roo-btn-primary:not(.search-button)", has_text="查询").click()
        page.wait_for_timeout(1000)

        actions = store.locator(".store-list-table-actions")
        actions.locator(".action-btn", has_text="更多").click()
        page.wait_for_timeout(300)
        actions.locator(".action-btn", has_text="资质管理").click()
        page.wait_for_timeout(2500)

        for _ in range(15):
            close_btn = page.locator(".push-card__close").first
            if close_btn.count() == 0 or not close_btn.is_visible():
                break
            close_btn.click()
            page.wait_for_timeout(400)

        qual = page.frame_locator("#hashframe").frame_locator('iframe[src*="shangdan_qualification"]')

        edit_btn = qual.locator("button.roo-btn-primary", has_text="编辑")
        edit_btn.wait_for(state="visible", timeout=20000)
        edit_btn.click()
        page.wait_for_timeout(1000)

        # ---------- 第四步：填写信息 ----------
        qual.locator(".top-affix .tab-item", has_text="许可证").click()
        page.wait_for_timeout(800)

        license_panel = (
            qual.locator("#qualify-info-container > div")
            .filter(has=qual.locator("input[type='file']"))
            .filter(has_text=re.compile(r"^\s*许可证"))
        )
        license_panel.wait_for(state="visible", timeout=15000)
        license_panel.locator("input[type='file']").set_input_files(str(license_path))
        page.wait_for_timeout(2000)

        confirm_btn = qual.locator(".roo-modal-footer button.roo-btn-primary", has_text="确定")
        confirm_btn.wait_for(state="visible", timeout=20000)
        confirm_btn.click()
        page.wait_for_timeout(1500)

        fill_license_fields(page, qual, license_panel, license_form)
        page.wait_for_timeout(500)
        verify_and_fix_license(page, qual, license_panel, license_form)

        # 4.4 右上角「保存」
        save_btn = qual.locator("button.roo-btn-primary", has_text="保存")
        save_btn.wait_for(state="visible", timeout=10000)
        save_btn.click()
        page.wait_for_timeout(800)

        # 4.5 弹窗「是否保存？」→ 点「确认保存」
        confirm_save = qual.locator(
            ".roo-modal-footer button.roo-btn-primary", has_text="确认保存"
        )
        confirm_save.wait_for(state="visible", timeout=10000)
        confirm_save.click()
        page.wait_for_timeout(2000)

        if hold:
            input("浏览器已定格，按回车关闭...")
    finally:
        closeChrom(page)


def main() -> int:
    parser = argparse.ArgumentParser(description="美团闪购资质填写（前端表单入参）")
    parser.add_argument("--job", required=True, help="job.json 路径（前端/API 字段）")
    parser.add_argument("--license", required=True, help="证件图片路径")
    parser.add_argument(
        "--hold",
        action="store_true",
        help="填完后定格浏览器，按回车再关（本地调试用）",
    )
    args = parser.parse_args()

    job_path = Path(args.job)
    license_path = Path(args.license)
    if not job_path.is_file():
        print(f"找不到 job 文件: {job_path}", file=sys.stderr)
        return 2

    job = json.loads(job_path.read_text(encoding="utf-8"))
    try:
        run(job, license_path, hold=args.hold)
    except Exception as e:
        print(f"[changeFileMT] failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
