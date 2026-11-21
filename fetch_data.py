#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开奖号码数据抓取 —— 供 GitHub Actions 每日自动运行。

抓五个彩种（快乐8、双色球、排列五、大乐透、7星彩），按期号合并去重（最新在前），
输出五份页面可直接消费的 JSON：
  kl8.json  {"updated","latest_issue","data":[[20个数]],"issues":[],"dates":[]}
  ssq.json  {"updated","latest_issue","data":[{"red":[6],"blue":n}],"issues":[],"dates":[]}
  pl5.json  {"updated","latest_issue","data":[{"n":[5]}],"issues":[],"dates":[]}
  dlt.json  {"updated","latest_issue","data":[{"r":[5],"b":[2]}],"issues":[],"dates":[]}
  qxc.json  {"updated","latest_issue","data":[{"n":[7]}],"issues":[],"dates":[]}

数据源：
  福彩（快乐8 / 双色球）：https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice
  体彩（排列五 / 大乐透 / 7星彩）：https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry

任一彩种抓取失败：仍然写入其余彩种，最后以非 0 退出码暴露失败。
"""
import json
import os
import re
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

CWL = ("https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/"
       "findDrawNotice?name=%s&issueCount=100&pageNo=1&pageSize=100&systemType=PC")
SPORT = ("https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
         "?gameNo=%s&provinceId=0&pageSize=100&isVerify=1&pageNo=1")


def get_json(url, referer):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": referer, "Accept": "application/json",
    })
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    return json.loads(raw)


def fetch_cwl(name):
    """福彩：返回 [{"issue","date","red":[..],"blue":str}]"""
    j = get_json(CWL % name, "https://www.cwl.gov.cn/")
    out = []
    for x in (j.get("result") or []):
        issue = str(x.get("code", "")).strip()
        date = str(x.get("date", ""))[:10]
        red = [int(n) for n in str(x.get("red", "")).split(",") if str(n).strip()]
        out.append({"issue": issue, "date": date, "red": red,
                    "blue": str(x.get("blue", "")).strip()})
    return out


def fetch_sport(game):
    """体彩：返回原始 list（字段由各彩种自行解析）"""
    j = get_json(SPORT % game, "https://www.sporttery.cn/")
    if not j.get("success"):
        raise RuntimeError("sporttery success=%r" % j.get("success"))
    return j.get("value", {}).get("list") or []


# ---------- 各彩种：抓新数据 ----------

def grab_kl8():
    recs = []
    for x in fetch_cwl("kl8"):
        nums = [int(n) for n in x["red"]]
        if re.fullmatch(r"20\d{5}", x["issue"]) and len(nums) == 20 and all(1 <= n <= 80 for n in nums):
            recs.append({"issue": x["issue"], "date": x["date"], "numbers": nums})
    return recs


def grab_ssq():
    recs = []
    for x in fetch_cwl("ssq"):
        blue = int(x["blue"]) if x["blue"].isdigit() else -1
        if (re.fullmatch(r"20\d{5}", x["issue"]) and len(x["red"]) == 6
                and all(1 <= n <= 33 for n in x["red"]) and 1 <= blue <= 16):
            recs.append({"issue": x["issue"], "date": x["date"], "red": x["red"], "blue": blue})
    return recs


def grab_pl5():
    recs = []
    for x in fetch_sport("350133"):
        nums = re.findall(r"\d", x.get("lotteryDrawResult", "") or "")
        if len(nums) == 5:
            recs.append({"issue": str(x.get("lotteryDrawNum", "")),
                         "date": (x.get("lotteryDrawTime", "") or "")[:10],
                         "nums": [int(n) for n in nums]})
    return recs


def grab_dlt():
    recs = []
    for x in fetch_sport("85"):
        draw = re.findall(r"\d{1,2}", x.get("lotteryDrawResult", "") or "")
        if len(draw) >= 7:
            red = [int(n) for n in draw[:5]]
            blue = [int(n) for n in draw[5:7]]
            if all(1 <= n <= 35 for n in red) and all(1 <= n <= 12 for n in blue):
                recs.append({"issue": str(x.get("lotteryDrawNum", "")),
                             "date": (x.get("lotteryDrawTime", "") or "")[:10],
                             "red": red, "blue": blue})
    return recs


def grab_qxc():
    recs = []
    for x in fetch_sport("04"):
        nums = re.findall(r"\d+", x.get("lotteryDrawResult", "") or "")
        if len(nums) != 7:
            continue
        front = [int(n) for n in nums[:6]]
        back = int(nums[6])
        if any(n > 9 for n in front) or back > 14:
            continue
        recs.append({"issue": str(x.get("lotteryDrawNum", "")),
                     "date": (x.get("lotteryDrawTime", "") or "")[:10],
                     "nums": front + [back]})
    return recs


# ---------- payload <-> records ----------

def load_payload(fn):
    p = os.path.join(BASE, fn)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def merge_records(old, fresh):
    seen = {r["issue"]: r for r in old}
    for r in fresh:
        seen.setdefault(r["issue"], r)
    merged = list(seen.values())
    merged.sort(key=lambda r: r["issue"], reverse=True)
    return merged


def payload_to_records(kind, payload):
    if not payload:
        return []
    recs = []
    for i, d in enumerate(payload.get("data") or []):
        issue = payload["issues"][i] if i < len(payload.get("issues", [])) else ""
        date = payload["dates"][i] if i < len(payload.get("dates", [])) else ""
        if kind == "kl8":
            recs.append({"issue": issue, "date": date, "numbers": d})
        elif kind == "ssq":
            recs.append({"issue": issue, "date": date, "red": d["red"], "blue": d["blue"]})
        elif kind == "pl5":
            recs.append({"issue": issue, "date": date, "nums": d["n"]})
        elif kind == "dlt":
            recs.append({"issue": issue, "date": date, "red": d["r"], "blue": d["b"]})
        elif kind == "qxc":
            recs.append({"issue": issue, "date": date, "nums": d["n"]})
    return recs


def records_to_payload(kind, recs):
    if kind == "kl8":
        data = [r["numbers"] for r in recs]
    elif kind == "ssq":
        data = [{"red": r["red"], "blue": r["blue"]} for r in recs]
    elif kind == "pl5":
        data = [{"n": r["nums"]} for r in recs]
    elif kind == "dlt":
        data = [{"r": r["red"], "b": r["blue"]} for r in recs]
    else:
        data = [{"n": r["nums"]} for r in recs]
    return {
        "updated": recs[0]["date"] if recs else "",
        "latest_issue": recs[0]["issue"] if recs else "",
        "data": data,
        "issues": [r["issue"] for r in recs],
        "dates": [r.get("date", "") for r in recs],
    }


JOBS = [
    ("kl8", "kl8.json", grab_kl8),
    ("ssq", "ssq.json", grab_ssq),
    ("pl5", "pl5.json", grab_pl5),
    ("dlt", "dlt.json", grab_dlt),
    ("qxc", "qxc.json", grab_qxc),
]


def main():
    failed = []
    for kind, fn, grab in JOBS:
        try:
            fresh = grab()
            if not fresh:
                raise RuntimeError("抓取结果为空")
            old = payload_to_records(kind, load_payload(fn))
            recs = merge_records(old, fresh)
            payload = records_to_payload(kind, recs)
            out = os.path.join(BASE, fn)
            if old and payload == load_payload(fn):
                print("%-4s unchanged %s (%d 期)" % (kind, payload["latest_issue"], len(recs)))
                continue
            with open(out, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            print("%-4s updated %s %s (%d 期)" % (kind, payload["latest_issue"],
                                                 payload["updated"], len(recs)))
        except Exception as e:
            failed.append(kind)
            print("%-4s FAILED: %r" % (kind, e))
        time.sleep(1)

    if failed:
        print("抓取失败彩种: %s" % ",".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
