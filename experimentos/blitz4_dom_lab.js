/* BLITZ4 Direct Reader - LAB ONLY. Paste into DevTools Console on the Blitz4 Double page.
 * Local observations only: no HTTP requests, no bets, no server writes.
 * Stop: window.blitzLab.stop(); report: window.blitzLab.report()
 */
(() => {
  if (window.blitzLab?.stop) window.blitzLab.stop();
  const selector='#roulette-recent .entries.main > .entry';
  const states={seen:[],logs:[],ambiguous:0,updates:0,started:new Date().toISOString()};
  const title=e=>e?.getAttribute('title')||e?.getAttribute('aria-label')||'';
  function parse(entry){
    const text=entry.querySelector('.roulette-tile .number')?.textContent?.trim();
    const tile=entry.querySelector('.roulette-tile');
    if(!tile)return null;
    // Confirmed by Blitz4 page inspection: whites have .roulette-tile .sm-box.white > svg.
    if(tile.querySelector('.sm-box.white svg'))return {number:0,color:'branco'};
    if(/^\d{1,2}$/.test(text||'')){
      const number=Number(text);
      if(number>=1&&number<=14)return {number,color:number<=7?'amarelo':'escuro'};
      if(number===0)return {number:0,color:'branco'};
    }
    // No guessing from background color alone. Other unknown tile types stay unconfirmed.
    const marker=[title(tile),title(entry),tile.textContent||''].join(' ').trim().toLowerCase();
    if(/(^|\s)(white|branco|zero|0)(\s|$)/.test(marker)&&!/[1-9]/.test(marker))
      return {number:0,color:'branco'};
    return {number:null,color:'nao_confirmado'};
  }
  const signature=x=>String(x.number)+':'+x.color;
  function snapshot(){
    const entries=[...document.querySelectorAll(selector)].map(parse).filter(Boolean);
    return entries;
  }
  function update(){
    const latest=snapshot();if(!latest.length)return;
    states.updates++;
    const previous=states.seen.map(signature),now=latest.map(signature);
    if(!previous.length){states.seen=latest;console.info('[Blitz LAB] referência inicial: '+latest.length+' pedras; nenhum envio retrospectivo');return}
    // Entries in this UI are newest first. Find unique exact overlap (min 3 observations).
    const overlaps=[];
    for(let shift=0;shift<now.length;shift++){
      const length=Math.min(previous.length,now.length-shift);
      if(length<3)continue;
      if(previous.slice(0,length).every((v,i)=>v===now[i+shift]))overlaps.push({shift,length});
    }
    const valid=overlaps.filter(x=>x.length>=3);
    if(valid.length!==1){
      if(previous.join('|')!==now.join('|')){
        states.ambiguous++;console.warn('[Blitz LAB] lacuna/ordem ambígua; nenhum resultado novo confirmado',{overlaps:valid.length,seen:states.seen.length,current:latest.length});
        states.seen=latest;
      }
      return;
    }
    const fresh=latest.slice(0,valid[0].shift).reverse();
    for(const item of fresh){
      states.logs.push({...item,observed_utc:new Date().toISOString(),source:'blitz4_dom_lab',verified_game_id:false});
      console.info('[Blitz LAB] rodada observada',item);
    }
    states.seen=latest;
  }
  let t;
  const observer=new MutationObserver(()=>{clearTimeout(t);t=setTimeout(update,120)});
  observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true});
  update();
  window.blitzLab={stop(){observer.disconnect();clearTimeout(t);console.info('[Blitz LAB] parado')},
    report(){return {started:states.started,updates:states.updates,ambiguous:states.ambiguous,rounds:states.logs.slice(),latest:states.seen.slice(0,15)}}};
  console.info('[Blitz LAB] ligado localmente. Use blitzLab.report() após 20-50 rodadas.');
})();