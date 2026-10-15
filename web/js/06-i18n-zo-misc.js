// Monitor row label from sidereus/bgtasks_parse.py keeps its Korean prefix on the wire (also stored in card text);
// only the fixed prefix is translated, the description is user data.
function monLab(s){ return LANG === 'en' && typeof s === 'string' && s.startsWith('감시 ') ? 'Monitor ' + s.slice(3) : s; }
// Status-bar layer (60b): an account row whose quota fetch failed.
Object.assign(I18N.ko, {'Quota fetch failed for this account': '이 계정의 한도 조회에 실패했습니다'});
