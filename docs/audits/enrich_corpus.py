import os,csv,urllib.request,urllib.parse,json,time
key=os.environ["OPENALEX_API_KEY"]
rows=list(csv.DictReader(open("riparian_methods_corpus.csv")))
dois=[r["doi"].strip().lower() for r in rows if r.get("doi","").strip()]
# map doi -> oa info
info={}
def norm(d): return d.replace("https://doi.org/","").strip().lower()
for i in range(0,len(dois),50):
    batch=dois[i:i+50]
    flt="doi:"+"|".join(batch)
    url="https://api.openalex.org/works?"+urllib.parse.urlencode({"filter":flt,"per-page":50,"api_key":key,"select":"doi,open_access,best_oa_location,primary_location,id"})
    req=urllib.request.Request(url,headers={"User-Agent":"python-urllib"})
    try:
        d=json.load(urllib.request.urlopen(req,timeout=90))
    except Exception as e:
        print("batch",i,"FAIL",e); continue
    for w in d["results"]:
        doi=norm(w.get("doi") or "")
        oa=w.get("open_access",{}) or {}; bl=w.get("best_oa_location") or {}; pl=w.get("primary_location") or {}
        info[doi]={"is_oa":oa.get("is_oa"),
                   "oa_pdf_url":(bl.get("pdf_url") or oa.get("oa_url") or ""),
                   "landing":(bl.get("landing_page_url") or pl.get("landing_page_url") or ""),
                   "openalex_url":(w.get("id") or "")}
    print("batch",i,"got",len(d["results"]),"total mapped",len(info),flush=True)
    time.sleep(0.3)
# write enriched
out_cols=list(rows[0].keys())+["doi_url","oa_pdf_url","landing_url","openalex_url","is_oa"]
n_pdf=0;n_oa=0
for r in rows:
    doi=norm(r.get("doi",""))
    r["doi_url"]="https://doi.org/"+doi if doi else ""
    m=info.get(doi,{})
    r["oa_pdf_url"]=m.get("oa_pdf_url","") or ""
    r["landing_url"]=m.get("landing","") or ""
    r["openalex_url"]=m.get("openalex_url","") or ""
    r["is_oa"]=m.get("is_oa","")
    if r["oa_pdf_url"]: n_pdf+=1
    if m.get("is_oa"): n_oa+=1
w=csv.DictWriter(open("riparian_methods_corpus_linked.csv","w",newline=""),fieldnames=out_cols)
w.writeheader(); w.writerows(rows)
print(f"DONE rows {len(rows)} | with DOI-url {sum(1 for r in rows if r['doi_url'])} | is_oa {n_oa} | with OA-PDF {n_pdf}",flush=True)
