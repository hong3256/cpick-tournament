#!/usr/bin/env python3
"""downloads/cpick-tournament-bracket.html -> index.html (PWA 메타·서비스워커 등록 추가)."""
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(os.path.dirname(HERE), "downloads", "cpick-tournament-bracket.html")
DST = os.path.join(HERE, "index.html")
BASE = "https://hong3256.github.io/cpick-tournament/"

HEAD_BLOCK = """<meta name="color-scheme" content="light">
<!-- PWA -->
<meta name="theme-color" content="#12335f">
<meta name="description" content="C-PICK 피클볼 월례대회 대진표 — 참석자 자동 편성, 점수 입력, 카톡 공유, 이미지 저장">
<meta name="robots" content="noindex, nofollow">
<link rel="manifest" href="manifest.json">
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" href="icon-192.png" type="image/png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="C-PICK 대진표">
<meta name="application-name" content="C-PICK 대진표">
<meta name="format-detection" content="telephone=no">
<link rel="canonical" href="{base}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="C-PICK 대진표">
<meta property="og:title" content="C-PICK 월례대회 대진표">
<meta property="og:description" content="참석자 자동 편성 · 점수 입력 · 카톡 공유 · 이미지 저장">
<meta property="og:url" content="{base}">
<meta property="og:image" content="{base}icon-512.png">
<meta name="twitter:card" content="summary_large_image">
""".format(base=BASE)

SW_BLOCK = """<!-- PWA: 서비스 워커 등록 (오프라인 실행 / 홈 화면 앱) -->
<script>
(function () {
  if (!('serviceWorker' in navigator)) return;
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('./sw.js').then(function (reg) {
      reg.addEventListener && reg.update && reg.update();
    }).catch(function (err) {
      console.warn('[PWA] 서비스 워커 등록 실패:', err);
    });
  });
})();
</script>
</body>
</html>
"""


def main():
    html = open(SRC, encoding="utf-8").read()

    old_head = '<meta name="color-scheme" content="light">\n'
    if old_head not in html:
        raise SystemExit("head anchor not found")
    html = html.replace(old_head, HEAD_BLOCK, 1)

    # viewport-fit=cover (standalone 상태바 아래 여백 확보)
    html = html.replace('<meta name="viewport" content="width=device-width, initial-scale=1">',
                        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">', 1)

    old_tail = "</script>\n</body>\n</html>\n"
    if old_tail not in html:
        raise SystemExit("tail anchor not found")
    html = html.replace(old_tail, "</script>\n" + SW_BLOCK, 1)

    open(DST, "w", encoding="utf-8").write(html)
    print("wrote", DST, len(html), "bytes")


if __name__ == "__main__":
    main()
