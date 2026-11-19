#!/usr/bin/env python3
"""downloads/cpick-apps-script.txt (Code.gs) 로직 검증.

Google 서비스는 최소한으로 흉내 내고(SpreadsheetApp·ContentService·LockService·Utilities)
doGet / doPost 를 실제로 실행해 PIN 검증·저장·응답 형식을 확인한다.
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GS = os.path.join(os.path.dirname(HERE), "downloads", "cpick-apps-script.txt")

HARNESS = r"""
(code) => {
  const CELLS = { A1: '{}', B1: '3256', C1: '← 관리자 PIN', D1: '' };
  const touched = [];
  const sheet = {
    getRange(r) {
      return {
        getValue() { return CELLS[r] === undefined ? '' : CELLS[r]; },
        setValue(v) { CELLS[r] = v; touched.push(r); }
      };
    }
  };
  const ss = { getSheets() { return [sheet]; }, getSheetByName() { return sheet; } };
  const SpreadsheetApp = {
    getActiveSpreadsheet() { return ss; },
    openById() { return ss; },
    flush() { }
  };
  const ContentService = {
    MimeType: { JSON: 'application/json' },
    createTextOutput(text) {
      let mime = 'text/plain';
      return {
        getContent() { return text; },
        getMimeType() { return mime; },
        setMimeType(m) { mime = m; return this; }
      };
    }
  };
  const Utilities = { formatDate() { return '2026-11-19 10:00:00'; } };
  const LockService = {
    getScriptLock() { return { waitLock() { }, releaseLock() { } }; }
  };
  const api = new Function(
    'SpreadsheetApp', 'ContentService', 'Utilities', 'LockService',
    code + '\nreturn { doGet: doGet, doPost: doPost };'
  )(SpreadsheetApp, ContentService, Utilities, LockService);

  const call = (fn, arg) => {
    const out = api[fn](arg);
    return { mime: out.getMimeType(), body: JSON.parse(out.getContent()) };
  };
  const post = (obj) => call('doPost', { postData: { contents: JSON.stringify(obj) } });

  const out = {};
  out.getEmpty = call('doGet', { parameter: {} });
  out.ping = call('doGet', { parameter: { action: 'ping' } });

  out.verifyWrong = post({ action: 'verify_pin', pin: '0000' });
  out.verifyRight = post({ action: 'verify_pin', pin: '3256' });

  out.saveWrongPin = post({ pin: '1111', data: { header: { title: '해킹' } } });
  out.a1AfterWrong = CELLS.A1;

  const data = { header: { title: 'C-PICK 11월', date: '2026-11-21' }, part1: [{ c: '11', b: '9' }] };
  out.saveOk = post({ pin: '3256', data });
  out.a1 = CELLS.A1;
  out.a1Parsed = JSON.parse(CELLS.A1);
  out.d1 = CELLS.D1;
  out.touched = touched.slice();

  out.getAfterSave = call('doGet', { parameter: {} });

  CELLS.B1 = '9988';                       // 시트에서 PIN을 바꾼 경우
  out.oldPinAfterChange = post({ pin: '3256', data });
  out.newPinAfterChange = post({ pin: '9988', data });
  out.pinAsNumber = post({ pin: 9988, data });   // 숫자로 와도 문자 비교

  out.badJson = call('doPost', { postData: { contents: '{not json' } });
  out.noData = post({ pin: '9988' });
  out.pinSetFlag = call('doGet', { parameter: {} }).body.pinSet;
  CELLS.B1 = '';
  out.noPinInSheet = post({ pin: '', data });
  return out;
}
"""


def main():
    code = open(GS, encoding="utf-8").read()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context().new_page()
        page.goto("about:blank")
        r = page.evaluate(HARNESS, code)
        browser.close()

    results = []

    def ok(name, cond, detail=None):
        results.append((bool(cond), name, detail))
        print(("통과  " if cond else "실패  ") + name + ("" if detail is None else " :: " + json.dumps(detail, ensure_ascii=False)))

    ok("doGet: JSON MIME", r["getEmpty"]["mime"] == "application/json", r["getEmpty"]["mime"])
    ok("doGet: ok=true + data + updatedAt 형식",
       r["getEmpty"]["body"].get("ok") is True and "data" in r["getEmpty"]["body"] and "updatedAt" in r["getEmpty"]["body"],
       {k: r["getEmpty"]["body"][k] for k in ("ok", "updatedAt")})
    ok("doGet?action=ping", r["ping"]["body"].get("pong") is True, r["ping"]["body"])
    ok("오답 PIN → PIN_MISMATCH", r["verifyWrong"]["body"].get("error") == "PIN_MISMATCH", r["verifyWrong"]["body"])
    ok("정답 PIN 3256 → verified", r["verifyRight"]["body"].get("ok") is True, r["verifyRight"]["body"])
    ok("오답 PIN 저장 요청 차단", r["saveWrongPin"]["body"].get("error") == "PIN_MISMATCH", r["saveWrongPin"]["body"])
    ok("오답 PIN 일 때 A1 그대로", r["a1AfterWrong"] == "{}", r["a1AfterWrong"])
    ok("정답 PIN 저장 → ok + updatedAt",
       r["saveOk"]["body"].get("ok") is True and r["saveOk"]["body"].get("updatedAt") == "2026-11-19 10:00:00",
       r["saveOk"]["body"])
    ok("A1에 JSON 저장", r["a1Parsed"].get("header", {}).get("title") == "C-PICK 11월" and
       r["a1Parsed"].get("part1", [{}])[0].get("c") == "11")
    ok("D1에 저장 시각 기록", r["d1"] == "2026-11-19 10:00:00", r["d1"])
    ok("A1·D1만 건드림", r["touched"] == ["A1", "D1"] or set(r["touched"]) <= {"A1", "D1"}, r["touched"])
    ok("저장 후 doGet 이 같은 데이터 반환",
       r["getAfterSave"]["body"]["data"]["header"]["title"] == "C-PICK 11월",
       r["getAfterSave"]["body"]["data"]["header"]["title"])
    ok("시트 PIN 변경 후 옛 PIN 거부", r["oldPinAfterChange"]["body"].get("error") == "PIN_MISMATCH",
       r["oldPinAfterChange"]["body"])
    ok("시트 PIN 변경 후 새 PIN 통과", r["newPinAfterChange"]["body"].get("ok") is True, r["newPinAfterChange"]["body"])
    ok("숫자로 온 PIN도 비교", r["pinAsNumber"]["body"].get("ok") is True, r["pinAsNumber"]["body"])
    ok("깨진 JSON → BAD_JSON", r["badJson"]["body"].get("error") == "BAD_JSON", r["badJson"]["body"])
    ok("data 없이 저장 요청 → NO_DATA", r["noData"]["body"].get("error") == "NO_DATA", r["noData"]["body"])
    ok("doGet pinSet 플래그", r["pinSetFlag"] is True, r["pinSetFlag"])
    ok("시트에 PIN 없으면 NO_PIN", r["noPinInSheet"]["body"].get("error") == "NO_PIN", r["noPinInSheet"]["body"])

    passed = sum(1 for x in results if x[0])
    print(f"\n=== {passed}/{len(results)} 통과 ===")
    for good, name, detail in results:
        if not good:
            print("  실패:", name, detail)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
