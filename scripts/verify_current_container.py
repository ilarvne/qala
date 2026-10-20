#!/usr/bin/env python3
"""Build and independently smoke-test this exact source/data in Docker.

Creates one uniquely named, network-isolated container. No host ports, volumes,
dotenv files, provider credentials, external requests or user-container changes.
The built image remains for review; only this script's own container is removed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/container-verification-current.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_hashes() -> dict:
    paths = [ROOT / name for name in ("Dockerfile", ".dockerignore", "requirements.lock.txt", "package.json", "package-lock.json", "index.html", "vite.config.ts", "components.json")]
    paths += list(ROOT.glob("tsconfig*.json"))
    for folder in ("backend", "data", "src", "public"):
        paths += [path for path in (ROOT / folder).rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"]
    return {str(path.relative_to(ROOT)): sha(path) for path in sorted(set(paths))}


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = "qala-verify-current-" + stamp.lower()
    image = "qala:verify-current-" + stamp.lower()
    log = Path("/tmp") / (name + "-build.log")
    before = input_hashes()
    expected_poi_count = len(json.loads((ROOT / "data/pois.json").read_text())["pois"])
    if OUTPUT.exists():
        shutil.copyfile(OUTPUT, OUTPUT.with_name("container-verification-before-" + stamp.lower() + ".json"))
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "passed": False,
        "method": "Actual Docker build and actual network-isolated container; no mocked results",
        "build": {"image_tag": image, "build_log": str(log)},
        "isolation": {"network": "none", "host_ports_bound": False, "host_volumes_mounted": False,
            "provider_keys_supplied": False, "env_file_supplied": False, "provider_requests": 0,
            "cpus": 1, "memory": "2g", "pids": 128, "capabilities_dropped": "ALL", "no_new_privileges": True},
        "cleanup": {"container_name": name, "removed_own_container": False, "other_services_touched": False},
        "scope": "Current corpus/backend and rebuilt production frontend in the portable hash-retrieval Docker distribution. Russian local grounded planning, exact copied source/data hashes, nonroot execution and actual browser-audio normalization. No live provider, external map/navigation, microphone or phone claim."}
    created = False
    try:
        report["docker_server_version"] = subprocess.check_output(["docker", "version", "--format", "{{.Server.Version}}"], text=True).strip()
        start = time.monotonic()
        with log.open("w") as output:
            build = subprocess.run(["docker", "build", "--progress=plain", "-t", image, "."], cwd=ROOT,
                                   stdout=output, stderr=subprocess.STDOUT, timeout=720)
        report["build"].update(exit_code=build.returncode, duration_seconds=round(time.monotonic() - start, 2), completed=build.returncode == 0)
        if build.returncode:
            raise RuntimeError("Docker build failed; inspect the retained build log")
        report["build"]["image_id"] = subprocess.check_output(["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True).strip()
        text = log.read_text()
        report["build"]["typescript_and_vite_completed"] = "vite" in text and "built in" in text
        transfers = re.findall(r"transferring context: ([^\n]+)", text)
        report["build"]["observed_context_transfer"] = transfers[-1] if transfers else "BuildKit cache; no transfer line"
        runtime_hashes = {key: value for key, value in before.items() if key.startswith(("backend/", "data/")) or key == "requirements.lock.txt"}
        subprocess.run(["docker", "run", "--detach", "--name", name, "--network", "none", "--cpus", "1", "--memory", "2g", "--pids-limit", "128", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--env", "QALA_WEATHER=off", "--env", "QALA_EVENTS=off", "--env", "QALA_LLM_PROVIDER=local", "--env", "QALA_RERANK_PROVIDER=none", "--env", "QALA_EMBEDDINGS=hash", image], stdout=subprocess.DEVNULL, check=True)
        created = True
        code = r'''
import asyncio,hashlib,io,json,os,re,subprocess,time,urllib.request,wave
from pathlib import Path
expected = EXPECTED_HASHES
deadline=time.monotonic()+100
while True:
 try:
  with urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2) as r:
   health=json.load(r)
  break
 except Exception:
  if time.monotonic()>deadline:raise RuntimeError('Container health startup deadline exceeded')
  time.sleep(.3)
assert health['status']=='ok' and health['poi_count']==EXPECTED_POI_COUNT, health
assert os.getuid()==10001
key_names=[key for key in os.environ if key.endswith('_API_KEY') or key in {'ALEMPLUS_EMBED_KEY','ALEMPLUS_RERANK_KEY','ALEMPLUS_STT_KEY','ALEMPLUS_STT_KK_KEY','TWILIO_AUTH_TOKEN','QALA_VOICE_TOOL_SECRET'}]
assert not key_names, 'Provider credential variable names unexpectedly configured'
dotenv=[str(path) for base in ('/app','/home/qala') for path in Path(base).rglob('.env*')]
assert not dotenv, 'Dotenv files present'
actual={key:hashlib.sha256((Path('/app')/key).read_bytes()).hexdigest() for key in expected}
assert actual==expected, 'Image backend/data do not match source snapshot'
dataset=json.loads(Path('/app/data/pois.json').read_text());by_id={p['id']:p for p in dataset['pois']}
body={'message':'Я возле Mega Silk Way, хочу погулять 45 минут','location':{'lat':51.0897,'lon':71.4073,'label':'Mega Silk Way · simulated'},'duration_minutes':45,'language':'ru','starts_at':'2026-10-20T14:00:00+05:00','use_saved_preferences':False}
request=urllib.request.Request('http://127.0.0.1:8000/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
with urllib.request.urlopen(request,timeout=45) as response:
 plan=json.load(response);no_store=response.headers.get('Cache-Control')=='no-store'
items=plan['recommendations'];assert 1<=len(items)<=3
assert plan['context']['language']=='ru' and re.search(r'[А-Яа-яЁё]',plan['message']) and plan['route']['total_minutes']<=45
assert plan['route']['total_minutes']==plan['route']['walk_minutes']+plan['route']['visit_minutes']+plan['route']['buffer_minutes']
for item in items:
 assert item['id'] in by_id
 assert item['source']['url']==by_id[item['id']]['source']['url']
 assert item['name']==by_id[item['id']]['names'].get('ru',by_id[item['id']]['name']) or item['name']==by_id[item['id']]['name']
assert no_store
with urllib.request.urlopen('http://127.0.0.1:8000/',timeout=5) as response:
 html=response.read().decode();assert response.status==200 and 'id="root"' in html
 js=re.search(r'<script[^>]+src="([^"]+\.js)"',html).group(1)
with urllib.request.urlopen('http://127.0.0.1:8000'+js,timeout=5) as response:
 bundle=response.read();assert response.status==200 and len(bundle)>10000
webm=subprocess.check_output(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=0.3','-ac','1','-ar','48000','-c:a','libopus','-f','webm','pipe:1'])
from backend.alemplus import normalize_browser_audio
wav_bytes=asyncio.run(normalize_browser_audio(webm,'audio/webm'))
with wave.open(io.BytesIO(wav_bytes),'rb') as wav:
 audio={'input':'Synthetic 440Hz sine WebM/Opus generated inside container','input_bytes':len(webm),'output':'WAV PCM s16le','output_bytes':len(wav_bytes),'channels':wav.getnchannels(),'sample_rate':wav.getframerate(),'sample_width_bytes':wav.getsampwidth(),'frames':wav.getnframes(),'duration_seconds':wav.getnframes()/wav.getframerate(),'provider_requests':0}
 assert audio['channels']==1 and audio['sample_rate']==16000 and audio['sample_width_bytes']==2 and audio['frames']>4000
print(json.dumps({'uid':os.getuid(),'health':health,'dotenv_files_present':False,'provider_credentials_configured':False,'credential_values_inspected_or_recorded':False,'source_data_hashes_verified':len(actual),'image_source_hashes':actual,'dataset_sha256':actual['data/pois.json'],'chat':{'status':200,'language':'ru','mode':plan.get('mode'),'poi_ids':[i['id'] for i in items],'source_urls':[i['source']['url'] for i in items],'budget_minutes':45,'total_minutes':plan['route']['total_minutes'],'source_grounded':True,'no_store':no_store,'trace_nodes':[t['node'] for t in plan['trace']]},'static_frontend':{'status':200,'root_element_present':True,'asset':js,'asset_bytes':len(bundle),'asset_sha256':hashlib.sha256(bundle).hexdigest()},'audio_normalization':audio,'ffmpeg_version':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0]}))
'''.replace("EXPECTED_HASHES", repr(runtime_hashes)).replace("EXPECTED_POI_COUNT", str(expected_poi_count))
        runtime = subprocess.run(["docker", "exec", "--interactive", name, "python", "-"], input=code, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        report["runtime_exit_code"] = runtime.returncode
        if runtime.returncode:
            # These diagnostic paths contain only assertions/runtime traces, no
            # provider credentials were supplied or inspected by this process.
            diagnostic = Path("/tmp") / (name + "-runtime.log")
            diagnostic.write_text(runtime.stdout + runtime.stderr)
            report["runtime_diagnostic_log"] = str(diagnostic)
            raise RuntimeError("Container runtime verification failed")
        report["runtime_smoke"] = json.loads(runtime.stdout)
        after = input_hashes()
        changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
        report["source_snapshot"] = {"file_count": len(before), "source_files_changed_during_verification": changed,
                                     "source_hashes": before, "copy_matches_local_source_snapshot": True}
        if changed:
            raise RuntimeError("Source inputs changed during build/verification; image verified against the recorded initial snapshot")
        report["passed"] = True
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if created:
            cleanup = subprocess.run(["docker", "rm", "--force", name], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            report["cleanup"]["removed_own_container"] = cleanup.returncode == 0
        report["image_retained"] = report["build"].get("completed", False)
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps({"passed": report["passed"], "image_tag": image, "report": str(OUTPUT), "error": report.get("error"), "removed_own_container": report["cleanup"]["removed_own_container"]}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
