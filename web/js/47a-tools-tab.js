// «Tools» tab (92 mainView 'tools'): «Tools | Session tools» switch — tools = 47 paintTools, conn = 47k paintMcpConn.
// ⚠An old Tokens › Tools/Connections or Pipelines › Tools/Connections state arrives as 05 mvToolsMoved; it wins once and is written back.
const TLVIEWS = ['tools', 'conn'];
let TLVIEW = (() => {
  if(typeof mvToolsMoved !== 'undefined' && TLVIEWS.includes(mvToolsMoved)){ lsSet('sidereus.tlview', mvToolsMoved); return mvToolsMoved; }
  const v = lsGet('sidereus.tlview', 'tools');
  return TLVIEWS.includes(v) ? v : 'tools';
})();
function tlViewSeg(){
  return '<div class=tkvs>' + [['tools', 'Tools'], ['conn', 'Session tools']].map(([k, en]) => '<button class="wkrgb'
    + (k === TLVIEW ? ' on" aria-pressed="true' : '" aria-pressed="false') + '" data-tlv="' + k + '">' + esc(T(en)) + '</button>').join('') + '</div>';
}
// Single TLVIEW writer for switch clicks and jumps from other views (47b); off the tab it opens the tab.
function tlSetView(v){
  v = TLVIEWS.includes(v) ? v : 'tools';
  TLVIEW = v;
  lsSet('sidereus.tlview', v);
  if(mainView !== 'tools'){ setMainView('tools'); return; }
  tlPaint();
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('.wkrgb[data-tlv]');
  if(!b || b.dataset.tlv === TLVIEW) return;
  const hadF = document.activeElement === b;   // ⚠the repaint drops focus to <body> (46 kbHold)
  tlSetView(b.dataset.tlv);
  if(hadF) kbHold('.wkrgb[data-tlv].on');
});
function tlPaint(fromPoll){
  if(mainView !== 'tools') return;
  const box = document.getElementById('feed');
  if(!box) return;
  tbSlot('tools', tlViewSeg());   // the switch lives in the header toolbar slot, never in the body
  if(TLVIEW === 'conn'){ paintMcpConn(box); return; }
  const fe = document.activeElement;   // ⚠poll rebuilds keep keyboard focus and an open title tooltip in the tool lists; this is the one guard (47b hnRepaint calls tlPaint(poll) for it)
  if(fromPoll === true && document.querySelector && document.querySelector('.tvw [title]:hover')) return;
  // A focused row (kept by tvwRepaint after open/close, also after a mouse click) is repainted with its focus put back;
  // skipping here would freeze the list until focus leaves it. Any other focused control still skips the poll.
  if(fromPoll === true && fe && fe.closest && fe.closest('.tvw')){
    if(fe.matches && fe.matches('.tvwr[data-tid]')){ tvwRepaint(fe.dataset.tid); return; }
    return;
  }
  paintTools(box);
}
// State-poll repaint (95 poll), as 48b plPoll did for these views while they lived on the Pipelines tab.
function tlPoll(){
  if(mainView !== 'tools' || document.hidden) return;
  tlPaint(true);
}
