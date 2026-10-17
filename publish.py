"""깐깐팍 인스타 자동 업로드 (Instagram API with Instagram Login)
posts/<YYYY-MM-DD_HHMM>_<이름>/ 폴더에 이미지(01.jpg, 02.jpg …) 또는 video.mp4 + caption.txt 를 넣으면,
예약 시간(한국시간)이 지난 폴더를 찾아 게시하고 published.json 을 남깁니다.
"""
import os, sys, json, time, glob, datetime, urllib.parse, urllib.request

TOKEN = os.environ["IG_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]          # owner/repo
BRANCH = os.environ.get("BRANCH", "main")
DRY = os.environ.get("DRY_RUN", "false").lower() == "true"
API = "https://graph.instagram.com"
KST = datetime.timezone(datetime.timedelta(hours=9))

def call(method, path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    req = urllib.request.Request(url if method == "POST" else url + "?" + data.decode(),
                                 data=data if method == "POST" else None, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise SystemExit(f"API 오류 {e.code} {path}: {body}")

def raw_url(path):
    return f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{urllib.parse.quote(path)}"

def wait_ready(cid, tries=40):
    for _ in range(tries):
        st = call("GET", cid, fields="status_code").get("status_code")
        if st == "FINISHED": return
        if st in ("ERROR", "EXPIRED"): raise SystemExit(f"컨테이너 {cid} 상태 {st}")
        time.sleep(5)
    raise SystemExit(f"컨테이너 {cid} 준비 시간 초과")

def due(folder):
    name = os.path.basename(folder)
    try:
        when = datetime.datetime.strptime(name[:15], "%Y-%m-%d_%H%M").replace(tzinfo=KST)
    except ValueError:
        return False
    return when <= datetime.datetime.now(KST) and not os.path.exists(os.path.join(folder, "published.json"))

def main():
    me = call("GET", "me", fields="user_id,username")
    uid = me["user_id"]
    print(f"계정: @{me.get('username')} ({uid})  DRY_RUN={DRY}")
    targets = sorted(f for f in glob.glob("posts/*") if os.path.isdir(f) and due(f))
    if os.environ.get("FORCE_FOLDER"):
        targets = [os.environ["FORCE_FOLDER"]]
    if not targets:
        print("올릴 게시물 없음"); return
    for folder in targets:
        cap_path = os.path.join(folder, "caption.txt")
        caption = open(cap_path, encoding="utf-8").read().strip() if os.path.exists(cap_path) else ""
        imgs = sorted(glob.glob(os.path.join(folder, "*.jpg")) + glob.glob(os.path.join(folder, "*.jpeg")))
        vids = sorted(glob.glob(os.path.join(folder, "*.mp4")))
        print(f"\n▶ {folder}: 이미지 {len(imgs)}장, 영상 {len(vids)}개")
        if vids:
            c = call("POST", f"{uid}/media", media_type="REELS", video_url=raw_url(vids[0]), caption=caption)
            cid = c["id"]
        elif len(imgs) == 1:
            cid = call("POST", f"{uid}/media", image_url=raw_url(imgs[0]), caption=caption)["id"]
        elif 2 <= len(imgs) <= 10:
            kids = [call("POST", f"{uid}/media", image_url=raw_url(p), is_carousel_item="true")["id"] for p in imgs]
            for k in kids: wait_ready(k)
            cid = call("POST", f"{uid}/media", media_type="CAROUSEL", children=",".join(kids), caption=caption)["id"]
        else:
            print("  ⚠️ 이미지가 없거나 10장 초과 — 건너뜀"); continue
        wait_ready(cid)
        if DRY:
            print(f"  ✅ 시험 실행: 컨테이너 {cid} 준비 완료 (게시는 안 함)"); continue
        res = call("POST", f"{uid}/media_publish", creation_id=cid)
        json.dump({"media_id": res.get("id"), "at": datetime.datetime.now(KST).isoformat()},
                  open(os.path.join(folder, "published.json"), "w"), ensure_ascii=False)
        print(f"  🎉 게시 완료: media {res.get('id')}")

if __name__ == "__main__":
    main()
