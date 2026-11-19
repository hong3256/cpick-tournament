#!/usr/bin/env python3
"""배포된 사이트에서 실시간 동기화 UI 검증 (Apps Script 응답은 모킹)."""
import json
import os
import sys

from playwright.sync_api import sync_playwright

URL = "https://hong3256.github.io/cpick-tournament/"
API = "https://script.google.com/macros/s/LIVETEST/exec"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(OUT, exist_ok=True)

MOCK = {"data": None, "updatedAt": "2026-11-19 10:00:00", "pin": "3256"}
POSTS = []


def handle(route):
    req = route.request
    hdr = {"Access-Control-Allow-Origin": "*"}
    if req.method == "POST":
        body = json.loads(req.post_data or "{}")
        POSTS.append(body)
        if body.get("action") == "verify_pin":
            good = str(body.get("pin")) == MOCK["pin"]
            return route.fulfill(status=200, content_type="application/json", headers=hdr,
                                 body=json.dumps({"ok": good, "verified": good} if good else
                                                 {"ok": False, "error": "PIN_MISMATCH"}))
        MOCK["data"] = body.get("data")
        return route.fulfill(status=200, content_type="application/json", headers=hdr,
                             body=json.dumps({"ok": True, "updatedAt": "2026-11-19 10:05:00"}))
    return route.fulfill(status=200, content_type="application/json", headers=hdr,
                         body=json.dumps({"ok": True, "data": MOCK["data"], "updatedAt": MOCK["updatedAt"]}, ensure_ascii=False))


def main():
    errs, perrs = [], []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                            is_mobile=True, has_touch=True, locale="ko-KR")
        page = ctx.new_page()
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: perrs.append(str(e)))
        page.route("https://script.google.com/**", handle)

        page.goto(URL, wait_until="networkidle")
        local_badge = page.inner_text("[data-sync-badge]").strip()
        editable = page.evaluate("!document.body.classList.contains('ro-mode')")
        state = json.loads(page.evaluate("JSON.stringify(window.cpick.state())"))
        state["header"]["title"] = "배포 사이트 원격 확인"
        state["part1"][0]["c"] = "11"
        state["part1"][0]["b"] = "9"
        MOCK["data"] = state

        page.goto(URL + "?api=" + API, wait_until="networkidle")
        page.wait_for_function("() => document.querySelector('[data-sync-badge]').textContent.indexOf('실시간') >= 0", timeout=20000)
        page.wait_for_timeout(500)
        remote_title = page.inner_text(".title").strip()
        remote_score = page.eval_on_selector('input[data-score="p1-0:c"]', "el => el.value")
        locked = page.evaluate("document.body.classList.contains('ro-mode')")
        sw = page.evaluate("() => document.documentElement.scrollWidth")
        iw = page.evaluate("() => window.innerWidth")
        page.click('[data-act="adminToggle"]')
        page.fill("[data-pin-input]", "3256")
        page.click("[data-pin-ok]")
        page.wait_for_timeout(900)
        unlocked = not page.evaluate("document.body.classList.contains('ro-mode')")
        page.fill('input[data-score="p1-3:c"]', "11")
        page.wait_for_timeout(1100)
        saved = [x for x in POSTS if "data" in x]
        page.screenshot(path=os.path.join(OUT, "live-sync-admin.png"))
        b.close()

    checks = [
        ("배포 사이트 로컬 모드 배지", local_badge == "⚪ 연동 전", local_badge),
        ("배포 사이트 기본 입력 가능", editable is True, editable),
        ("?api= 로 연동 → 원격 제목 반영", remote_title == "배포 사이트 원격 확인", remote_title),
        ("원격 점수 반영", remote_score == "11", remote_score),
        ("보기 전용 잠금", locked is True, locked),
        ("모바일 가로 스크롤 없음", sw <= iw + 1, {"sw": sw, "iw": iw}),
        ("PIN 3256 으로 입력 모드", unlocked is True, unlocked),
        ("입력 후 POST 저장", bool(saved) and saved[-1]["data"]["part1"][3]["c"] == "11", saved[-1] if saved else None),
        ("콘솔 에러 0", len(errs) == 0, errs[:3]),
        ("페이지 에러 0", len(perrs) == 0, perrs[:3]),
    ]
    ok = 0
    for name, cond, detail in checks:
        ok += 1 if cond else 0
        print(("통과  " if cond else "실패  ") + name + " :: " + json.dumps(detail, ensure_ascii=False))
    print(f"\n=== {ok}/{len(checks)} 통과 ===")
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
