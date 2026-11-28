// Salva as odds (jogo e jogadores) de cada partida do site de apostas.
// Uso: node odds_site.js PASTA slug1 slug2 ...   (slug = final da URL /pt/events/<slug>)
const {chromium}=require('playwright');(async()=>{
const proxy=process.env.HTTPS_PROXY?{server:process.env.HTTPS_PROXY}:undefined;
const b=await chromium.launch({proxy});const ctx=await b.newContext({ignoreHTTPSErrors:true,locale:'pt-BR',timezoneId:'America/Sao_Paulo',viewport:{width:430,height:1600}});
const dir=process.argv[2];
for(const slug of process.argv.slice(3)){
 const p=await ctx.newPage();
 await p.goto('https://sport-iframe.x7q9f3.click/pt/events/'+slug+'?tab=all',{waitUntil:'domcontentloaded',timeout:60000}).catch(e=>console.log('GOTO',e.message));
 await p.waitForTimeout(9000);
 require('fs').writeFileSync(dir+'/main_'+slug+'.txt',await p.evaluate(()=>document.body.innerText));
 await p.getByText('Total de jogado',{exact:false}).first().click({timeout:5000}).catch(e=>console.log('sem props',slug));
 await p.waitForTimeout(3500);
 for(let i=0;i<15;i++){const n=await p.evaluate(()=>{const els=[...document.querySelectorAll('*')].filter(e=>e.children.length===0&&e.innerText&&e.innerText.trim()==='Mostrar mais');els.forEach(e=>e.click());return els.length});if(!n)break;await p.waitForTimeout(1000);}
 require('fs').writeFileSync(dir+'/players_'+slug+'.txt',await p.evaluate(()=>document.body.innerText));
 console.log('ok',slug); await p.close();}
await b.close()})();
