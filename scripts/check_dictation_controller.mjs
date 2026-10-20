/** Controlled microphone/transport lifecycle proof; no live speech claim. */
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {createHash} from 'node:crypto';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const source='src/components/agent/dictation-controller.ts';
const bundled=await build({absWorkingDir:root,entryPoints:[source],bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});
const {DictationController}=await import('data:text/javascript;base64,'+Buffer.from(bundled.outputFiles[0].text).toString('base64'));
let count=0;const check={equal(...x){assert.equal(...x);count++},deepEqual(...x){assert.deepEqual(...x);count++}};
const original={navigator:Object.getOwnPropertyDescriptor(globalThis,'navigator'),MediaRecorder:globalThis.MediaRecorder,fetch:globalThis.fetch,setTimeout:globalThis.setTimeout,clearTimeout:globalThis.clearTimeout,setInterval:globalThis.setInterval,clearInterval:globalThis.clearInterval};
let permission,fetcher,recorders=[],timers=new Map(),timerId=0,bytes=10;
class Recorder {
 static isTypeSupported(type){return type==='audio/webm;codecs=opus'}
 constructor(stream,options){this.stream=stream;this.mimeType=options?.mimeType||'audio/webm';this.state='inactive';recorders.push(this)}
 start(){this.state='recording'}
 stop(){this.state='inactive';queueMicrotask(()=>{this.ondataavailable?.({data:new Blob([new Uint8Array(bytes)],{type:this.mimeType})});this.onstop?.()})}
}
const stream=()=>{const track={stops:0,stop(){this.stops++}};return{track,getTracks:()=>[track]}};
const flush=async()=>{await new Promise(r=>original.setTimeout(r,0));await new Promise(r=>original.setTimeout(r,0))};
let failure;
try{
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia:()=>permission()}}});
 globalThis.MediaRecorder=Recorder;
 globalThis.fetch=(...x)=>fetcher(...x);
 globalThis.setTimeout=(callback,delay)=>{const id=++timerId;timers.set(id,{callback,delay});return id};globalThis.clearTimeout=id=>timers.delete(id);
 globalThis.setInterval=(callback,delay)=>{const id=++timerId;timers.set(id,{callback,delay,interval:true});return id};globalThis.clearInterval=id=>timers.delete(id);
 function harness(){const h={active:true,states:[],errors:[],transcripts:[],seconds:[]};h.controller=new DictationController({active:()=>h.active,onState:s=>h.states.push(s),onSeconds:s=>h.seconds.push(s),onError:(...e)=>h.errors.push(e),onTranscript:t=>h.transcripts.push(t)});return h}
 let calls=[];let mic=stream();permission=async()=>mic;fetcher=async(url,init)=>{calls.push({url,init});return Response.json({text:'  Кофе рядом  '})};
 let h=harness();check.equal(recorders.length,0);await h.controller.start('ru');check.equal(h.states.at(-1),'recording');check.equal(recorders.at(-1).mimeType,'audio/webm;codecs=opus');
 h.controller.stop();check.equal(mic.track.stops,1);await flush();check.equal(calls[0].url,'/api/voice/transcribe');check.equal(calls[0].init.body.get('language'),'ru');check.equal(calls[0].init.body.get('file').size,10);check.deepEqual(h.transcripts,['Кофе рядом']);check.equal(timers.size,0);
 // Permission can resolve after a user closes the dialog.
 let resolvePermission;mic=stream();permission=()=>new Promise(r=>resolvePermission=r);h=harness();const pending=h.controller.start('kk');h.active=false;h.controller.cancel();resolvePermission(mic);await pending;check.equal(mic.track.stops,1);check.equal(calls.length,1);check.equal(h.transcripts.length,0);
 // A late transcription cannot update a closed or cancelled dialog.
 mic=stream();permission=async()=>mic;let respond;fetcher=async(url,init)=>{calls.push({url,init});return new Promise(r=>respond=r)};h=harness();await h.controller.start('kk');h.controller.stop();await flush();const request=calls.at(-1);h.controller.cancel();check.equal(request.init.signal.aborted,true);respond(Response.json({text:'Кеш жауап'}));await flush();check.equal(h.transcripts.length,0);check.equal(mic.track.stops,1);
 // The real 60-second deadline stops the recorder and releases its track.
 mic=stream();permission=async()=>mic;fetcher=async()=>Response.json({text:'Таймер'});h=harness();await h.controller.start('kk');const deadline=[...timers.values()].find(t=>t.delay===60000);check.equal(!!deadline,true);deadline.callback();await flush();check.equal(mic.track.stops,1);check.deepEqual(h.transcripts,['Таймер']);check.equal(timers.size,0);
 permission=async()=>{throw new DOMException('Denied','NotAllowedError')};h=harness();await h.controller.start('en');check.equal(h.errors.at(-1)[0],'permission');check.equal(h.states.at(-1),'idle');
 mic=stream();permission=async()=>mic;h=harness();await h.controller.start('en');recorders.at(-1).onerror();await flush();check.equal(mic.track.stops,1);check.equal(h.errors.at(-1)[0],'failed');check.equal(timers.size,0);
 mic=stream();h=harness();await h.controller.start('en');recorders.at(-1).ondataavailable({data:new Blob([new Uint8Array(8*1024*1024+1)])});await flush();check.equal(h.errors.at(-1)[0],'large');check.equal(mic.track.stops,1);check.equal(timers.size,0);
 mic=stream();bytes=0;h=harness();await h.controller.start('en');h.controller.stop();await flush();check.equal(h.errors.at(-1)[0],'empty');check.equal(h.transcripts.length,0);check.equal(mic.track.stops,1);bytes=10;
 mic=stream();fetcher=async()=>Response.json({detail:'Provider unavailable'},{status:502});h=harness();await h.controller.start('en');h.controller.stop();await flush();check.equal(h.errors.at(-1)[0],'failed');check.equal(h.errors.at(-1)[1],'Provider unavailable');check.equal(mic.track.stops,1);
 globalThis.MediaRecorder=undefined;h=harness();await h.controller.start('en');check.equal(h.errors.at(-1)[0],'unsupported');check.equal(timers.size,0);
}catch(error){failure=error}finally{
 if(original.navigator)Object.defineProperty(globalThis,'navigator',original.navigator);else delete globalThis.navigator;
 Object.assign(globalThis,{MediaRecorder:original.MediaRecorder,fetch:original.fetch,setTimeout:original.setTimeout,clearTimeout:original.clearTimeout,setInterval:original.setInterval,clearInterval:original.clearInterval});
}
const report={checked_at:new Date().toISOString(),command:'node scripts/check_dictation_controller.mjs',passed:!failure,assertions_passed:count,scope:'Controlled MediaRecorder/getUserMedia and HTTP fixtures exercise the bundled production controller; actual Alem speech/ElevenLabs connection verified separately.',coverage:['Explicit microphone start','MIME negotiation and multipart language/file','Stop releases all tracks before transcription','Close while permission pending','Abort and suppress late transcription','60-second deadline','Permission denial, recorder error, empty audio, 8MB limit, HTTP error','Timer/track cleanup'],source_sha256:{[source]:createHash('sha256').update(await readFile(resolve(root,source))).digest('hex')},...(failure?{error:String(failure.message||failure)}:{})};
await mkdir(resolve(root,'artifacts'),{recursive:true});await writeFile(resolve(root,'artifacts/dictation-controller-verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));if(failure)throw failure;
