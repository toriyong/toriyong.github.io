"""진단용(2차): 정정 전/후 구간과 표 원본 XML 구조 확인."""
import io, os, re, sys, zipfile
sys.path.insert(0, "collect/market")
import requests
import dart_ipo as d
import dart_doc as dd

key = os.environ["DART_API_KEY"].strip()
s = requests.Session()
for name, r in (("영광와이케이엠씨", "20261103000312"), ("엠비디", "20261110000253")):
    blob = s.get(f"{d.API}/document.xml", params={"crtfc_key": key, "rcept_no": r}, timeout=(10, 60)).content
    z = zipfile.ZipFile(io.BytesIO(blob))
    print(f"\n######## {name} files={[(i.filename, i.file_size) for i in z.infolist()]}")
    text = dd.zip_to_text(blob, r)
    for m in re.finditer(r"[^\n]{0,40}정정\s*[전후][^\n]{0,40}", text):
        print(f"MARK @{m.start()}: {m.group(0)!r}")
    for pat in (r"\d+\.\d+%에 해당", r"유통가능[^\n]{0,30}\d+\.\d+%"):
        for m in re.finditer(pat, text):
            print(f"FLOAT @{m.start()}: {text[max(0,m.start()-120):m.end()+20]!r}")
    raw = z.read(z.infolist()[0]).decode("utf-8", "ignore")
    i = raw.find("의무보유확약기간별")
    print("RAWXML:", repr(raw[i:i + 2500]))
