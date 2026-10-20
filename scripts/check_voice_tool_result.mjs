/** Actual SDK full-payload shape guards; isolated fixture proof, no live claim. */
import assert from 'node:assert/strict';import {build} from 'esbuild';import {createHash} from 'node:crypto';import {readFile,writeFile,mkdir} from 'node:fs/promises';import{resolve,dirname}from'node:path';import{fileURLToPath}from'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),source='src/components/agent/voice-tool-result.ts';
const b=await build({absWorkingDir:root,entryPoints:[source],bundle:true,platform:'node',format:'esm',write:false,logLevel:'silent'});const {voiceToolRecommendation:parse}=await import('data:text/javascript;base64,'+Buffer.from(b.outputFiles[0].text).toString('base64'));
let count=0;const check={equal(...x){assert.equal(...x);count++},deepEqual(...x){assert.deepEqual(...x);count++}};let failure;
try{
 const context={location:{lat:51.12,lon:71.43,label:'Байтерек'},language:'ru',duration_minutes:60,group_size:1,accessible:false,indoor:false,airport_transfer_minutes:null,interests:[],starts_at:'2026-10-19T14:00:00+05:00'};
 const result={message:'План рядом.',recommendations:[{id:'sourced-id',lat:51.121,lon:71.431}],route:{coordinates:[[71.43,51.12],[71.431,51.121]],total_minutes:25},context:{},conversation:{duration_minutes:30}};
 const event={tool_name:'recommend_city_walk',is_error:false,is_called:true,full_tool_result:JSON.stringify(result)},snapshot=JSON.stringify(context);
 const accepted=parse(event,snapshot,snapshot);check.deepEqual(accepted.result,result);check.deepEqual(accepted.context,context);check.equal(JSON.parse(accepted.nextContext).duration_minutes,30);
 check.equal(parse({...event,is_error:true},snapshot,snapshot),undefined);check.equal(parse({...event,truncated:true},snapshot,snapshot),undefined);check.equal(parse({...event,tool_name:'different_tool'},snapshot,snapshot),undefined);check.equal(parse({...event,full_tool_result:'{invalid'},snapshot,snapshot),undefined);
 check.equal(parse(event,snapshot,JSON.stringify({...context,duration_minutes:45})),undefined);check.equal(parse(event,snapshot,JSON.stringify({...context,language:'en'})),undefined);
 check.equal(parse({...event,full_tool_result:JSON.stringify({...result,route:{...result.route,coordinates:[[72,52]]}})},snapshot,snapshot),undefined);
 check.equal(parse({...event,full_tool_result:JSON.stringify({...result,recommendations:[{id:'bad',lat:null,lon:71.4}]})},snapshot,snapshot),undefined);
 check.equal(parse({...event,full_tool_result:JSON.stringify({...result,message:undefined})},snapshot,snapshot),undefined);
 check.deepEqual(parse(event,snapshot,JSON.stringify({...context,remember:false,memory_generation:4})).result,result);
 const next=JSON.stringify({...context,duration_minutes:30});check.deepEqual(parse(event,accepted.nextContext,next).result,result);
}catch(e){failure=e}
const report={checked_at:new Date().toISOString(),command:'node scripts/check_voice_tool_result.mjs',passed:!failure,assertions_passed:count,scope:'Bundled production full-payload decoder with SDK-shaped fixtures. Provider event subscription and live connection verified separately.',coverage:['Exact recommend_city_walk full_tool_result event','Origin/current-context and known result shape guards','Error/truncated/malformed rejection','No privacy-state rollback','Canonical context across consecutive voice plans'],source_sha256:{[source]:createHash('sha256').update(await readFile(resolve(root,source))).digest('hex')},...(failure?{error:String(failure.message||failure)}:{})};await mkdir(resolve(root,'artifacts'),{recursive:true});await writeFile(resolve(root,'artifacts/voice-tool-result-verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));if(failure)throw failure;
