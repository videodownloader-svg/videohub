#!/usr/bin/env python3
import os,sys,subprocess,json,re,shutil,uuid,signal,urllib.request
from pathlib import Path
def ep(p,i=None):
    i=i or p
    try:__import__(p)
    except:subprocess.check_call([sys.executable,"-m","pip","install","-q",i])
ep("flask");ep("yt_dlp","yt-dlp")
if not shutil.which("yt-dlp"):subprocess.call([sys.executable,"-m","pip","install","-q","-U","yt-dlp"])
from flask import Flask,render_template,request,Response,jsonify,send_from_directory

BD=Path(__file__).parent.resolve()
TD=BD/"templates";TD.mkdir(exist_ok=True)
sh=Path.home()/"storage"/"downloads"
DD=(sh/"VideoDownloader") if sh.exists() else (BD/"downloads")
DD.mkdir(parents=True,exist_ok=True)
HF=BD/"history.json"
RF=BD/"ratings.json"
print(f"📁 Download Folder: {DD}")
ACT={}

def lh():
    if HF.exists():
        try:return json.loads(HF.read_text(encoding='utf-8'))
        except:return {}
    return {}
def sh_(h):
    try:HF.write_text(json.dumps(h,indent=2,ensure_ascii=False),encoding='utf-8')
    except:pass
def lr():
    if RF.exists():
        try:return json.loads(RF.read_text(encoding='utf-8'))
        except:return {"ratings":{},"votes":{}}
    return {"ratings":{},"votes":{}}
def sr_(r):
    try:RF.write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')
    except:pass

app=Flask(__name__)
def sani(u):
    if not u or not re.match(r'^https?://',u):return None
    return u
def get_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'

@app.route('/')
def index():return render_template('index.html')

@app.route('/thumb')
def thumb():
    url=request.args.get('url','')
    if not url or not url.startswith('http'):return '',400
    try:
        req=urllib.request.Request(url,headers={
            'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Accept':'image/webp,image/apng,image/*,*/*;q=0.8',
        })
        with urllib.request.urlopen(req,timeout=15) as r:
            data=r.read()
            ct=r.headers.get('Content-Type','image/jpeg')
            if not ct.startswith('image/'):ct='image/jpeg'
            return Response(data,mimetype=ct,headers={'Cache-Control':'public,max-age=86400'})
    except:return '',404

@app.route('/info',methods=['POST'])
def info():
    u=sani((request.form.get('url') or '').strip())
    if not u:return jsonify({'error':'Invalid URL.'})
    try:
        r=subprocess.run(['yt-dlp','-J','--no-warnings','--no-playlist',u],capture_output=True,text=True,timeout=45)
        if r.returncode!=0:return jsonify({'error':'Could not fetch info.'})
        d=json.loads(r.stdout)
        vid=d.get('id','')
        h=lh();done=h.get(vid,[])
        fmts=[];seen=set()
        raw=d.get('formats',[]);raw.sort(key=lambda x:x.get('height',0) or 0,reverse=True)
        dur=d.get('duration',0)
        for f in raw:
            if f.get('vcodec')!='none' and f.get('height'):
                ht=f.get('height')
                if ht not in seen:
                    seen.add(ht)
                    fs=f.get('filesize') or f.get('filesize_approx')
                    sz="Unknown"
                    if fs and fs>0:sz=f"~{fs/(1024*1024):.1f} MB"
                    elif dur:
                        tbr=f.get('tbr') or f.get('vbr')
                        if tbr and tbr>0:sz=f"~{(tbr*1000/8)*dur/(1024*1024):.1f} MB"
                    v=str(ht)
                    fmts.append({'label':f'{ht}p','value':v,'size':sz,'downloaded':v in done})
        av='audio'
        fmts.append({'label':'MP3','value':av,'size':'Audio Only','downloaded':av in done})
        thumb=d.get('thumbnail','')
        thumbnails=d.get('thumbnails',[])
        candidates=[]
        if thumb:candidates.append(thumb)
        for t in reversed(thumbnails):
            if t.get('url') and t['url'] not in candidates:
                candidates.append(t['url'])
        return jsonify({'title':d.get('title','Unknown'),'thumbnail':thumb,'thumbnails':candidates[:5],'duration':d.get('duration_string') or 'Unknown','video_id':vid,'formats':fmts})
    except subprocess.TimeoutExpired:return jsonify({'error':'Timeout.'})
    except Exception as e:return jsonify({'error':str(e)})

@app.route('/download',methods=['POST'])
def dl():
    u=sani((request.form.get('url') or '').strip())
    q=request.form.get('quality','1080');did=request.form.get('id',str(uuid.uuid4()))
    vid=request.form.get('vid_id','')
    if not u:return Response(f"data: {json.dumps({'error':'Invalid URL'})}\n\n",mimetype='text/event-stream')
    if q=='audio':sel='bestaudio/best'
    elif q=='16k':sel='bestvideo[height<=?8640]+bestaudio/best[height<=?8640]'
    elif q=='8k':sel='bestvideo[height<=?4320]+bestaudio/best[height<=?4320]'
    elif q=='4k':sel='bestvideo[height<=?2160]+bestaudio/best[height<=?2160]'
    else:sel=f'bestvideo[height<={q}]+bestaudio/best[height<={q}]'
    o=str(DD/'%(title).150s.%(ext)s')
    c=['yt-dlp','-f',sel,'-o',o,'--no-playlist','--newline','--no-warnings','--progress','--restrict-filenames','--no-mtime',u]
    if q=='audio':c+=['-x','--audio-format','mp3','--audio-quality','0']
    else:c+=['--merge-output-format','mp4']
    def gen():
        ok=False
        try:
            p=subprocess.Popen(c,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,preexec_fn=os.setsid)
            ACT[did]=p
            for l in iter(p.stdout.readline,''):yield f"data: {json.dumps({'line':l.rstrip()})}\n\n"
            p.stdout.close();p.wait()
            ok=(p.returncode==0)
        except Exception as e:yield f"data: {json.dumps({'error':str(e)})}\n\n"
        finally:ACT.pop(did,None)
        if ok and vid:
            try:
                h=lh()
                if vid not in h:h[vid]=[]
                if q not in h[vid]:h[vid].append(q)
                sh_(h)
            except:pass
        yield f"data: {json.dumps({'done':True})}\n\n"
    return Response(gen(),mimetype='text/event-stream',headers={'Cache-Control':'no-cache'})

@app.route('/cancel/<did>',methods=['POST'])
def cn(did):
    p=ACT.get(did)
    if p:
        try:os.killpg(os.getpgid(p.pid),signal.SIGTERM);return jsonify({'ok':True})
        except Exception as e:return jsonify({'ok':False,'error':str(e)}),500
    return jsonify({'ok':False}),404

@app.route('/files')
def fl():
    it=[]
    try:
        for f in sorted(DD.iterdir(),key=lambda x:x.stat().st_mtime if x.is_file() else 0,reverse=True):
            if f.is_file() and f.suffix.lower() in ['.mp4','.mkv','.webm','.mp3','.m4a','.mov','.avi']:
                st=f.stat()
                it.append({'name':f.name,'size':st.st_size,'mtime':int(st.st_mtime),'url':f'/download_file/{f.name}'})
    except:pass
    return jsonify(it)

@app.route('/download_file/<path:f>')
def df(f):return send_from_directory(DD,f,as_attachment=True)

@app.route('/delete/<path:f>',methods=['DELETE'])
def dlf(f):
    try:
        p=DD/f
        if p.exists() and p.is_file():p.unlink();return jsonify({'ok':True})
    except Exception as e:return jsonify({'ok':False,'error':str(e)}),500
    return jsonify({'ok':False}),404

@app.route('/rating',methods=['GET'])
def get_rating():
    r=lr()
    ratings=r.get('ratings',{});votes=r.get('votes',{})
    all_vals=list(ratings.values());total=len(all_vals)
    avg=round(sum(all_vals)/total,1) if total>0 else 0
    my_ip=get_ip();my_vote=votes.get(my_ip,0)
    dist={1:0,2:0,3:0,4:0,5:0}
    for v in all_vals:
        if v in dist:dist[v]+=1
    return jsonify({'average':avg,'total':total,'distribution':dist,'my_vote':my_vote,'can_vote':my_vote==0})

@app.route('/rating',methods=['POST'])
def post_rating():
    try:star=int(request.form.get('stars',0))
    except:star=0
    if star<1 or star>5:return jsonify({'ok':False,'error':'Invalid rating'}),400
    r=lr();ratings=r.get('ratings',{});votes=r.get('votes',{})
    ip=get_ip()
    if ip in votes:return jsonify({'ok':False,'error':'You have already rated','my_vote':votes[ip]}),200
    vid=str(uuid.uuid4())
    ratings[vid]=star;votes[ip]=star
    r['ratings']=ratings;r['votes']=votes
    sr_(r)
    all_vals=list(ratings.values());total=len(all_vals)
    avg=round(sum(all_vals)/total,1) if total>0 else 0
    dist={1:0,2:0,3:0,4:0,5:0}
    for v in all_vals:
        if v in dist:dist[v]+=1
    return jsonify({'ok':True,'average':avg,'total':total,'distribution':dist,'my_vote':star})

if __name__=='__main__':
    cert=BD/"cert.pem";key=BD/"key.pem"
    print("="*55)
    print("🎬 VideoDL Pro — Created by Mahedi Hassan Anik")
    if cert.exists() and key.exists():
        print("🔒 HTTPS Enabled (Secure Connection)")
        print(f"🌐 https://localhost:5000")
        print("⚠️  Browser will show 'Not Secure' warning - tap 'Advanced' → 'Proceed'")
        print("="*55)
        app.run(host='0.0.0.0',port=5000,debug=False,threaded=True,ssl_context=(str(cert),str(key)))
    else:
        print("⚠️  SSL cert not found! Run:")
        print("    openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 3650 -nodes -subj '/CN=localhost'")
        print(f"🌐 http://localhost:5000 (Auto-paste will NOT work)")
        print("="*55)
        app.run(host='0.0.0.0',port=5000,debug=False,threaded=True)
