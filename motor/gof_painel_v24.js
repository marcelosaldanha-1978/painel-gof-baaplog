// ---------- v2.4: blocos opcionais (config «blocos»), injetados por render_html só quando ligados
// Restos a pagar por ano de inscrição (rp_por_ano) e contratos vigentes (contratos). Sem pessoa, sem NE.
(function(){var nv=document.getElementById("nav"),mainEl=document.querySelector("main");
function sec(id,tid){var s=document.createElement("section");s.id=id;s.setAttribute("aria-labelledby",tid);mainEl.appendChild(s);return s;}
var tb='style="width:100%;border-collapse:collapse;font-size:13px;min-width:560px"',th='style="text-align:right;padding:4px 6px;border-bottom:1px solid currentColor;white-space:nowrap"',td='style="text-align:right;padding:4px 6px;white-space:nowrap"',tl='style="text-align:left;padding:4px 6px"';
var RP=D.rp_por_ano;
if(RP!==undefined){var el=sec("rpano","trpano");
 var h='<p class="kicker">Restos a pagar · Diretriz e Dec. 93.872/1986, art. 68</p><h2 id="trpano">Restos a pagar por ano de inscrição</h2>';
 if(!RP||RP.ausente){h+='<div class="card"><p class="note orange">'+esc((RP&&RP.ressalva)||"Leitura do TG por NE ainda não disponível.")+'</p></div>';}
 else{h+='<p class="sub">Dados do TG até '+dbr(RP.data_dado)+'. Índice = (liquidado + cancelado) ÷ (inscrito + reinscrito). Conferido: soma por NE = restos a pagar da régua, UG a UG.</p>';
  (RP.alertas||[]).forEach(function(a){h+='<div class="card"><p class="note '+(a.evento==="cancelamento"?"red":"orange")+'"><b>'+esc(NOME[a.omds]||a.omds)+' · UG '+esc(a.ug)+' · '+esc(a.ano)+':</b> '+esc(a.texto)+' — '+rs(a.saldo)+'</p></div>';});
  var por={};(RP.por_omds||[]).forEach(function(x){(por[x.omds]=por[x.omds]||[]).push(x);});
  Object.keys(por).forEach(function(o){var L=por[o];
   h+='<div class="card"><h3>'+esc(L[0].rotulo||o)+'</h3><div style="overflow-x:auto"><table '+tb+'><thead><tr><th '+tl.replace("padding","font-weight:600;padding")+'>Ano</th><th '+th+'>Inscrito + reinscrito</th><th '+th+'>Liquidado</th><th '+th+'>Cancelado</th><th '+th+'>A liquidar</th><th '+th+'>Bloqueado</th><th '+th+'>Índice</th><th '+th+'>Prazo legal</th></tr></thead><tbody>';
   L.forEach(function(x){var tot=x.ano==="total";
    h+='<tr'+(tot?' style="font-weight:600"':'')+'><td '+tl+'>'+(tot?"Total":esc(x.ano))+'</td><td '+td+'>'+rs(x.inscrito)+'</td><td '+td+'>'+rs(x.liquidado)+'</td><td '+td+'>'+rs(x.cancelado)+'</td><td '+td+'>'+rs(x.a_liquidar+(x.em_liquidacao||0))+'</td><td '+td+'>'+rs(x.bloqueado)+'</td><td '+td+'>'+(x.indice==null?"—":pc(x.indice))+'</td><td '+td+'>'+(tot?"":"bloq. "+esc(String(x.bloqueio).split("-").reverse().join("/"))+"<br>canc. "+esc(String(x.cancelamento).split("-").reverse().join("/")))+'</td></tr>';});
   h+='</tbody></table></div>'+(L.some(function(x){return x.excetuado>0.005;})?'<p class="note">Inclui saldo excetuado do cancelamento (Lei 14.133/2021, art. 105).</p>':'')+'</div>';});}
 el.innerHTML=h;if(nv)nv.innerHTML+='<a href="#rpano">Restos a pagar</a>';}
var CT=D.contratos;
if(CT!==undefined){var ec=sec("contratos","tcontratos");
 var c='<p class="kicker">Contratos · Contratos.gov.br</p><h2 id="tcontratos">Contratos vigentes</h2>';
 if(!CT||CT.ausente){c+='<div class="card"><p class="note orange">'+esc((CT&&CT.ressalva)||"Coleta de contratos ainda não disponível.")+'</p></div>';}
 else{c+='<p class="sub">Coleta de '+dbr(CT.data_coleta)+'. Valor global é o teto do instrumento, não o executado. A execução de cada contrato vem do TG.</p>';
  (CT.ressalvas||[]).forEach(function(r){c+='<p class="note orange">'+esc(r)+'</p>';});
  (CT.por_omds||[]).forEach(function(o){c+='<div class="card"><h3>'+esc(o.rotulo)+' <span class="un">· UG '+esc(o.ug)+'</span></h3>';
   if(o.indisponivel){c+='<p class="note orange">Fonte indisponível na coleta.</p></div>';return;}
   c+='<div class="kv"><span>Vigentes</span><b>'+n(o.quantidade)+'<small>teto '+mi(o.teto_total)+'</small></b></div><div class="kv"><span>Vencem em até 90 · 180 · 365 dias</span><b>'+n(o.vencem_90)+' · '+n(o.vencem_180)+' · '+n(o.vencem_365)+'</b></div>';
   if(o.contratos&&o.contratos.length){c+='<details><summary>Ver os '+n(o.contratos.length)+' contratos</summary><div style="overflow-x:auto"><table '+tb+'><thead><tr><th '+tl+'>Número</th><th '+tl+'>Objeto</th><th '+th+'>Fim</th><th '+th+'>Dias</th><th '+th+'>Valor global (teto)</th></tr></thead><tbody>';
    o.contratos.forEach(function(k){var cor=k.dias_para_vencer<=90?"red":(k.dias_para_vencer<=180?"orange":"");c+='<tr><td '+tl+'>'+esc(k.numero)+'</td><td '+tl+'>'+esc(k.objeto)+'</td><td '+td+'>'+esc(String(k.vigencia_fim).split("-").reverse().join("/"))+'</td><td '+td+'><span class="'+cor+'">'+n(k.dias_para_vencer)+'</span></td><td '+td+'>'+rs(k.valor_global_teto)+'</td></tr>';});
    c+='</tbody></table></div></details>';}
   c+='</div>';});}
 ec.innerHTML=c;if(nv)nv.innerHTML+='<a href="#contratos">Contratos</a>';}
})();
