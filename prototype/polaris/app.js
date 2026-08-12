const euro = new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR' });
const nowTime = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const ids = { plan: 'PLAN-SIM-AAPL-001', order: 'ORD-SIM-0001', broker: 'SIM-BRK-4451', position: 'POS-SIM-AAPL-001' };
const navItems = ['Home','Portfolio','Opportunities','Trade Plans','Orders','Journal','Alerts','Evidence','Assistant','Settings'];
const state = {
  screen: 'home', degraded: false, emergency: false, evidenceOpen: false,
  plan: { qty: 10, entry: 212.40, stop: 205.00, target: 228.00 },
  acknowledgements: { loss: false, stop: false, portfolio: false, uncertainty: false },
  orderState: 'draft', filledQty: 0, avgFill: 0, cancellationRequested: false, positionCreated: false,
  audit: []
};
function calc() {
  const { qty, entry, stop, target } = state.plan;
  const capital = qty * entry;
  const loss = Math.max(0, qty * (entry - stop));
  const gain = Math.max(0, qty * (target - entry));
  const rr = loss ? gain / loss : 0;
  const exposure = 12.1 + capital / 100000 * 100;
  const riskRemaining = Math.max(0, 73 - loss / 1000);
  return { capital, loss, gain, rr, exposure, riskRemaining };
}
function audit(event, object, resultingState) {
  const id = `EV-SIM-${String(state.audit.length + 1).padStart(4,'0')}`;
  state.audit.unshift({ timestamp: nowTime(), event, actor: 'Prototype Operator', object, resultingState, source: 'Simulated Prototype', id });
  renderAudit();
}
function setScreen(screen) { state.screen = screen; if (screen === 'opportunity') audit('opportunity opened','AAPL','reviewing opportunity'); render(); }
function setOrderState(next, event = 'order state changed') { state.orderState = next; audit(event, ids.order, next); render(); }
function canAct() { return !state.degraded && !state.emergency; }
function updateStatus() {
  document.getElementById('sim-time').textContent = `SIM TIME ${nowTime()}`;
  document.getElementById('data-status').textContent = state.degraded ? 'DATA STATUS: DELAYED' : 'DATA STATUS: CURRENT - SIMULATED';
  document.getElementById('broker-status').textContent = state.degraded ? 'BROKER: UNAVAILABLE' : 'BROKER: SIMULATED CONNECTED';
  document.getElementById('health-status').textContent = state.emergency ? 'SYSTEM: EMERGENCY STOP ACTIVE' : state.degraded ? 'SYSTEM: DEGRADED' : 'SYSTEM: HEALTHY';
}
function renderNav() {
  const nav = document.getElementById('main-nav');
  nav.innerHTML = navItems.map(item => {
    const future = ['Journal','Alerts','Assistant','Settings'].includes(item) ? '<span class="future">future</span>' : '';
    const target = item === 'Home' ? 'home' : item === 'Opportunities' ? 'opportunity' : item === 'Trade Plans' ? 'plan' : item === 'Orders' ? 'order' : item === 'Evidence' ? 'evidence' : item.toLowerCase();
    return `<button class="nav-button ${state.screen===target?'active':''}" type="button" data-nav="${target}"><span>${item}</span>${future}</button>`;
  }).join('');
  nav.querySelectorAll('button').forEach(btn => btn.addEventListener('click', () => {
    const target = btn.dataset.nav;
    if (target === 'evidence') { toggleEvidence(true); return; }
    if (['portfolio','journal','alerts','assistant','settings'].includes(target)) { renderPlaceholder(btn.textContent.replace('future','').trim()); return; }
    setScreen(target);
  }));
}
function renderPanels() {
  const degraded = document.getElementById('degraded-panel');
  degraded.classList.toggle('hidden', !state.degraded);
  degraded.innerHTML = `<strong>DEGRADED MODE ACTIVE</strong><div class="grid two"><p><b>What is known:</b> The last portfolio snapshot was received successfully.<br><b>What is not known:</b> Current broker order state cannot be confirmed.</p><p><b>Affected functions:</b> Order submission, cancellation, and final-state reconciliation.<br><b>Safest next action:</b> Wait for connectivity or complete broker reconciliation outside this prototype.</p></div><button class="secondary" id="restore-services" type="button">RESTORE SIMULATED SERVICES</button>`;
  const emergency = document.getElementById('emergency-panel');
  emergency.classList.toggle('hidden', !state.emergency);
  emergency.innerHTML = `<strong>EMERGENCY STOP ACTIVE</strong><p>New order authorizations and simulated submission controls are disabled. Existing simulated states remain visible. This prototype does not control a real broker.</p><button class="secondary" id="reset-emergency" type="button">RESET PROTOTYPE EMERGENCY STOP</button>`;
}
function metric(label, value, note = '') { return `<article class="card"><p class="section-label">${label}</p><p class="metric-value">${value}</p><p class="muted">${note}</p></article>`; }
function header(title, subtitle) { return `<div class="screen-header"><div><p class="eyebrow">Simulated prototype</p><h1 id="screen-title">${title}</h1><p class="muted">${subtitle}</p></div><span class="pill paper">PAPER ENVIRONMENT</span></div>`; }
function renderHome() {
  return `${header('Good morning, Eduardo.','Markets are stable. Three opportunities meet your criteria. Two existing positions require review. No immediate action is required.')}
  <div class="grid metrics">
    ${metric('Portfolio Status','HEALTHY','Operating normally - simulated')}${metric('Risk Budget','73%','remaining')}${metric('Capital at Risk','2.4%','of portfolio')}${metric('Action Required','None','No immediate action')}
    ${metric('Open Positions','4','two for review')}${metric('Pending Approvals','1','prototype draft')}${metric('Broker Events','0','unresolved')}${metric('Data Status','Current','simulated')}
  </div>
  <div class="grid two" style="margin-top:1rem"><section class="card"><h2>Opportunities worth reviewing</h2><table class="table"><thead><tr><th>Symbol</th><th>Company</th><th>Classification</th><th>Sim price</th><th>Planned risk</th><th>Uncertainty</th><th>Action</th></tr></thead><tbody>
    ${['AAPL|Apple Inc.|Momentum pullback|€212.40|€74.00|Earnings within holding period','MSFT|Microsoft Corp.|Trend continuation|€401.20|€88.00|Cloud-sector overlap','NVDA|NVIDIA Corp.|High-volatility setup|€119.80|€96.00|Liquidity and gap risk'].map(row => { const c=row.split('|'); return `<tr><td><b>${c[0]}</b></td><td>${c[1]}</td><td>${c[2]}</td><td class="num">${c[3]}</td><td class="num">${c[4]}</td><td>${c[5]}</td><td><button class="secondary" data-open="${c[0]}">${c[0]==='AAPL'?'Review':'Inactive'}</button></td></tr>`}).join('')}
  </tbody></table></section><aside class="grid"><section class="card"><h2>Positions requiring review</h2><p>TSLA: review stop distance after volatility expansion.</p><p>AMZN: check sector concentration; no immediate action.</p></section><section class="card"><h2>Recent material actions</h2><div class="timeline"><div class="timeline-item"><strong>Risk review completed</strong> Simulated plan remained within Paper policy.</div><div class="timeline-item"><strong>Evidence exported</strong> Prior prototype audit record available.</div></div></section></aside></div>`;
}
function renderOpportunity() {
  return `${header('AAPL Opportunity Detail','Conceptual opportunity review. Facts, calculations, rules, model interpretation, and uncertainty remain separated.')}
  <div class="grid two"><section class="card"><dl class="kv"><dt>Instrument</dt><dd>AAPL - Apple Inc.</dd><dt>Simulated market price</dt><dd>€212.40</dd><dt>Market state</dt><dd>Stable, moderate liquidity</dd><dt>Data timestamp</dt><dd>${nowTime()} - simulated</dd><dt>Classification</dt><dd>Momentum pullback for review</dd></dl></section><section class="card warning"><h2>Unresolved uncertainty</h2><p>This recommendation includes unresolved uncertainty. Earnings are scheduled within the conceptual holding period.</p></section></div>
  <div class="grid three" style="margin-top:1rem">${['FACTS|Price above 20-day average. Volume is above the simulated review threshold.','CALCULATIONS|Reward-to-risk can exceed 2.0 under the current draft plan.','RULES|Candidate passes conceptual Paper policy and duplicate checks.','MODEL INTERPRETATION|The available evidence supports further review, not certainty.','UNCERTAINTY|Gap risk, earnings event risk, and execution uncertainty remain.','EVIDENCE|EV-SIM-OPP-AAPL, simulated scanner snapshot, simulated data freshness record.'].map(x=>{const [t,b]=x.split('|'); return `<section class="card"><p class="section-label">${t}</p><p>${b}</p></section>`}).join('')}</div>
  <div class="actions"><button class="secondary">Add to Watchlist</button><button class="ghost">Dismiss</button><button class="primary" id="create-plan" type="button">CREATE TRADE PLAN</button></div>`;
}
function renderPlan() {
  const c = calc();
  return `${header('Trade Plan Builder','AAPL BUY LIMIT plan. All values are simulated and no external action can occur.')}
  <section class="card"><div class="form-grid">
    <label>Quantity<input id="qty" type="number" min="1" value="${state.plan.qty}"></label>
    <label>Estimated entry (€)<input id="entry" type="number" step="0.01" value="${state.plan.entry.toFixed(2)}"></label>
    <label>Protective stop (€)<input id="stop" type="number" step="0.01" value="${state.plan.stop.toFixed(2)}"></label>
    <label>Target (€)<input id="target" type="number" step="0.01" value="${state.plan.target.toFixed(2)}"></label>
  </div></section>
  <div class="grid metrics" style="margin-top:1rem">${metric('Estimated capital', euro.format(c.capital),'generic simulated amount')}${metric('Maximum planned loss', euro.format(c.loss),'risk before reward')}${metric('Potential gain', euro.format(c.gain),'at target, uncertain')}${metric('Reward-to-risk', c.rr.toFixed(2),'calculated')}</div>
  <div class="grid two" style="margin-top:1rem"><section class="card"><h2>Strategy rationale</h2><p>The available evidence supports further review. Invalidation condition: close below protective stop or event risk changes materially.</p><p>Planned holding period: 5-15 sessions. Event-risk acknowledgement required.</p><label>Notes<textarea id="notes">Simulated prototype plan. No broker connection.</textarea></label></section><section class="card"><h2>Portfolio impact</h2><p>Portfolio exposure after trade: <b>${c.exposure.toFixed(1)}%</b></p><p>Remaining risk budget: <b>${c.riskRemaining.toFixed(1)}%</b></p><button class="secondary" id="save-draft" type="button">Save Draft</button></section></div><div class="actions"><button class="primary" id="review-risk" type="button">REVIEW RISK</button></div>`;
}
function renderRisk() {
  const c = calc();
  const all = Object.values(state.acknowledgements).every(Boolean);
  return `${header('Risk Review','Risk appears before expected reward. This scenario remains within the configured Paper risk limit.')}
  <div class="grid metrics">${metric('Maximum planned loss', euro.format(c.loss),'shown before reward')}${metric('Capital committed', euro.format(c.capital),'portfolio capital')}${metric('Exposure after action', `${c.exposure.toFixed(1)}%`,'after approval')}${metric('Risk budget remaining', `${c.riskRemaining.toFixed(1)}%`,'simulated')}</div>
  <div class="grid two" style="margin-top:1rem"><section class="card"><h2>Risk factors</h2><table class="table"><tbody>${['Position concentration|Moderate; within Paper policy','Sector concentration|Technology overlap visible','Correlated exposure|Existing growth exposure noted','Stop distance|€7.40 per share','Liquidity|Simulated liquidity adequate','Gap risk|Possible around earnings','Earnings/event risk|Earnings are scheduled within the conceptual holding period','Stale-data risk|Current - simulated','Model uncertainty|Interpretation is not certainty','Broker uncertainty|Fill and cancellation require broker truth'].map(x=>{const [a,b]=x.split('|'); return `<tr><th>${a}</th><td>${b}</td></tr>`}).join('')}</tbody></table></section><section class="card warning"><h2>Required acknowledgements</h2><p class="status-chip">WITHIN CONFIGURED PAPER POLICY</p><div class="checklist">${[['loss','I reviewed the maximum planned loss.'],['stop','I understand that the stop price does not guarantee the exit price.'],['portfolio','I reviewed the portfolio impact.'],['uncertainty','I reviewed the identified uncertainties.']].map(([k,t])=>`<label class="checkline"><input type="checkbox" data-ack="${k}" ${state.acknowledgements[k]?'checked':''}> <span>${t}</span></label>`).join('')}</div><button class="primary" id="to-approval" type="button" ${all && canAct() ? '' : 'disabled'}>CONTINUE TO PAPER APPROVAL</button></section></div>`;
}
function renderApproval() {
  const c = calc();
  return `${header('Paper Approval','Formal approval review. This prototype does not contact a broker.')}
  <div class="grid two"><section class="card"><p class="pill paper">PAPER ENVIRONMENT</p><dl class="kv"><dt>Instrument</dt><dd>AAPL</dd><dt>Side</dt><dd>BUY</dd><dt>Order type</dt><dd>LIMIT</dd><dt>Quantity</dt><dd>${state.plan.qty} shares</dd><dt>Estimated capital</dt><dd>${euro.format(c.capital)}</dd><dt>Entry / Stop / Target</dt><dd>${euro.format(state.plan.entry)} / ${euro.format(state.plan.stop)} / ${euro.format(state.plan.target)}</dd><dt>Maximum planned loss</dt><dd>${euro.format(c.loss)}</dd><dt>Exposure after approval</dt><dd>${c.exposure.toFixed(1)}%</dd><dt>Broker</dt><dd>SIMULATED BROKER</dd><dt>External action?</dt><dd>No. Authorization creates only a simulated order lifecycle.</dd></dl></section><section class="card warning"><h2>Before authorization</h2><p>Assumptions and unresolved uncertainty remain visible. Operator authorization is required.</p><p>This prototype does not contact a broker, production system, or real market data.</p><div class="actions"><button class="primary" id="authorize" type="button" ${canAct() ? '' : 'disabled'}>AUTHORIZE PAPER ORDER</button><button class="secondary" id="back-risk" type="button">Return to Risk Review</button><button class="ghost" id="reject-plan" type="button">Reject Plan</button><button class="ghost" id="edit-plan" type="button">Edit Trade Plan</button></div></section></div>`;
}
function renderStatus() {
  const states = ['approved','submission pending','submitted','acknowledged'];
  return `${header('Paper Submission and Broker Status','The simulated lifecycle distinguishes application intent, outbound request, broker acknowledgment, broker execution, and reconciled final state.')}
  <section class="card"><div class="stepper">${states.map(s=>`<div class="step ${state.orderState===s?'current':states.indexOf(s)<states.indexOf(state.orderState)?'done':''}"><span class="status-chip">${s.toUpperCase()}</span><span>${s==='approved'?'Application approval recorded.':s==='submission pending'?'A simulated outbound request is being prepared.':s==='submitted'?'The simulated request was sent.':'The simulated broker acknowledged the order.'}</span></div>`).join('')}</div><p class="status-chip">Current state: ${state.orderState.toUpperCase()}</p><p>${state.orderState==='acknowledged'?'Order is active and has not filled.':'The prototype is waiting for the next simulated state.'}</p></section>
  <section class="card"><h2>Prototype controls</h2><p class="muted">These controls simulate broker outcomes. They do not contact a broker.</p><div class="actions"><button class="secondary" id="view-order" type="button">View Order</button><button class="secondary" id="cancel" type="button" ${canAct()?'':'disabled'}>Request Cancellation</button><button class="secondary" id="partial" type="button" ${canAct()?'':'disabled'}>Simulate Partial Fill</button><button class="secondary" id="full" type="button" ${canAct()?'':'disabled'}>Simulate Full Fill</button><button class="secondary" id="reject-order" type="button" ${canAct()?'':'disabled'}>Simulate Rejection</button><button class="secondary" id="unknown" type="button">Simulate Unknown State</button></div></section>`;
}
function renderOrder() {
  const c = calc();
  return `${header('Order Detail','Never show completed when broker state is unresolved.')}
  <div class="grid two"><section class="card"><dl class="kv"><dt>Internal plan ID</dt><dd>${ids.plan}</dd><dt>Internal order ID</dt><dd>${ids.order}</dd><dt>Sim broker order ID</dt><dd>${ids.broker}</dd><dt>Instrument</dt><dd>AAPL</dd><dt>Side</dt><dd>BUY</dd><dt>Quantity</dt><dd>${state.plan.qty}</dd><dt>Order type</dt><dd>LIMIT</dd><dt>Limit</dt><dd>${euro.format(state.plan.entry)}</dd><dt>Environment</dt><dd>PAPER ENVIRONMENT</dd><dt>Current status</dt><dd>${state.orderState.toUpperCase()}</dd><dt>Filled quantity</dt><dd>${state.filledQty}</dd><dt>Average fill price</dt><dd>${state.avgFill ? euro.format(state.avgFill) : '—'}</dd><dt>Cancellation status</dt><dd>${state.cancellationRequested ? state.orderState==='cancelled'?'Confirmed cancelled':'Cancellation requested, not confirmed' : 'Not requested'}</dd><dt>Reconciliation status</dt><dd>${['filled','cancelled','rejected'].includes(state.orderState)?'Reconciled final state':state.orderState==='unresolved'?'Reconciliation required':'Active / not final'}</dd><dt>Latest broker message</dt><dd>${state.orderState==='rejected'?'Simulated broker rejected the order because the prototype scenario requested rejection.':state.orderState==='unresolved'?'The application cannot confirm the broker final state.':'The simulated broker acknowledged the order.'}</dd></dl></section><section class="card"><h2>Conceptual order states</h2><div class="state-list">${['draft','awaiting approval','approved','submission pending','submitted','acknowledged','partially filled','filled','cancellation requested','cancelled','rejected','expired','unresolved','reconciliation required'].map(s=>`<span class="status-chip">${s}</span>`).join('')}</div><div class="actions">${state.orderState==='cancellation requested'?'<button class="primary" id="confirm-cancel" type="button">SIMULATE BROKER CANCELLATION CONFIRMATION</button>':''}${state.orderState==='unresolved'?'<button class="primary" id="reconcile" type="button">SIMULATE RECONCILIATION</button>':''}${state.positionCreated?'<button class="primary" id="view-position" type="button">View Position</button>':''}</div></section></div><section class="card"><h2>Evidence timeline</h2><div class="timeline">${state.audit.slice(0,8).map(e=>`<div class="timeline-item"><strong>${e.event}</strong>${e.timestamp} · ${e.object} · ${e.resultingState} · ${e.id}</div>`).join('')}</div></section>`;
}
function renderPosition() {
  const c = calc();
  return `${header('Position Detail','Performance appears with risk context. Exit submission is outside Phase 1.')}
  <div class="grid two"><section class="card"><dl class="kv"><dt>Symbol</dt><dd>AAPL</dd><dt>Quantity</dt><dd>${state.plan.qty}</dd><dt>Average entry</dt><dd>${euro.format(state.avgFill || state.plan.entry)}</dd><dt>Current simulated price</dt><dd>${euro.format(214.10)}</dd><dt>Current value</dt><dd>${euro.format(state.plan.qty * 214.10)}</dd><dt>Unrealized result</dt><dd>Simulated gain shown with original risk context</dd><dt>Original max planned loss</dt><dd>${euro.format(c.loss)}</dd><dt>Stop / Target</dt><dd>${euro.format(state.plan.stop)} / ${euro.format(state.plan.target)}</dd><dt>Portfolio exposure</dt><dd>${c.exposure.toFixed(1)}%</dd></dl></section><section class="card"><h2>Decision context</h2><p>Rationale: momentum pullback supported further review.</p><p>Invalidation: close below stop or material event-risk change.</p><p>Upcoming risk event: earnings within conceptual holding period.</p><p>Review status: review scheduled.</p><div class="actions"><button class="secondary">Review Position</button><button class="secondary">Create Exit Plan</button><button class="secondary">Add Journal Entry</button><button class="secondary" id="position-evidence">View Evidence</button></div></section></div>`;
}
function renderPlaceholder(name) { state.screen = 'placeholder'; document.getElementById('app-screen').innerHTML = `${header(name, 'Future or inactive prototype area. No production capability is implied.')}`; renderNav(); }
function renderAudit() {
  const list = document.getElementById('audit-list');
  list.innerHTML = state.audit.length ? state.audit.map(e => `<article class="audit-event"><strong>${e.event}</strong><p>${e.timestamp} · ${e.actor} · ${e.object}</p><p>Resulting state: ${e.resultingState}</p><p>Source: ${e.source} · <code>${e.id}</code></p></article>`).join('') : '<p class="muted">No material prototype actions yet. Browser refresh may reset this trail.</p>';
}
function toggleEvidence(open) { state.evidenceOpen = open; const d = document.getElementById('evidence-drawer'); d.classList.toggle('open', open); d.setAttribute('aria-hidden', String(!open)); renderAudit(); }
function render() {
  updateStatus(); renderNav(); renderPanels();
  const screen = document.getElementById('app-screen');
  screen.innerHTML = state.screen==='home'?renderHome():state.screen==='opportunity'?renderOpportunity():state.screen==='plan'?renderPlan():state.screen==='risk'?renderRisk():state.screen==='approval'?renderApproval():state.screen==='status'?renderStatus():state.screen==='order'?renderOrder():state.screen==='position'?renderPosition():renderHome();
  bind();
}
function bind() {
  document.querySelectorAll('[data-open="AAPL"]').forEach(b=>b.addEventListener('click',()=>setScreen('opportunity')));
  document.querySelectorAll('[data-open]').forEach(b=>{ if(b.dataset.open!=='AAPL') b.disabled = true; });
  const cp = document.getElementById('create-plan'); if(cp) cp.onclick=()=>{ audit('trade plan created',ids.plan,'draft'); setScreen('plan'); };
  ['qty','entry','stop','target'].forEach(id=>{ const el=document.getElementById(id); if(el) el.oninput=()=>{ state.plan[id==='qty'?'qty':id]=Number(el.value); audit('trade plan edited',ids.plan,'draft edited'); render(); }; });
  const save=document.getElementById('save-draft'); if(save) save.onclick=()=>audit('trade plan saved as draft',ids.plan,'draft');
  const rr=document.getElementById('review-risk'); if(rr) rr.onclick=()=>{ audit('risk review opened',ids.plan,'reviewing risk'); setScreen('risk'); };
  document.querySelectorAll('[data-ack]').forEach(el=>el.addEventListener('change',()=>{ state.acknowledgements[el.dataset.ack]=el.checked; audit('acknowledgment selected','risk review',Object.values(state.acknowledgements).filter(Boolean).length + ' of 4 selected'); render(); }));
  const ta=document.getElementById('to-approval'); if(ta) ta.onclick=()=>{ audit('risk review completed',ids.plan,'within configured Paper policy'); setScreen('approval'); };
  const br=document.getElementById('back-risk'); if(br) br.onclick=()=>setScreen('risk');
  const ep=document.getElementById('edit-plan'); if(ep) ep.onclick=()=>setScreen('plan');
  const rejectPlan=document.getElementById('reject-plan'); if(rejectPlan) rejectPlan.onclick=()=>{ audit('plan rejected by operator',ids.plan,'rejected; no order created'); setScreen('home'); };
  const auth=document.getElementById('authorize'); if(auth) auth.onclick=()=>{ audit('Paper order authorized',ids.plan,'approved'); state.orderState='approved'; setScreen('status'); ['submission pending','submitted','acknowledged'].forEach((s,i)=>window.setTimeout(()=>{ state.orderState=s; audit(s==='submission pending'?'simulated request prepared':s==='submitted'?'simulated request submitted':'simulated acknowledgment received',ids.order,s); render(); }, 700*(i+1))); };
  const viewOrder=document.getElementById('view-order'); if(viewOrder) viewOrder.onclick=()=>setScreen('order');
  const cancel=document.getElementById('cancel'); if(cancel) cancel.onclick=()=>{ state.cancellationRequested=true; setOrderState('cancellation requested','cancellation requested'); setScreen('order'); };
  const partial=document.getElementById('partial'); if(partial) partial.onclick=()=>{ state.filledQty=Math.max(1, Math.floor(state.plan.qty/2)); state.avgFill=212.38; setOrderState('partially filled','partial fill simulated'); };
  const full=document.getElementById('full'); if(full) full.onclick=()=>{ state.filledQty=state.plan.qty; state.avgFill=212.40; state.positionCreated=true; setOrderState('filled','full fill simulated'); };
  const rej=document.getElementById('reject-order'); if(rej) rej.onclick=()=>setOrderState('rejected','simulated broker rejection received');
  const unk=document.getElementById('unknown'); if(unk) unk.onclick=()=>setOrderState('unresolved','unknown broker state entered');
  const cc=document.getElementById('confirm-cancel'); if(cc) cc.onclick=()=>{ state.cancellationRequested=true; setOrderState('cancelled','cancellation confirmed'); };
  const rec=document.getElementById('reconcile'); if(rec) rec.onclick=()=>setOrderState('reconciliation required','reconciliation simulated; no final broker state assumed');
  const vp=document.getElementById('view-position'); if(vp) vp.onclick=()=>setScreen('position');
  const pe=document.getElementById('position-evidence'); if(pe) pe.onclick=()=>toggleEvidence(true);
  const restore=document.getElementById('restore-services'); if(restore) restore.onclick=()=>{ state.degraded=false; audit('simulated services restored','system','healthy'); render(); };
  const reset=document.getElementById('reset-emergency'); if(reset) reset.onclick=()=>{ state.emergency=false; audit('prototype emergency stop reset','system','authorization available'); render(); };
}
document.getElementById('evidence-toggle').onclick = () => toggleEvidence(true);
document.getElementById('drawer-close').onclick = () => toggleEvidence(false);
document.getElementById('emergency-entry').onclick = () => {
  if (!state.emergency) {
    const ok = window.confirm('Activate prototype emergency stop? New order authorizations and simulated submission controls will be disabled. This prototype does not control a real broker.');
    if (ok) { state.emergency = true; audit('emergency stop activated','system','EMERGENCY STOP ACTIVE'); render(); }
  }
};
window.addEventListener('keydown', (event) => { if (event.key === 'Escape') toggleEvidence(false); });
setInterval(updateStatus, 30000);
window.simulateDegradedMode = () => { state.degraded = true; audit('degraded mode simulated','system','broker unavailable; data delayed'); render(); };
function addDegradedButton() {
  const button = document.createElement('button'); button.className='ghost'; button.type='button'; button.textContent='SIMULATE DEGRADED MODE'; button.onclick=window.simulateDegradedMode; document.querySelector('.topbar').appendChild(button);
}
audit('prototype opened','Polaris Phase 1','home dashboard');
addDegradedButton();
render();
