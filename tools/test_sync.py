#!/usr/bin/env python3
"""실시간 동기화(구글 시트 + Apps Script) 로컬 검증.

로컬 서버(cpick-bracket-app/) + Playwright(headless Chromium)로
Apps Script GET/POST 를 모킹해 다음을 확인한다.

  1) 연동 전(local 모드) — 누구나 바로 입력 가능, 원격 요청 없음
  2) 연동 후 — 즉시 GET 반영, 5초 폴링으로 원격 점수 갱신, 보기 전용 잠금
  3) 관리자 PIN — 오답 거부 / 3256 성공, 입력 시 text/plain POST 로 0.6초 디바운스 저장
  4) 입력 중에는 폴링이 입력 칸을 덮어쓰지 않음
  5) 모바일 390px — 가로 스크롤 0, 콘솔 에러 0
"""
import json
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}/"
API = "https://script.google.com/macros/s/TESTEXEC/exec"
OUT = os.path.join(HERE, "tools", "shots")
os.makedirs(OUT, exist_ok=True)

MOCK = {"data": None, "updatedAt": "2026-11-19 10:00:00", "pin": "3256"}
POSTS = []
GETS = []
console_errors, page_errors = [], []
results = []


def ok(name, cond, detail=None):
    results.append((bool(cond), name, detail))
    print(("통과  " if cond else "실패  ") + name + ("" if detail is None else " :: " + json.dumps(detail, ensure_ascii=False)))


def handle(route):
    req = route.request
    if req.method == "POST":
        body = {}
        try:
            body = json.loads(req.post_data or "{}")
        except Exception:
            body = {"_raw": req.post_data}
        POSTS.append({"body": body, "headers": req.headers})
        if body.get("action") == "verify_pin":
            if str(body.get("pin")) == MOCK["pin"]:
                return route.fulfill(status=200, content_type="application/json",
                                     headers={"Access-Control-Allow-Origin": "*"},
                                     body=json.dumps({"ok": True, "verified": True}))
            return route.fulfill(status=200, content_type="application/json",
                                 headers={"Access-Control-Allow-Origin": "*"},
                                 body=json.dumps({"ok": False, "error": "PIN_MISMATCH"}))
        if str(body.get("pin")) != MOCK["pin"]:
            return route.fulfill(status=200, content_type="application/json",
                                 headers={"Access-Control-Allow-Origin": "*"},
                                 body=json.dumps({"ok": False, "error": "PIN_MISMATCH"}))
        MOCK["data"] = body.get("data")
        MOCK["updatedAt"] = "2026-11-19 10:05:00"
        return route.fulfill(status=200, content_type="application/json",
                             headers={"Access-Control-Allow-Origin": "*"},
                             body=json.dumps({"ok": True, "updatedAt": MOCK["updatedAt"]}))
    GETS.append(req.url)
    payload = {"ok": True, "data": MOCK["data"], "updatedAt": MOCK["updatedAt"], "pinSet": True}
    return route.fulfill(status=200, content_type="application/json",
                         headers={"Access-Control-Allow-Origin": "*"},
                         body=json.dumps(payload, ensure_ascii=False))


def main():
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1",
                               "--directory", HERE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="ko-KR")
            page = ctx.new_page()
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route("https://script.google.com/**", handle)

            # ---------- 1) 연동 전 (local 모드) ----------
            page.goto(BASE, wait_until="networkidle")
            ok("local 모드 배지", page.inner_text("[data-sync-badge]").strip() == "⚪ 연동 전",
               page.inner_text("[data-sync-badge]"))
            ok("local 모드에서 관리자 버튼 숨김", page.is_hidden('[data-act="adminToggle"]'))
            ok("local 모드에서 잠금 없음(ro-mode 미적용)", page.evaluate("!document.body.classList.contains('ro-mode')"))
            base_state = json.loads(page.evaluate("JSON.stringify(window.cpick.state())"))

            page.fill('input[data-score="p1-0:c"]', "5")
            page.wait_for_timeout(300)
            ok("local 모드 점수 입력 가능", page.evaluate("window.cpick.state().part1[0].c") == "5",
               page.evaluate("window.cpick.state().part1[0].c"))
            ok("local 모드에서는 원격 요청 없음", len(GETS) == 0 and len(POSTS) == 0, {"get": len(GETS), "post": len(POSTS)})

            # ---------- 2) 연동 후: 즉시 GET + 보기 전용 ----------
            remote = json.loads(json.dumps(base_state))
            remote["header"]["title"] = "원격 저장된 11월 대회"
            remote["part1"][0]["c"] = "11"
            remote["part1"][0]["b"] = "9"
            remote["participants"] = remote["participants"][:8]
            MOCK["data"] = remote

            page.goto(BASE + "?api=" + API, wait_until="networkidle")
            page.wait_for_function("() => document.querySelector('[data-sync-badge]').textContent.indexOf('실시간') >= 0", timeout=15000)
            page.wait_for_timeout(400)
            ok("연동 즉시 GET 1회 이상", len(GETS) >= 1, {"gets": len(GETS)})
            ok("배지 '🟢 실시간 동기화'", page.inner_text("[data-sync-badge]").strip() == "🟢 실시간 동기화",
               page.inner_text("[data-sync-badge]"))
            ok("원격 제목 반영", page.inner_text(".title").strip() == "원격 저장된 11월 대회", page.inner_text(".title"))
            ok("원격 점수 반영(11:9)",
               page.eval_on_selector('input[data-score="p1-0:c"]', "el => el.value") == "11" and
               page.eval_on_selector('input[data-score="p1-0:b"]', "el => el.value") == "9")
            ok("보기 전용 클래스 적용", page.evaluate("document.body.classList.contains('ro-mode')"))
            ok("보기 전용: 입력칸 포인터 차단",
               page.eval_on_selector('input[data-score="p1-0:c"]', "el => getComputedStyle(el).pointerEvents") == "none")
            ok("관리자 버튼 노출", page.is_visible('[data-act="adminToggle"]') and
               page.inner_text('[data-act="adminToggle"]').strip() == "🔐 관리자 입력")
            blocked = False
            try:
                page.click('input[data-score="p1-0:c"]', timeout=1200)
                page.keyboard.type("7")
                page.wait_for_timeout(200)
                blocked = page.evaluate("window.cpick.state().part1[0].c") == "11"
            except Exception:
                blocked = True
            ok("보기 전용: 점수 변경 차단", blocked, page.evaluate("window.cpick.state().part1[0].c"))
            ok("보기 전용: 대진 버튼 차단",
               page.evaluate("""() => {
                 const b = document.querySelector('[data-act=generate]');
                 b.click();
                 return document.body.classList.contains('ro-mode');
               }"""))
            page.screenshot(path=os.path.join(OUT, "sync-01-viewonly.png"), full_page=False)

            # ---------- 2b) 5초 폴링 ----------
            gets_before = len(GETS)
            remote2 = json.loads(json.dumps(remote))
            remote2["part1"][0]["c"] = "7"
            remote2["part1"][0]["b"] = "11"
            MOCK["data"] = remote2
            MOCK["updatedAt"] = "2026-11-19 10:03:00"
            page.wait_for_timeout(6200)
            ok("5초 폴링으로 원격 점수 갱신(7:11)",
               page.eval_on_selector('input[data-score="p1-0:c"]', "el => el.value") == "7",
               page.eval_on_selector('input[data-score="p1-0:c"]', "el => el.value"))
            ok("폴링 주기(6.2초에 GET 1회 이상 추가)", len(GETS) - gets_before >= 1, {"new": len(GETS) - gets_before})

            # ---------- 3) 관리자 PIN ----------
            page.click('[data-act="adminToggle"]')
            page.wait_for_selector("[data-pin-modal]:not([hidden])", timeout=3000)
            page.fill("[data-pin-input]", "1111")
            page.click("[data-pin-ok]")
            page.wait_for_timeout(900)
            ok("오답 PIN 거부 메시지", "맞지 않습니다" in page.inner_text("[data-pin-msg]"), page.inner_text("[data-pin-msg]"))
            ok("오답 PIN: 여전히 보기 전용", page.evaluate("document.body.classList.contains('ro-mode')"))
            ok("오답 PIN: 검증만 요청(저장 안 함)",
               POSTS and POSTS[-1]["body"].get("action") == "verify_pin" and "data" not in POSTS[-1]["body"],
               {"posts": len(POSTS)})

            page.fill("[data-pin-input]", "3256")
            page.click("[data-pin-ok]")
            page.wait_for_timeout(900)
            ok("정답 PIN 3256 통과", not page.evaluate("document.body.classList.contains('ro-mode')"))
            ok("관리자 버튼 라벨 전환", "관리자 잠금" in page.inner_text('[data-act="adminToggle"]'),
               page.inner_text('[data-act="adminToggle"]'))
            ok("PIN 모달 닫힘", page.is_hidden("[data-pin-modal]"))

            # ---------- 3b) 입력 → 0.6초 디바운스 POST ----------
            posts_before = len(POSTS)
            page.fill('input[data-score="p1-1:c"]', "11")
            page.wait_for_timeout(180)
            mid = len(POSTS)
            page.wait_for_timeout(1200)
            ok("디바운스(즉시 전송하지 않음)", mid == posts_before, {"after180ms": mid - posts_before})
            saved = POSTS[-1]["body"] if len(POSTS) > posts_before else {}
            ok("점수 입력 시 POST 저장", saved.get("pin") == "3256" and
               saved.get("data", {}).get("part1", [{}])[1].get("c") == "11",
               {"pin": saved.get("pin")})
            ctype = (POSTS[-1]["headers"].get("content-type") or "") if POSTS else ""
            ok("POST Content-Type=text/plain (CORS 프리플라이트 회피)", ctype.startswith("text/plain"), ctype)
            ok("시트 응답 후 배지 실시간 복귀", page.inner_text("[data-sync-badge]").strip() == "🟢 실시간 동기화",
               page.inner_text("[data-sync-badge]"))

            # ---------- 4) 입력 중 덮어쓰기 방지 ----------
            page.click('input[data-score="p1-2:c"]')
            page.fill('input[data-score="p1-2:c"]', "5")
            remote3 = json.loads(json.dumps(remote2))
            remote3["part1"][2]["c"] = "9"
            MOCK["data"] = remote3
            page.wait_for_timeout(6200)
            ok("입력 중인 칸은 폴링이 덮어쓰지 않음",
               page.eval_on_selector('input[data-score="p1-2:c"]', "el => el.value") == "5",
               page.eval_on_selector('input[data-score="p1-2:c"]', "el => el.value"))
            page.screenshot(path=os.path.join(OUT, "sync-02-admin.png"))

            # 관리자 잠금
            page.click('[data-act="adminToggle"]')
            page.wait_for_timeout(300)
            ok("관리자 잠금 → 다시 보기 전용", page.evaluate("document.body.classList.contains('ro-mode')"))

            # ---------- 5) 모바일 390px ----------
            m = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                    is_mobile=True, has_touch=True, locale="ko-KR")
            mp = m.new_page()
            m_console, m_page_errors = [], []
            mp.on("console", lambda x: m_console.append(x.text) if x.type == "error" else None)
            mp.on("pageerror", lambda e: m_page_errors.append(str(e)))
            mp.route("https://script.google.com/**", handle)
            mp.goto(BASE + "?api=" + API, wait_until="networkidle")
            mp.wait_for_timeout(1200)
            dims = mp.evaluate("""() => ({
              sw: document.documentElement.scrollWidth,
              iw: window.innerWidth,
              barW: document.querySelector('[data-syncbar]').getBoundingClientRect().width,
              barH: document.querySelector('[data-syncbar]').getBoundingClientRect().height,
              badge: document.querySelector('[data-sync-badge]').textContent,
              info: document.querySelector('[data-sync-info]').getBoundingClientRect().width
            })""")
            ok("모바일 390px 가로 스크롤 없음", dims["sw"] <= dims["iw"] + 1, dims)
            ok("모바일 콘솔 에러 0", len(m_console) == 0, m_console[:3])
            ok("모바일 페이지 에러 0", len(m_page_errors) == 0, m_page_errors[:3])
            ok("모바일 배지 표시", "실시간" in dims["badge"], dims["badge"])
            mp.screenshot(path=os.path.join(OUT, "sync-03-mobile.png"))
            mp.click('[data-act="adminToggle"]')
            mp.wait_for_timeout(400)
            mp.screenshot(path=os.path.join(OUT, "sync-04-mobile-pin.png"))
            m.close()

            browser.close()

        ok("데스크톱 콘솔 에러 0", len(console_errors) == 0, console_errors[:3])
        ok("데스크톱 페이지 에러 0", len(page_errors) == 0, page_errors[:3])
    finally:
        server.terminate()

    passed = sum(1 for r in results if r[0])
    print(f"\n=== {passed}/{len(results)} 통과 ===")
    for good, name, detail in results:
        if not good:
            print("  실패:", name, detail)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
