"""饿了么（淘宝闪购零售商家版）：按前端表单入参上传许可证并填写字段。

用法：
  python changeFileElm.py --job ../tmp/job_1.json --license ../licenses/job1_xxx.jpg --hold
  python changeFileElm.py --job ... --license ... --skip-photo --skip-submit --hold
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from openChrom import closeChrom, openChrom

ELM_URL = (
    "https://nr.ele.me/app/eleme-nr-bfe-newretail/common-next#/pc/homePagePc/"
)
STORE_LIST_URL = (
    "https://nr.ele.me/app/eleme-nr-bfe-newretail/common-next"
    "#/pc/storeManagementPc/shopList/overview"
)
CHAIN_ACCOUNT_NEEDLE = "新鲁东"

ELM_REQUIRED_KEYS = (
    "operator_name",
    "credit_code",
    "legal_person",
    "address",
    "business_scope",
    "valid_until",
    "license_no",
)

# 前端「散装+预包装」→ 优先两条「含冷藏冷冻」，都没有再勾合并项
SCOPE_BUNDLE_NEEDLE = "散装食品和预包装食品销售"
SCOPE_BUNDLE_DETAILED = (
    "预包装食品销售（含冷藏冷冻食品）",
    "散装食品销售（含冷藏冷冻食品）",
)
SCOPE_BUNDLE_COMBINED = "预包装及散装食品"


def _pause(page, ms: int = 300) -> None:
    page.wait_for_timeout(ms)


def require_job_fields(job: dict) -> None:
    missing = [k for k in ELM_REQUIRED_KEYS if not str(job.get(k, "")).strip()]
    if missing:
        raise ValueError(f"job 缺少字段: {', '.join(missing)}")


def resolve_scope_options(raw: str) -> list[str]:
    wanted: list[str] = []
    for part in (p.strip() for p in re.split(r"[，,、；;]+", raw) if p.strip()):
        if SCOPE_BUNDLE_NEEDLE in part:
            for opt in (*SCOPE_BUNDLE_DETAILED, SCOPE_BUNDLE_COMBINED):
                if opt not in wanted:
                    wanted.append(opt)
            continue
        core = re.sub(r"[（(][^）)]*[）)]", "", part).strip()
        if core and core not in wanted:
            wanted.append(core)
    return wanted


def form_item(panel, label: str):
    item = panel.locator(".ant-form-item").filter(
        has=panel.locator(".ant-form-item-label", has_text=label)
    )
    return item if item.count() else panel.locator(".ant-form-item").filter(has_text=label)


def fill_by_placeholder(panel, placeholder: str, value: str) -> None:
    inp = panel.get_by_placeholder(placeholder)
    inp.wait_for(state="visible", timeout=10000)
    inp.click()
    inp.fill(value)


def _visible(loc) -> bool:
    try:
        return loc.count() > 0 and loc.first.is_visible()
    except Exception:
        return False


def _click_if_visible(loc) -> bool:
    if not _visible(loc):
        return False
    loc.first.click()
    return True


def dismiss_blocking_modals(setup, page) -> None:
    """关掉挡路弹窗；只点「暂不修改 / 我知道了」，避免点「取消」退出编辑态。"""
    for name in (r"暂不修改", r"我知道了"):
        if _click_if_visible(setup.get_by_role("button", name=re.compile(name))):
            print(f"[changeFileELM] 关闭弹窗: {name}")
            _pause(page, 500)


def dismiss_license_already_used(setup, page, *, wait_ms: int = 400) -> None:
    _pause(page, wait_ms)
    modal = setup.locator(".ant-modal").filter(has_text="食品经营许可证已被使用")
    btn = setup.get_by_role("button", name=re.compile(r"暂不修改"))
    if btn.count() == 0:
        btn = page.get_by_role("button", name=re.compile(r"暂不修改"))
    if not (_visible(modal) or _visible(btn)):
        return
    btn.first.click()
    print("[changeFileELM] 已点「暂不修改」（许可证已被使用）")
    _pause(page, 400)


def confirm_ocr_overwrite(setup, page, *, timeout_ms: int = 10000) -> None:
    """上传后最多等 timeout_ms：出现「覆盖」则点；超时再填表（弹窗早到会立刻点完返回）。"""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        overwrite = setup.get_by_role("button", name=re.compile(r"^覆\s*盖$"))
        if overwrite.count() == 0:
            overwrite = page.get_by_role("button", name=re.compile(r"^覆\s*盖$"))
        modal = setup.locator(".ant-modal").filter(has_text="证件编号信息提示")
        if (_visible(modal) or _visible(overwrite)) and _click_if_visible(overwrite):
            print("[changeFileELM] 已点 OCR「覆盖」")
            _pause(page, 1000)
            return
        _pause(page, 200)
    print(f"[changeFileELM] {timeout_ms}ms 内无 OCR 覆盖弹窗，继续填表")


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip())


def _read_placeholder(panel, placeholder: str) -> str:
    inp = panel.get_by_placeholder(placeholder)
    if inp.count() == 0:
        return ""
    try:
        return (inp.first.input_value() or "").strip()
    except Exception:
        return ""


def _expected_scope_tags(raw_scope: str) -> list[str]:
    """校验用：有明细两条则不要求合并项；其余项按映射结果。"""
    wanted = resolve_scope_options(raw_scope)
    has_detailed = all(t in wanted for t in SCOPE_BUNDLE_DETAILED)
    out: list[str] = []
    for t in wanted:
        if t == SCOPE_BUNDLE_COMBINED and has_detailed:
            continue
        out.append(t)
    return out


def _read_scope_tags(panel) -> list[str]:
    item = form_item(panel, "经营范围")
    tags = item.locator(".ant-select-selection-item")
    texts: list[str] = []
    for i in range(tags.count()):
        t = (tags.nth(i).inner_text() or "").replace("\n", " ").strip()
        # 去掉关闭图标旁的多余空白
        t = re.sub(r"\s+", "", t)
        if t and t not in texts:
            texts.append(t)
    return texts


def _read_valid_until(panel) -> str:
    item = form_item(panel, "有效日期")
    inp = item.locator(".ant-picker-input input")
    if inp.count() == 0:
        return ""
    try:
        return (inp.first.input_value() or "").strip()
    except Exception:
        return ""


def read_license_fields(panel) -> dict[str, str]:
    """读行业资质面板当前值（文本 / 日期 / 经营范围标签）。"""
    return {
        "license_no": _read_placeholder(panel, "请输入许可证编号"),
        "operator_name": _read_placeholder(panel, "请输入单位名称"),
        "credit_code": _read_placeholder(panel, "请输入社会信用代码"),
        "legal_person": _read_placeholder(panel, "请输入法人代表"),
        "reg_address": _read_placeholder(panel, "请输入注册地址"),
        "biz_address": _read_placeholder(panel, "请输入经营场所"),
        "valid_until": _read_valid_until(panel),
        "business_scope": ",".join(_read_scope_tags(panel)),
    }


def expected_license_fields(job: dict) -> dict[str, str]:
    address = str(job["address"]).strip()
    return {
        "license_no": str(job["license_no"]).strip(),
        "operator_name": str(job["operator_name"]).strip(),
        "credit_code": str(job["credit_code"]).strip(),
        "legal_person": str(job["legal_person"]).strip(),
        "reg_address": address,
        "biz_address": address,
        "valid_until": str(job["valid_until"]).strip(),
        "business_scope": ",".join(_expected_scope_tags(str(job["business_scope"]))),
    }


def diff_license_fields(actual: dict[str, str], expected: dict[str, str]) -> list[str]:
    """返回不一致的字段名。经营范围：期望标签须都出现在实际已选项中。"""
    bad: list[str] = []
    for key, exp in expected.items():
        act = actual.get(key, "")
        if key == "business_scope":
            act_set = {_norm_text(x) for x in act.split(",") if x}
            need = [_norm_text(x) for x in exp.split(",") if x]
            if not all(n in act_set for n in need):
                bad.append(key)
            continue
        if _norm_text(act) != _norm_text(exp):
            bad.append(key)
    return bad


def replace_license_photo(panel, license_path: Path, page) -> None:
    item = form_item(panel, "资质照片")
    if item.count() == 0:
        item = panel.locator(".ant-form-item").filter(has_text="资质照片")
    item.first.wait_for(state="visible", timeout=15000)
    item.first.scroll_into_view_if_needed()
    _pause(page)

    thumbs = item.locator(".ant-upload-list-item, .ant-upload-list-item-container")
    for _ in range(5):
        if thumbs.count() == 0:
            break
        thumb = thumbs.first
        thumb.hover()
        _pause(page, 400)
        trash = item.locator(".anticon-delete, .ant-upload-list-item-card-actions-btn")
        if trash.count() == 0:
            trash = thumb.locator(".anticon-delete, .ant-upload-list-item-card-actions-btn")
        if trash.count() == 0:
            print("[changeFileELM] 未找到删除按钮，直接上传")
            break
        trash.first.click(force=True)
        _pause(page, 600)
        print("[changeFileELM] 已删除原资质照片")

    file_input = item.locator("input[type='file']")
    if file_input.count() == 0:
        hit = item.locator(".ant-upload.ant-upload-select, .ant-upload-select-picture-card, .ant-upload")
        if hit.count():
            hit.first.click(force=True)
            _pause(page)
        file_input = item.locator("input[type='file']")
    file_input.first.set_input_files(str(license_path))
    print(f"[changeFileELM] 已上传: {license_path.name}")


def select_ant_date(setup, panel, page, ymd: str) -> None:
    year_i, month_i, _ = (int(x) for x in ymd.split("-"))
    item = form_item(panel, "有效日期")
    item.first.wait_for(state="visible", timeout=10000)
    item.first.scroll_into_view_if_needed()

    long_term = item.locator("label.ant-checkbox-wrapper").filter(has_text="长期")
    if long_term.count():
        wrapper = long_term.first
        box = wrapper.locator("input[type='checkbox']")
        checked = "ant-checkbox-wrapper-checked" in (wrapper.get_attribute("class") or "") or (
            box.count() > 0 and box.first.is_checked()
        )
        if checked:
            wrapper.click()
            _pause(page, 400)
            print("[changeFileELM] 已取消「长期」")

    page.keyboard.press("Escape")
    _pause(page, 150)
    item.locator(".ant-picker-input input").click(force=True)
    _pause(page, 400)

    dropdown = setup.locator(".ant-picker-dropdown:not(.ant-picker-dropdown-hidden)").last
    dropdown.wait_for(state="visible", timeout=10000)

    dropdown.locator(".ant-picker-year-btn").click()
    _pause(page, 200)
    year_cell = dropdown.locator(".ant-picker-cell-inner", has_text=re.compile(rf"^{year_i}$"))
    for _ in range(24):
        if year_cell.count() and year_cell.first.is_visible():
            break
        nums = [int(x) for x in re.findall(r"\d{4}", dropdown.locator(".ant-picker-header-view").inner_text())]
        btn = ".ant-picker-header-super-prev-btn" if nums and year_i < min(nums) else ".ant-picker-header-super-next-btn"
        dropdown.locator(btn).click()
        _pause(page, 200)
    year_cell.first.click()
    _pause(page, 200)

    month_panel = dropdown.locator(".ant-picker-month-panel")
    if month_panel.count() == 0 or not month_panel.first.is_visible():
        dropdown.locator(".ant-picker-month-btn").click()
        _pause(page, 200)
    dropdown.locator(".ant-picker-cell-inner", has_text=re.compile(rf"^{month_i}月$")).click()
    _pause(page, 200)
    dropdown.locator(f'td.ant-picker-cell-in-view[title="{ymd}"]').click()
    _pause(page)


def _scroll_virtual(dropdown, page, *, top: bool = False, delta: int = 160) -> int:
    if top:
        dropdown.evaluate(
            """el => { const h = el.querySelector('.rc-virtual-list-holder'); if (h) h.scrollTop = 0; }"""
        )
        _pause(page, 100)
        return 0
    pos = dropdown.evaluate(
        f"""el => {{
          const h = el.querySelector('.rc-virtual-list-holder');
          if (!h) return -1;
          h.scrollTop = h.scrollTop + {delta};
          return h.scrollTop;
        }}"""
    )
    _pause(page, 80)
    return pos


def _option_texts(dropdown) -> list[str]:
    opts = dropdown.locator(".ant-select-item-option")
    seen: list[str] = []
    for i in range(opts.count()):
        text = (opts.nth(i).inner_text() or "").replace("\n", " ").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _collect_all_options(dropdown, page) -> list[str]:
    _scroll_virtual(dropdown, page, top=True)
    seen: list[str] = []
    last = -1
    for _ in range(30):
        for t in _option_texts(dropdown):
            if t not in seen:
                seen.append(t)
        top = dropdown.evaluate(
            """el => {
              const h = el.querySelector('.rc-virtual-list-holder');
              if (!h) return -1;
              h.scrollTop += Math.max(120, h.clientHeight * 0.8);
              return h.scrollTop;
            }"""
        )
        _pause(page, 80)
        if top == last:
            break
        last = top
    _scroll_virtual(dropdown, page, top=True)
    return seen


def _match_scope(target: str, available: list[str]) -> str | None:
    for text in available:
        if text == target or text.startswith(target):
            return text
    return None


def select_business_scope(setup, panel, page, raw_scope: str) -> None:
    """打开下拉，滚动虚拟列表直接点选项（不走搜索框输入）。"""
    wanted = resolve_scope_options(raw_scope)
    print(f"[changeFileELM] 经营范围映射 → {wanted}")
    item = form_item(panel, "经营范围")
    if item.count() == 0:
        item = panel.locator(".ant-form-item").filter(has_text="经营范围")
    item.first.wait_for(state="visible", timeout=15000)
    item.first.scroll_into_view_if_needed()

    while item.locator(".ant-select-selection-item-remove").count():
        item.locator(".ant-select-selection-item-remove").first.click(force=True)
        _pause(page, 150)

    def ensure_dd():
        item.locator(".ant-select-selector").click(force=True)
        _pause(page, 400)
        dd = setup.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)").last
        dd.wait_for(state="visible", timeout=10000)
        return dd

    def click_option(dd, matched: str) -> bool:
        opt = dd.locator(".ant-select-item-option").filter(
            has_text=re.compile(rf"^{re.escape(matched)}$")
        )
        if opt.count() == 0:
            opt = dd.locator(".ant-select-item-option", has_text=matched)
        if opt.count() == 0:
            return False
        if "ant-select-item-option-selected" not in (opt.first.get_attribute("class") or ""):
            opt.first.click(force=True)
            _pause(page, 250)
            print(f"[changeFileELM] 已选经营范围: {matched}")
            dismiss_license_already_used(setup, page, wait_ms=400)
        else:
            print(f"[changeFileELM] 经营范围已勾选: {matched}")
        return True

    dropdown = ensure_dd()
    available = _collect_all_options(dropdown, page)
    print(f"[changeFileELM] 经营范围选项: {available}")

    targets = [t for t in wanted if t != SCOPE_BUNDLE_COMBINED]
    deferred = SCOPE_BUNDLE_COMBINED in wanted
    selected_detailed = False

    def pick(target: str) -> bool:
        nonlocal dropdown
        if not dropdown.is_visible():
            dropdown = ensure_dd()
        matched = _match_scope(target, available)
        if not matched:
            print(f"[changeFileELM] 经营范围无匹配，跳过: {target}")
            return False
        _scroll_virtual(dropdown, page, top=True)
        for _ in range(30):
            if click_option(dropdown, matched):
                return True
            _scroll_virtual(dropdown, page, delta=160)
        print(f"[changeFileELM] 经营范围点击失败: {matched}")
        return False

    for target in targets:
        if pick(target) and target in SCOPE_BUNDLE_DETAILED:
            selected_detailed = True
    if deferred and not selected_detailed:
        pick(SCOPE_BUNDLE_COMBINED)

    page.keyboard.press("Escape")
    _pause(page, 200)


def _fill_license_text_fields(setup, panel, page, job: dict, *, only: set[str] | None = None) -> None:
    """填写文本类字段；only 非空时只改不一致项。"""
    address = str(job["address"]).strip()
    mapping = (
        ("license_no", "请输入许可证编号", str(job["license_no"]).strip()),
        ("operator_name", "请输入单位名称", str(job["operator_name"]).strip()),
        ("credit_code", "请输入社会信用代码", str(job["credit_code"]).strip()),
        ("legal_person", "请输入法人代表", str(job["legal_person"]).strip()),
        ("reg_address", "请输入注册地址", address),
        ("biz_address", "请输入经营场所", address),
    )
    for key, ph, val in mapping:
        if only is not None and key not in only:
            continue
        fill_by_placeholder(panel, ph, val)
        dismiss_license_already_used(setup, page)


def fill_industry_license(setup, panel, page, job: dict, license_path: Path, *, skip_photo: bool = False) -> None:
    if skip_photo:
        print("[changeFileELM] 跳过资质照片更换")
    else:
        replace_license_photo(panel, license_path, page)
        confirm_ocr_overwrite(setup, page, timeout_ms=10000)
        dismiss_license_already_used(setup, page, wait_ms=800)

    _fill_license_text_fields(setup, panel, page, job)
    select_business_scope(setup, panel, page, str(job["business_scope"]).strip())
    dismiss_license_already_used(setup, page, wait_ms=800)
    select_ant_date(setup, panel, page, str(job["valid_until"]).strip())
    dismiss_license_already_used(setup, page)


def verify_and_fix_license(setup, panel, page, job: dict, *, rounds: int = 2) -> None:
    """填完后对照前端 job；不一致则改对应项，最多 rounds 轮后再提交。"""
    expected = expected_license_fields(job)
    for round_i in range(1, rounds + 1):
        _pause(page, 400)
        actual = read_license_fields(panel)
        bad = diff_license_fields(actual, expected)
        if not bad:
            print(f"[changeFileELM] 校验通过（第 {round_i} 轮）")
            return
        print(f"[changeFileELM] 校验不一致（第 {round_i} 轮）: {bad}")
        for key in bad:
            print(f"  {key}: 页面={actual.get(key)!r} 期望={expected.get(key)!r}")

        text_keys = {
            "license_no",
            "operator_name",
            "credit_code",
            "legal_person",
            "reg_address",
            "biz_address",
        }
        need_text = text_keys.intersection(bad)
        if need_text:
            _fill_license_text_fields(setup, panel, page, job, only=need_text)
        if "business_scope" in bad:
            select_business_scope(setup, panel, page, str(job["business_scope"]).strip())
            dismiss_license_already_used(setup, page, wait_ms=600)
        if "valid_until" in bad:
            select_ant_date(setup, panel, page, str(job["valid_until"]).strip())
            dismiss_license_already_used(setup, page)

    actual = read_license_fields(panel)
    bad = diff_license_fields(actual, expected)
    if bad:
        raise RuntimeError(f"校验仍不一致，放弃提交: {bad}")
    print("[changeFileELM] 修正后校验通过")


def switch_to_chain_account(page) -> None:
    trigger = page.locator(".account-switch-trigger")
    trigger.wait_for(state="visible", timeout=15000)
    current = (trigger.inner_text() or "").replace("\n", " ").strip()
    if CHAIN_ACCOUNT_NEEDLE in current:
        print(f"[changeFileELM] 已在连锁账号: {current}")
        return

    def _pick() -> None:
        trigger.click()
        _pause(page, 600)
        item = (
            page.locator("li.cascade-menu-item")
            .filter(has_text=re.compile(CHAIN_ACCOUNT_NEEDLE))
            .filter(has_text="连锁")
        )
        item.first.wait_for(state="visible", timeout=10000)
        item.first.click()

    def _wait_switched(*, timeout: int = 20000) -> None:
        page.wait_for_function(
            """(needle) => {
              const t = document.querySelector('.account-switch-trigger');
              return !!(t && t.innerText && t.innerText.includes(needle));
            }""",
            arg=CHAIN_ACCOUNT_NEEDLE,
            timeout=timeout,
        )

    _pick()
    try:
        _wait_switched()
    except Exception:
        print("[changeFileELM] 账号切换未确认，重试")
        _pick()
        _wait_switched()
    _pause(page, 1200)
    print(f"[changeFileELM] 已切换账号: {(trigger.inner_text() or '').replace(chr(10), ' ').strip()}")


def open_store_setup(page, store_id: str):
    """查门店 → 点唯一「店铺设置」→ 返回新标签页。"""
    inp = page.get_by_placeholder("输入门店ID查询")
    inp.wait_for(state="visible", timeout=20000)
    inp.fill(store_id)
    _pause(page)
    page.locator("button.ant-btn-primary").filter(has_text=re.compile(r"查\s*询")).first.click()
    _pause(page, 1500)

    settings = page.get_by_role("button", name="店铺设置")
    for _ in range(20):
        if settings.count() == 1:
            break
        _pause(page, 500)
    if settings.count() != 1:
        raise RuntimeError(f"期望仅 1 条门店结果，实际「店铺设置」={settings.count()} 个")

    with page.context.expect_page(timeout=15000) as info:
        settings.click(force=True)
    setup_page = info.value
    setup_page.wait_for_load_state("domcontentloaded")
    setup_page.wait_for_url("**/storeSetupPc/**", timeout=15000)
    setup_page.wait_for_selector("iframe.shop-base-unify", timeout=20000)
    _pause(setup_page, 1500)
    return setup_page


def run(
    job: dict,
    license_path: Path,
    *,
    hold: bool = False,
    skip_photo: bool = False,
    skip_submit: bool = False,
) -> None:
    """供 run_qualification / worker 调用；未填 elm_store_id 时跳过。"""
    store_id = str(job.get("elm_store_id") or job.get("store_id") or "").strip()
    if not store_id:
        print("[changeFileELM] 跳过：未填 elm_store_id")
        return

    require_job_fields(job)
    if not skip_photo and not license_path.is_file():
        raise FileNotFoundError(f"证件图不存在: {license_path}")

    print(
        f"[changeFileELM] elm_store_id={store_id} license_no={job['license_no']} "
        f"skip_photo={skip_photo} skip_submit={skip_submit}"
    )

    page = openChrom(ELM_URL)
    setup_page = None
    try:
        _pause(page, 2500)
        switch_to_chain_account(page)
        # 菜单浮层不稳定，直接进门店列表
        page.goto(STORE_LIST_URL, wait_until="domcontentloaded")
        page.wait_for_url("**/storeManagementPc/**", timeout=20000)
        _pause(page, 1500)

        setup_page = open_store_setup(page, store_id)
        setup = setup_page.frame_locator("iframe.shop-base-unify")

        edit_btn = setup.get_by_role("button", name=re.compile(r"修改\s*信息"))
        if _visible(edit_btn):
            edit_btn.first.click()
            _pause(setup_page, 1500)
            dismiss_blocking_modals(setup, setup_page)
        else:
            print("[changeFileELM] 未看到「修改信息」，可能已在编辑态")

        next_btn = setup.get_by_role("button", name=re.compile(r"下一\s*步"))
        next_btn.wait_for(state="visible", timeout=20000)
        next_btn.click()
        _pause(setup_page, 2000)
        dismiss_blocking_modals(setup, setup_page)

        industry = (
            setup.locator(".ant-collapse-item")
            .filter(has_text=re.compile(r"行业资质\s*1"))
            .filter(has_text="食品经营许可证")
        )
        industry.first.wait_for(state="visible", timeout=20000)
        if "ant-collapse-item-active" not in (industry.first.get_attribute("class") or ""):
            industry.first.locator(".ant-collapse-header").click()
            _pause(setup_page, 500)
        industry.first.locator(".ant-collapse-header").scroll_into_view_if_needed()
        dismiss_blocking_modals(setup, setup_page)

        fill_industry_license(
            setup, industry.first, setup_page, job, license_path, skip_photo=skip_photo
        )
        print("[changeFileELM] 行业资质字段已填写")
        dismiss_blocking_modals(setup, setup_page)
        verify_and_fix_license(setup, industry.first, setup_page, job)
        dismiss_blocking_modals(setup, setup_page)

        if skip_submit:
            print("[changeFileELM] 跳过提交审核")
        else:
            submit_btn = setup.get_by_role("button", name=re.compile(r"提交\s*审核"))
            submit_btn.wait_for(state="visible", timeout=10000)
            submit_btn.click()
            _pause(setup_page, 2500)
            print("[changeFileELM] 已点击提交审核")

        if hold:
            input("饿了么页面已停住（可核对填写），按回车关闭...")
    finally:
        if setup_page is not None and not setup_page.is_closed():
            try:
                setup_page.close()
            except Exception:
                pass
        closeChrom(page)


def main() -> int:
    parser = argparse.ArgumentParser(description="饿了么资质填写")
    parser.add_argument("--job", required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--hold", action="store_true")
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
        print(f"[changeFileELM] failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
