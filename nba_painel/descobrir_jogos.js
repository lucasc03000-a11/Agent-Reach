// Lista os slugs dos próximos jogos da NBA no site de odds.
// Abre a página de um time, entra no próximo jogo dele e lê "Próximos jogos do torneio".
const {chromium}=require('playwright');(async()=>{
const proxy=process.env.HTTPS_PROXY?{server:process.env.HTTPS_PROXY}:undefined;
const b=await chromium.launch({proxy});const p=await (await b.newContext({ignoreHTTPSErrors:true,locale:'pt-BR',timezoneId:'America/Sao_Paulo'})).newPage();
const ev=()=>p.evaluate(()=>[...new Set([...document.querySelectorAll('a')].map(a=>a.href).filter(h=>/\/events\/[a-z0-9-]+-\d+$/.test(h)&&!h.includes('outrights')))]);
const times=['los-angeles-lakers-10322','san-antonio-spurs-10082','minnesota-timberwolves-9443','brooklyn-nets-15004'];
const achados=new Set();
for(const t of times){
  await p.goto('https://sport-iframe.x7q9f3.click/pt/teams/basketball/'+t,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{});
  await p.waitForTimeout(9000);
  const lista=await ev(); const prox=lista[lista.length>1?1:0]; if(!prox) continue;
  await p.goto(prox,{waitUntil:'domcontentloaded',timeout:60000}).catch(()=>{});
  await p.waitForTimeout(9000);
  (await ev()).forEach(h=>achados.add(h.split('/events/')[1]));
  achados.add(prox.split('/events/')[1]);
  if(achados.size>3) break;
}
console.log([...achados].join(' '));await b.close()})();
