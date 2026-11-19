#!/usr/bin/env python3
"""배포 URL 실검증: https://hong3256.github.io/cpick-tournament/"""
import json
import os
from playwright.sync_api import sync_playwright

URL = "https://hong3256.github.io/cpick-tournament/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(OUT, exist_ok=True)

NAMES = [("강민수", "남"), ("고은비", "여"), ("권도현", "남"), ("나윤아", "여"),
         ("류재현", "남"), ("문소리", "여"), ("배준호", "남"), ("신하늘", "여")]

results = []
console_errors, page_errors, failed = [], [], []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 412, "height": 915}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True, accept_downloads=True,
                                  locale="ko-KR")
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on("requestfailed", lambda r: failed.append(r.url + " :: " + str(r.failure)))

        resp = page.goto(URL, wait_until="networkidle", timeout=60000)
        results.append(("접속", {"status": resp.status, "url": page.url, "title": page.title()}))

        meta = page.evaluate("""() => {
          const g = s => { const e = document.querySelector(s); return e ? (e.content || e.getAttribute('href')) : null; };
          return {
            manifestLink: g('link[rel=manifest]'),
            themeColor: g('meta[name=theme-color]'),
            appleCapable: g('meta[name=apple-mobile-web-app-capable]'),
            appleTitle: g('meta[name=apple-mobile-web-app-title]'),
            viewport: g('meta[name=viewport]'),
            robots: g('meta[name=robots]'),
            swScript: !!Array.from(document.scripts).find(s => s.textContent.includes("serviceWorker.register('./sw.js')"))
          };
        }""")
        results.append(("head 메타", meta))

        man = page.evaluate("""async () => {
          const r = await fetch('manifest.json', {cache:'no-store'});
          const j = await r.json();
          const iconChecks = [];
          for (const i of j.icons) {
            const ir = await fetch(i.src, {cache:'no-store'});
            iconChecks.push(i.src + ' ' + i.sizes + ' ' + i.purpose + ' -> ' + ir.status + ' ' + ir.headers.get('content-type'));
          }
          return {status: r.status, name: j.name, short_name: j.short_name, start_url: j.start_url,
                  display: j.display, bg: j.background_color, theme: j.theme_color, icons: iconChecks};
        }""")
        results.append(("manifest", man))

        swres = page.evaluate("""async () => {
          const r = await fetch('sw.js', {cache:'no-store'});
          return {status: r.status, type: r.headers.get('content-type'), bytes: (await r.text()).length};
        }""")
        results.append(("sw.js", swres))

        page.wait_for_function("() => navigator.serviceWorker && navigator.serviceWorker.controller !== null", timeout=30000)
        sw = page.evaluate("""async () => {
          const reg = await navigator.serviceWorker.ready;
          const keys = await caches.keys();
          const c = await caches.open(keys[0]);
          const cached = (await c.keys()).map(r => new URL(r.url).pathname);
          return {scope: reg.scope, active: reg.active && reg.active.state, caches: keys, cachedCount: cached.length, cached};
        }""")
        results.append(("service worker", sw))

        # 기능 1: 붙여넣기 + 자동 편성
        page.click('[data-act="pasteToggle"]')
        page.fill('[data-paste-box]', "\n".join(f"{n} {g}" for n, g in NAMES))
        page.click('[data-act="replace" ]' if False else '[data-act="pasteReplace"]')
        page.wait_for_timeout(400)
        results.append(("참석자 전체 교체", page.evaluate("() => window.cpick.state().participants.length")))
        page.click('[data-act="generate"]')
        page.wait_for_timeout(600)
        results.append(("자동 편성", page.evaluate("""() => {
          const s = window.cpick.state();
          return {part1: s.part1.length, teams: s.teams.length,
                  rows: document.querySelectorAll('[data-mid]').length,
                  bracket: document.querySelectorAll('[data-bracket] .bmatch').length,
                  rosterC: document.querySelectorAll('[data-roster-c] .rmem').length,
                  rosterB: document.querySelectorAll('[data-roster-b] .rmem').length};
        }""")))
        page.screenshot(path=os.path.join(OUT, "live-01-generated.png"))

        # 기능 2: 점수 입력
        page.fill('input[data-score="p1-0:c"]', "11")
        page.fill('input[data-score="p1-0:b"]', "9")
        page.wait_for_timeout(400)
        results.append(("점수 입력", page.evaluate("""() => ({
          result: document.querySelector('[data-result="p1-0"]').textContent,
          sumC: document.querySelector('[data-sum-c]').textContent,
          sumB: document.querySelector('[data-sum-b]').textContent,
          saved: !!localStorage.getItem('cpick-monthly-bracket-v2')
        })""")))

        # 기능 3: 카톡 공유 텍스트 + 버튼
        results.append(("공유 텍스트", page.evaluate("() => window.cpick.shareText().split('\\n').slice(0,3).join(' / ')")))
        page.click('[data-act="kakaoShare"]')
        page.wait_for_timeout(800)
        results.append(("카톡 버튼", {"title": page.title(), "modal": page.evaluate("() => { const m=document.querySelector('[data-modal]'); return m ? !m.hidden : null; }")}))
        page.keyboard.press("Escape")

        # 기능 4: 이미지 저장
        results.append(("대진표 이미지 blob", page.evaluate("async () => { const b = await window.cpick.cardBlob(); return b ? b.size : 0; }")))
        try:
            with page.expect_download(timeout=20000) as dl:
                page.click('[data-act="saveImage"]')
            d = dl.value
            path = os.path.join(OUT, "live-download.png")
            d.save_as(path)
            results.append(("이미지 저장 다운로드", {"file": d.suggested_filename, "bytes": os.path.getsize(path)}))
        except Exception as e:
            results.append(("이미지 저장 다운로드", f"실패: {str(e)[:200]}"))

        # 기능 5: 새로고침 유지
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(700)
        results.append(("새로고침 후 유지", page.evaluate("() => { const s = window.cpick.state(); return {part1: s.part1.length, c: s.part1[0].c, b: s.part1[0].b}; }")))

        # 기능 6: 오프라인 재접속
        ctx.set_offline(True)
        try:
            r2 = page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)
            results.append(("오프라인 재접속", {"status": r2.status if r2 else None, **page.evaluate("""() => ({
              title: document.title,
              hasApp: !!window.cpick,
              part1: window.cpick ? window.cpick.state().part1.length : -1
            })""")}))
            page.screenshot(path=os.path.join(OUT, "live-02-offline.png"))
        except Exception as e:
            results.append(("오프라인 재접속", f"실패: {str(e)[:200]}"))
        ctx.set_offline(False)

        # 설치 가능성 점검
        page.goto(URL, wait_until="networkidle")
        inst = page.evaluate("""async () => {
          const reg = await navigator.serviceWorker.ready;
          const mf = await (await fetch('manifest.json')).json();
          return {hasManifest: !!document.querySelector('link[rel=manifest]'),
                  iconAny192: mf.icons.some(i => i.sizes === '192x192' && i.purpose === 'any'),
                  iconAny512: mf.icons.some(i => i.sizes === '512x512' && i.purpose === 'any'),
                  maskable: mf.icons.some(i => i.purpose === 'maskable'),
                  displayStandalone: mf.display === 'standalone',
                  swActive: !!reg.active, https: location.protocol === 'https:'};
        }""")
        results.append(("설치 요건", inst))

        page.screenshot(path=os.path.join(OUT, "live-03-mobile.png"))
        page2 = ctx.new_page()
        page2.set_viewport_size({"width": 1280, "height": 900})
        page2.goto(URL, wait_until="networkidle")
        page2.wait_for_timeout(500)
        page2.screenshot(path=os.path.join(OUT, "live-04-desktop.png"))
        browser.close()

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
