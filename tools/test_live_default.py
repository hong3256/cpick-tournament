#!/usr/bin/env python3
"""라이브 배포본 기본 연동 검증
   대상: https://hong3256.github.io/cpick-tournament/
   확인: 1) 설정 없이 🟢 실시간 동기화  2) 보기 전용 차단  3) PIN 3256 관리자 해제  4) 콘솔/페이지 에러 0
"""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://hong3256.github.io/cpick-tournament/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(OUT, exist_ok=True)

console_errors, page_errors, failed = [], [], []
report = {}


def wait_badge(page, want, timeout=45000):
    end = time.time() + timeout / 1000.0
    last = ""
    while time.time() < end:
        last = page.inner_text("[data-sync-badge]").strip()
        if want in last:
            return last
        page.wait_for_timeout(500)
    return last


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chromium")
        ctx = browser.new_context(viewport={"width": 412, "height": 915}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True, locale="ko-KR")
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on("requestfailed", lambda r: failed.append(r.url + " :: " + str(r.failure)))

        resp = page.goto(URL, wait_until="networkidle", timeout=90000)
        report["http_status"] = resp.status
        report["title"] = page.title()

        # 1) 설정 없이 바로 실시간 동기화
        badge = wait_badge(page, "실시간 동기화")
        report["badge_initial"] = badge
        report["sync_info_initial"] = page.inner_text("[data-sync-info]").strip()
        report["ro_mode_initial"] = page.eval_on_selector("body", "b => b.classList.contains('ro-mode')")
        report["admin_btn_visible"] = page.is_visible('[data-act="adminToggle"]')
        report["admin_btn_text"] = page.inner_text('[data-act="adminToggle"]').strip()
        page.screenshot(path=os.path.join(OUT, "live-1-연동됨-보기전용.png"), full_page=False)

        # 2) 보기 전용 차단: 팀 나누기 버튼 → 토스트, 상태 불변
        before = page.evaluate("() => localStorage.getItem('cpick-monthly-bracket-v2') || ''")
        page.click('[data-act="generate"]', force=True)
        page.wait_for_timeout(600)
        toast = page.inner_text("[data-toast]").strip() if page.is_visible("[data-toast]") else ""
        report["locked_click_toast"] = toast
        after = page.evaluate("() => localStorage.getItem('cpick-monthly-bracket-v2') || ''")
        report["locked_state_unchanged"] = (before == after)

        # 3) PIN 모달: 틀린 PIN → 경고, 맞는 PIN → 해제
        page.click('[data-act="adminToggle"]')
        page.wait_for_selector("[data-pin-modal]:not([hidden])", timeout=5000)
        page.fill("[data-pin-input]", "0000")
        page.click("[data-pin-ok]")
        page.wait_for_timeout(2500)
        report["wrong_pin_msg"] = page.inner_text("[data-pin-msg]").strip()
        page.fill("[data-pin-input]", "3256")
        page.click("[data-pin-ok]")
        end = time.time() + 30
        unlocked = False
        while time.time() < end:
            if not page.eval_on_selector("body", "b => b.classList.contains('ro-mode')"):
                unlocked = True
                break
            page.wait_for_timeout(400)
        report["pin_unlocked"] = unlocked
        report["pin_modal_hidden"] = page.eval_on_selector("[data-pin-modal]", "m => m.hidden")
        # 해제 직후 자동 저장(업로드)이 끝나 🟢 로 돌아올 때까지
        badge_after = wait_badge(page, "실시간 동기화", timeout=25000)
        page.wait_for_timeout(500)
        report["badge_after_pin"] = badge_after
        report["sync_info_after_pin"] = page.inner_text("[data-sync-info]").strip()
        report["admin_btn_after_pin"] = page.inner_text('[data-act="adminToggle"]').strip()
        report["name_input_pointer_events"] = page.eval_on_selector(
            '.pname', "e => getComputedStyle(e).pointerEvents")
        page.screenshot(path=os.path.join(OUT, "live-2-관리자-해제.png"), full_page=False)

        # 다시 잠그기
        page.click('[data-act="adminToggle"]')
        page.wait_for_timeout(800)
        report["relocked"] = page.eval_on_selector("body", "b => b.classList.contains('ro-mode')")
        page.screenshot(path=os.path.join(OUT, "live-3-다시-잠금.png"), full_page=False)

        # 서비스워커/캐시 이름 확인
        report["sw_caches"] = page.evaluate(
            "async () => (await caches.keys())"
        )

        browser.close()

    report["console_errors"] = console_errors
    report["page_errors"] = page_errors
    report["request_failed"] = failed
    print(json.dumps(report, ensure_ascii=False, indent=2))

    bad = console_errors or page_errors or failed
    if not report.get("http_status") == 200 or "실시간 동기화" not in report.get("badge_initial", "") \
            or not report.get("ro_mode_initial") or not report.get("locked_state_unchanged") \
            or "PIN이 맞지 않습니다" not in report.get("wrong_pin_msg", "") \
            or not report.get("pin_unlocked") or "관리자 입력 모드" not in report.get("sync_info_after_pin", "") \
            or report.get("admin_btn_after_pin") != "🔓 관리자 잠금" \
            or report.get("name_input_pointer_events") == "none" \
            or bad:
        print("RESULT: FAIL")
        sys.exit(1)
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
