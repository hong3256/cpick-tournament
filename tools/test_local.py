#!/usr/bin/env python3
"""로컬 검증: PWA 설치 요건 + 기존 기능 (참석자 자동 편성, 점수, 공유, 이미지 저장).
GitHub Pages와 같은 하위 경로(/cpick-tournament/)로 서빙해서 확인한다.
"""
import http.server
import json
import os
import socketserver
import threading
import sys

from playwright.sync_api import sync_playwright

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PREFIX = "/cpick-tournament/"
PORT = 8765
OUT = os.path.join(APP, "tools", "shots")
os.makedirs(OUT, exist_ok=True)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=APP, **kw)

    def translate_path(self, path):
        if path.startswith(PREFIX):
            path = path[len(PREFIX) - 1:]
        return super().translate_path(path)

    def log_message(self, *a):
        pass


def serve():
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


NAMES = [
    ("조덕기", "남"), ("김인옥", "여"), ("황병열", "남"), ("박종민", "남"),
    ("이보은", "여"), ("최현우", "남"), ("정미라", "여"), ("한상수", "남"),
    ("오세영", "남"), ("윤정희", "여"), ("장태호", "남"), ("서지연", "여"),
]


def main():
    httpd = serve()
    results = []
    console_errors = []
    page_errors = []
    failed = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 412, "height": 900},
                                      device_scale_factor=2, is_mobile=True, has_touch=True,
                                      accept_downloads=True)
            page = ctx.new_page()
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.on("requestfailed", lambda r: failed.append(r.url + " :: " + str(r.failure)))

            url = f"http://127.0.0.1:{PORT}{PREFIX}"
            resp = page.goto(url, wait_until="networkidle")
            results.append(("페이지 응답", resp.status if resp else None))

            # --- PWA 필수 리소스 ---
            man = page.evaluate("""async () => {
              const r = await fetch('manifest.json', {cache:'no-store'});
              const j = await r.json();
              return {status: r.status, name: j.name, short: j.short_name, start: j.start_url,
                      display: j.display, icons: j.icons.length, theme: j.theme_color};
            }""")
            results.append(("manifest.json", man))

            sw = page.evaluate("""async () => {
              const r = await fetch('sw.js', {cache:'no-store'});
              return {status: r.status, type: r.headers.get('content-type')};
            }""")
            results.append(("sw.js", sw))

            icon_codes = page.evaluate("""async () => {
              const out = {};
              for (const u of ['icon-192.png','icon-512.png','icon-maskable-512.png','apple-touch-icon.png','favicon.ico']) {
                try { const r = await fetch(u, {cache:'no-store'}); out[u] = r.status; } catch(e) { out[u] = 'ERR'; }
              }
              return out;
            }""")
            results.append(("icons", icon_codes))

            # 서비스 워커 등록/활성
            page.wait_for_function("() => navigator.serviceWorker && navigator.serviceWorker.controller !== null", timeout=15000)
            swstate = page.evaluate("""async () => {
              const reg = await navigator.serviceWorker.ready;
              const keys = await caches.keys();
              const c = await caches.open(keys[0]);
              const cached = (await c.keys()).map(r => new URL(r.url).pathname);
              return {scope: reg.scope, active: reg.active && reg.active.state, caches: keys, cached};
            }""")
            results.append(("service worker", swstate))

            # --- 기능 1: 참석자 붙여넣기 + 자동 편성 ---
            page.click('[data-act="pasteToggle"]')
            page.fill('[data-paste-box]', "\n".join(f"{n} {g}" for n, g in NAMES))
            page.click('[data-act="pasteAdd"]')
            page.wait_for_timeout(300)
            pcount = page.evaluate("() => window.cpick.state().participants.length")
            results.append(("참석자 수", pcount))

            page.click('[data-act="generate"]')
            page.wait_for_timeout(500)
            gen = page.evaluate("""() => {
              const s = window.cpick.state();
              return {part1: s.part1.length, teams: s.teams.length,
                      rows: document.querySelectorAll('[data-mid]').length,
                      rosterC: document.querySelectorAll('[data-roster-c] .rmem, [data-roster-c] > *').length,
                      rosterB: document.querySelectorAll('[data-roster-b] .rmem, [data-roster-b] > *').length,
                      bracketNodes: document.querySelectorAll('[data-bracket] .bmatch').length};
            }""")
            results.append(("자동 편성", gen))
            page.screenshot(path=os.path.join(OUT, "01-generated.png"), full_page=False)

            # --- 기능 2: 점수 입력 + 보드 반영 ---
            page.fill('input[data-score="p1-0:c"]', "11")
            page.fill('input[data-score="p1-0:b"]', "7")
            page.dispatch_event('input[data-score="p1-0:b"]', "input")
            page.wait_for_timeout(300)
            board = page.evaluate("""() => ({
              sumC: document.querySelector('[data-sum-c]').textContent,
              sumB: document.querySelector('[data-sum-b]').textContent,
              result: document.querySelector('[data-result="p1-0"]').textContent,
              saved: !!localStorage.getItem('cpick-monthly-bracket-v2')
            })""")
            results.append(("점수 입력", board))

            # --- 기능 3: 공유 텍스트 / 카톡 버튼 ---
            share = page.evaluate("() => window.cpick.shareText().slice(0, 160)")
            results.append(("공유 텍스트", share))
            page.click('[data-act="kakaoShare"]')
            page.wait_for_timeout(600)
            results.append(("카톡 버튼 클릭 후 페이지 상태", page.evaluate("() => document.title")))

            # --- 기능 4: 대진표 이미지 저장(다운로드) ---
            blob = page.evaluate("""async () => {
              const b = await window.cpick.cardBlob();
              return b ? b.size : 0;
            }""")
            results.append(("대진표 이미지 blob(bytes)", blob))
            try:
                with page.expect_download(timeout=15000) as dl:
                    page.click('[data-act="saveImage"]')
                d = dl.value
                path = os.path.join(OUT, "download-" + (d.suggested_filename or "bracket.png"))
                d.save_as(path)
                results.append(("이미지 저장 다운로드", {"file": os.path.basename(path),
                                                    "bytes": os.path.getsize(path)}))
            except Exception as e:
                results.append(("이미지 저장 다운로드", f"실패: {e}"))

            # --- 기능 5: 새로고침 후 상태 유지 ---
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(600)
            persist = page.evaluate("""() => {
              const s = window.cpick.state();
              return {part1: s.part1.length, c0: s.part1[0] && s.part1[0].c, b0: s.part1[0] && s.part1[0].b};
            }""")
            results.append(("새로고침 후 유지", persist))
            page.screenshot(path=os.path.join(OUT, "02-reload.png"), full_page=False)

            # --- 기능 6: 오프라인 재실행 ---
            ctx.set_offline(True)
            try:
                r2 = page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(800)
                off = page.evaluate("""() => ({
                  title: document.title,
                  hasState: !!window.cpick,
                  part1: window.cpick ? window.cpick.state().part1.length : -1,
                  text: document.body.innerText.slice(0, 40)
                })""")
                results.append(("오프라인 로드", {"status": r2.status if r2 else None, **off}))
                page.screenshot(path=os.path.join(OUT, "03-offline.png"), full_page=False)
            except Exception as e:
                results.append(("오프라인 로드", f"실패: {e}"))
            ctx.set_offline(False)

            # --- 데스크톱 화면 ---
            page2 = ctx.new_page()
            page2.set_viewport_size({"width": 1280, "height": 900})
            page2.goto(url, wait_until="networkidle")
            page2.wait_for_timeout(600)
            page2.screenshot(path=os.path.join(OUT, "04-desktop.png"), full_page=False)

            # 설치 프롬프트 가능 여부 (beforeinstallprompt 는 헤드리스에서 생략될 수 있음)
            audit = page2.evaluate("() => 'serviceWorker' in navigator && navigator.serviceWorker.controller !== null")
            results.append(("SW 컨트롤러(데스크톱)", audit))

            browser.close()
    finally:
        httpd.shutdown()

    print("=== 결과 ===")
    for k, v in results:
        print(f"- {k}: {json.dumps(v, ensure_ascii=False)}")
    print("=== 콘솔 에러 ===")
    for e in console_errors:
        print(" *", e)
    print("=== 페이지 에러 ===")
    for e in page_errors:
        print(" *", e)
    print("=== 실패 요청 ===")
    for e in failed:
        print(" *", e)
    print(f"요약: 콘솔에러 {len(console_errors)} · 페이지에러 {len(page_errors)} · 실패요청 {len(failed)}")


if __name__ == "__main__":
    main()
