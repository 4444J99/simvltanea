"""Persistent application frame and the named historical iteration catalog."""
from datetime import date
from html import escape
import json

from .browser_iterations import ENGINEERED_ITERATIONS


ENGINEERED_ITERATIONS_JSON = json.dumps(ENGINEERED_ITERATIONS, indent=2, ensure_ascii=False) + '\n'

STYLE = """
*{box-sizing:border-box}html,body{height:100%;margin:0;background:#101114;color:#eee;font:14px system-ui}
body{display:grid;grid-template-rows:auto minmax(0,1fr) auto}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 18px;
padding-top:max(10px,env(safe-area-inset-top));border-bottom:1px solid #34363c;background:#191b20}
.brand{letter-spacing:.12em;font-size:12px}nav{display:flex;gap:4px}
nav a{padding:10px 14px;border-radius:6px;text-decoration:none;color:#b9bcc5}
nav a[aria-current]{background:#343a40;color:#d6f7dc}
a:focus-visible,summary:focus-visible{outline:2px solid #b3e2be;outline-offset:3px}
main{position:relative;min-height:0}iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
section{height:100%;overflow:auto;padding:32px 24px 48px;max-width:1120px;margin:auto}
section a{color:#b3e2be}h1{font-size:clamp(28px,5vw,42px);letter-spacing:-.035em;margin:4px 0 12px}
h2{font-size:19px;line-height:1.3;letter-spacing:-.02em;margin:10px 0}
p{line-height:1.6;color:#b9bcc5}.intro{max-width:760px;margin:0 0 14px}.eyebrow{margin:0;color:#b3e2be;font-size:12px;letter-spacing:.08em;text-transform:uppercase}
#versions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;padding:0;margin:26px 0;list-style:none}
.iteration{display:flex;flex-direction:column;padding:22px;border:1px solid #343840;border-radius:10px;background:#191b20;min-width:0}
.iteration p{margin:0 0 18px}.version-meta{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;color:#a5a8b1;font-size:12px}
.iteration-open{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:44px;margin-top:auto;
padding:10px 12px;border:1px solid #46594b;border-radius:6px;background:#202c25;text-decoration:none;font-weight:600}
.iteration-open:hover{background:#293b2f;border-color:#78987f}.source{font-size:11px;color:#a5a8b1;margin-top:12px}
code{font:inherit;font-family:ui-monospace,monospace;overflow-wrap:anywhere}
#deployment-history{border-top:1px solid #343840;padding:20px 0;margin-top:28px}
summary{cursor:pointer;line-height:1.5;padding:6px 0}#deployment-history summary{font-size:18px}
#builds{padding-left:22px}#builds li{padding:12px 0;border-bottom:1px solid #30333b}
small{display:block;color:#a5a8b1;margin-top:4px}#catalog-about{max-width:800px;color:#a5a8b1;font-size:13px}
#catalog-about p{margin:6px 0}.catalog-count{color:#d6f7dc}.noscript{padding:10px 18px;background:#191b20}
[hidden]{display:none!important}#notice{font-size:11px;margin:0;padding:4px 18px;background:#191b20;pointer-events:none}
@media(max-width:640px){header{padding:8px;gap:4px}.brand{font-size:10px;letter-spacing:.06em}
nav a{padding:12px 9px;font-size:12px}section{padding:22px 16px 36px}#versions{grid-template-columns:1fr}.iteration{padding:18px}}
"""


def _iteration_cards() -> str:
    labels = {'replay': 'Early engine', 'studio': 'Studio',
              'lab': 'Modular Lab', 'deployment': 'Preserved website'}
    cards = []
    for item in ENGINEERED_ITERATIONS:
        title = escape(item['title'])
        stamp = date.fromisoformat(item['date'])
        display_date = f"{stamp.day} {stamp.strftime('%b %Y')}"
        revision = escape(item['revision'])
        cards.append(
            '<li class="iteration">'
            '<div class="version-meta">'
            f'<time datetime="{stamp.isoformat()}">{display_date}</time>'
            f'<span>{labels[item["kind"]]}</span></div>'
            f'<h2>{title}</h2><p>{escape(item["description"])}</p>'
            f'<a class="iteration-open" href="{escape(item["url"], quote=True)}" '
            f'target="_blank" rel="noopener" aria-label="Open {title} in a new tab">'
            'Open version <span aria-hidden="true">↗</span></a>'
            f'<small class="source">Source <code title="{revision}">{revision[:7]}</code></small>'
            '</li>')
    return '\n'.join(cards)


def _shell_html(default_view: str) -> str:
    direct = default_view == 'iterations'
    title = 'SIMVLTANEA · Iterations' if direct else 'SIMVLTANEA'
    hidden = '' if direct else ' hidden'
    navigation = ''.join(
        f'<a href="#{name}" data-view="{name}"' +
        (' aria-current="page"' if name == default_view else '') + f'>{label}</a>'
        for name, label in (('watch', 'Watch'), ('compose', 'Compose'), ('iterations', 'Iterations')))
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        'connect-src \'self\'; script-src \'self\'; style-src \'unsafe-inline\'; '
        'frame-src \'self\'; object-src \'none\'; base-uri \'none\'">'
        f'<title>{title}</title><style>{STYLE}</style>'
        '<script src="shell.js" defer></script></head>'
        f'<body data-default-view="{default_view}"><header><strong class="brand">SIMVLTANEA</strong>'
        f'<nav aria-label="Main navigation">{navigation}</nav></header><main id="views">'
        f'<section id="iterations" aria-labelledby="iterations-title"{hidden}>'
        '<p class="eyebrow">The project through its versions</p><h1 id="iterations-title">Iterations</h1>'
        f'<p class="intro"><span class="catalog-count">{len(ENGINEERED_ITERATIONS)} engineered versions</span>, '
        'from the earliest recovered browser engines to the composition workspace. '
        'Open any version in its own tab and use its original controls.</p>'
        '<details id="catalog-about"><summary>About the versions and their media</summary>'
        '<p>The restored early engines, Studios and modular Labs use the current public clip library. '
        'Their pages explain the source version and any media adaptation. '
        'They do not recreate an unavailable historical media collection.</p>'
        '<p>Dates are source-commit dates in UTC. Versions are ordered from oldest to newest. '
        'Preserved website links open their original published builds.</p></details>'
        f'<ol id="versions" aria-label="Engineered versions, oldest first">{_iteration_cards()}</ol>'
        '<details id="deployment-history"><summary>All recorded website deployments '
        f'({len(json.loads(ITERATIONS_JSON))})</summary>'
        '<p>The complete recorded deployment history, newest first. Several builds refine the same '
        'version. A successful deployment alone does not certify playback.</p>'
        '<ol id="builds"><li>Loading the deployment history…</li></ol></details>'
        '</section></main><p id="notice" role="status">Views keep their own sessions. '
        'Switching pauses the view you leave.</p><noscript><div class="noscript">'
        'Playback requires JavaScript. <a href="watch.html">Open Watch</a>, '
        '<a href="workspace.html">open Compose</a> or '
        '<a href="iterations.html">browse all iterations</a>.</div></noscript></body></html>')


SHELL_JS = """'use strict';
const frames=new Map(); let active=null;
function pause(name){
 frames.get(name)?.contentWindow.postMessage({type:'simvltanea:pause'},location.origin);
}
function mount(name){
 if(frames.has(name))return;
 const frame=document.createElement('iframe');frame.title=name==='watch'?'Watch composition':'Composition workspace';frame.hidden=true;frame.allow='autoplay; fullscreen';
 frame.addEventListener('load',()=>{
  const doc=frame.contentDocument;if(!doc)return;
  const style=doc.createElement('style');style.textContent=name==='compose'?'.system-nav{display:none!important}':'.lab-link{display:none!important}';doc.head.append(style);
  if(active!==name)pause(name);
 });
 frame.src=(name==='watch'?'watch.html'+location.search:'workspace.html');frames.set(name,frame);document.getElementById('views').append(frame);
}
function navigate(){
 const requested=location.hash.slice(1);
 const fallback=document.body?.dataset.defaultView==='iterations'?'iterations':'watch';
 const name=['watch','compose','iterations'].includes(requested)?requested:fallback;
 if(active && active!==name)pause(active);
 active=name;
 if(name!=='iterations')mount(name);
 frames.forEach((frame,key)=>{frame.hidden=key!==name;});
 document.getElementById('iterations').hidden=name!=='iterations';
 document.querySelectorAll('[data-view]').forEach(link=>{if(link.dataset.view===name)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');});
 document.title='SIMVLTANEA · '+({watch:'Watch',compose:'Compose',iterations:'Iterations'}[name]);
}
addEventListener('message', event => {
 if(event.origin!==location.origin || event.source!==frames.get('watch')?.contentWindow || event.data?.type!=='simvltanea:watch-url' || typeof event.data.search!=='string')return;
 const url=new URL(location.href);url.search=event.data.search;history.replaceState(null,'',url);
});
addEventListener('hashchange',navigate);
document.addEventListener('visibilitychange',()=>{if(document.hidden&&active)pause(active);});
fetch('iterations.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(items=>{
 const list=document.getElementById('builds');list.textContent='';
 for(const item of items){
  const row=document.createElement('li');const link=document.createElement('a');
  link.href=item.url;link.target='_blank';link.rel='noopener';link.textContent=item.title;
  const detail=document.createElement('small');detail.textContent=item.date+' · '+(item.revision||'revision unrecorded');
  row.append(link,detail);list.append(row);
 }
}).catch(()=>{document.getElementById('builds').textContent='The deployment history could not load. The versions above remain available.';});
navigate();
"""

ITERATIONS_JSON = '[{"url":"https://2056b2b0.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T21:25:14.517203Z","revision":"d6b61b72fc197455837c0fd824a9bfd0dcfafb55","title":"Merge local main (f835939) into GitHub main (e563073) for reconciliation"},{"url":"https://6874f745.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T20:59:38.211031Z","revision":"d6b61b72fc197455837c0fd824a9bfd0dcfafb55","title":"Merge local main (f835939) into GitHub main (e563073) for reconciliation"},{"url":"https://bf6d702a.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T18:00:39.541369Z","revision":"e563073312b7a085d88af5f15acb0d332c5391ed","title":"Merge pull request #97 from 4444J99/feat/parallel-composition-workspace"},{"url":"https://5af076c9.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T17:58:42.829547Z","revision":"ce6c2435f38a17141e777f71b19f440e4c0ef0e5","title":"Give Composition Workspace its own route alongside Studio"},{"url":"https://2ed9367c.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T12:56:25.859939Z","revision":"54ba9512f3f500b52e3542d79f6a7a12a08428ec","title":"fix: retain source-owned recovery across native loop stalls"},{"url":"https://ad500a11.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T11:55:57.967869Z","revision":"f3c724ecd7d4483e11e8d0b623a8e283cf0501a3","title":"Preserve overdue clip priority through loop-boundary deferrals"},{"url":"https://c58f18b7.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T11:23:20.386103Z","revision":"8cc2cf8d55413e80e89c2ea54b999897670721a3","title":"Merge pull request #95 from 4444J99/feat/integrate-adjustable-filters"},{"url":"https://77791df4.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T10:31:24.615525Z","revision":"df3ac1d3c2727f4a3c5ac19e9914b830b7e0e992","title":"Recover stalled loop seams when WebKit omits the seeking flag"},{"url":"https://9b3510be.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T09:45:35.113255Z","revision":"d2b0393f3f068a248061ef213ca857b58de37534","title":"Wait for each clip entrance before checking ecological image stability"},{"url":"https://504efa8c.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T09:05:44.89117Z","revision":"7f4702a63ffe8d35e3ef757779753d2ddd5e8d36","title":"Prioritize native recovery and avoid redundant library decoders"},{"url":"https://77eb8fcc.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T08:16:27.299952Z","revision":"540d7cdfbb4b3681e07dd3b2beab211ace525ed4","title":"Recover frozen native loops without replacing logical residents"},{"url":"https://fd14a75e.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T07:05:23.353053Z","revision":"50c40f3b0c92743ea43d58e36b7d2d41fa12d97a","title":"Preserve pending Studio edits through media preparation"},{"url":"https://24390369.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T05:58:37.720634Z","revision":"207b87f87881b6fce26710b3a7291fc39aa0d7be","title":"Integrate spatial panel workspace with persistent playback repairs"},{"url":"https://1b1f00b6.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T04:39:35.353515Z","revision":"5333bb72baa4e47f85e29e5be700ede724c49c4f","title":"Guard handoff readiness and test native seek recovery"},{"url":"https://fafae868.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T04:10:39.942605Z","revision":"4998d7389418f555e2d75de0a9e1d3b930fc8335","title":"Restore spatial panels in the audiovisual editing workspace"},{"url":"https://677dcc96.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T03:46:51.910662Z","revision":"373e3870a82421ff99a1a3add283ddbece785697","title":"Keep outgoing Lab videos fitted during viewport changes"},{"url":"https://32ac6d2d.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T02:53:04.918887Z","revision":"574249bf48d68b68165875a9471e7df9c0768791","title":"fix: evolve personal clips without crossing pending source pools"},{"url":"https://6888f4c6.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T02:09:40.036148Z","revision":"d071ef373e2b4e7dc3da3fe6c0fa75d4d8deda59","title":"fix: attempt source-isolated recovery of stalled native loop seeks"},{"url":"https://6061fab7.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T01:54:03.513174Z","revision":"1a2742519fc7829431deb58d459e61345d423d5e","title":"feat: integrate editor with adjustable clip filters and native replay coverage"},{"url":"https://2b8d8b66.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T01:31:38.676985Z","revision":"0e885ef584291ef3f9754e722fbc4968c81a3da0","title":"feat: integrate editing workspace with reliable source restoration"},{"url":"https://23fc1c10.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T01:22:51.748017Z","revision":"97e6e3e75fe5b8310603f91e533cbc7c6dfda089","title":"Merge pull request #90 from 4444J99/fix/webkit-continuity"},{"url":"https://9eb72122.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T00:50:01.88666Z","revision":"5dc225a87684012a529bad97770e10a8883d3585","title":"Revert \\"test: evaluate WebKit native-wrap playback reassertion\\""},{"url":"https://97464aea.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T00:38:11.408873Z","revision":"ae4e0dc89932ef66753f3a6cfb3e59358e064f16","title":"test: record source progress across playback sampling gaps"},{"url":"https://7a4ec3e2.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T00:36:41.465422Z","revision":"083110b76c8b343c4217bbd6e8f03ce1477e5d56","title":"test: evaluate WebKit native-wrap playback reassertion"},{"url":"https://b5586918.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T00:16:53.064416Z","revision":"4a9af5d8e539e0af0a9800c9afabbd932f68ece9","title":"Add optional public-domain footage and found-sound sources"},{"url":"https://06279a78.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T00:05:59.989079Z","revision":"f43c62eca4426f949ef7b0efcc81d930111a1b4d","title":"test: reuse correlated WebKit resource verification"},{"url":"https://16d63a9f.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-08T00:05:20.741893Z","revision":"191d400fc1ce6347421c6bceeb186bf06c9834f5","title":"Replace slider lab with direct audiovisual arrangement workspace"},{"url":"https://be6a4dbd.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T23:59:31.356204Z","revision":"d32a3415a1a61ff179de2e43821a0d6627359620","title":"test: classify delayed media disposal by source identity"},{"url":"https://14238b8f.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T23:51:07.574622Z","revision":"8fa80cd058dad34c3ebc002742452abf5d922499","title":"test: preserve every decoded frame with FFmpeg 7"},{"url":"https://0620cdd3.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T23:44:13.439951Z","revision":"0e4f0ba4b1d271f0abdbd12715c6adb71df7adca","title":"Merge clip presence filters into the playback repair"},{"url":"https://3d678bfa.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T23:34:52.273083Z","revision":"d81eec6dbebb95975f0120427f085989d5803c20","title":"feat: add playable effects lab with independent audiovisual layers"},{"url":"https://e5d9b9de.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T23:25:30.391672Z","revision":"f8d31201f4c2506a872db97ac472f8136d16cc76","title":"test: expose WebKit failure diagnostics in CI logs"},{"url":"https://22267eb7.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T23:23:45.423044Z","revision":"e4f4eb467bff9ec69f89e0f9b80009bf41f39ec5","title":"test: use spatial colour fixture for neighbour framing"},{"url":"https://4fd3d646.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T23:23:39.493987Z","revision":"d25f1c558a5e844e8484887683faf9f354e23130","title":"test: correlate Apple media failures with native playback state"},{"url":"https://0fe8f773.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T23:17:57.061637Z","revision":"d0ed94586192b398be5bdc458e89620b57e19016","title":"feat: synchronize adjustable clip audio and image filters"},{"url":"https://7365f793.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T22:56:00.4179Z","revision":"e523532d14a3be232349de2ee67204f355d80bab","title":"fix: resolve Apple browser cache path on the runner"},{"url":"https://3236dd5f.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T22:53:19.827615Z","revision":"38810e5a794316ccb86cfc7d334f68c7d3f906c3","title":"test: verify sustained Studio playback on Apple WebKit"},{"url":"https://33af4610.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T22:48:17.72819Z","revision":"8e3369fe77de4f50fae671a6f77f97f0b1aa7afd","title":"feat: add per-clip audio and visual presence filters"},{"url":"https://278340dc.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T22:03:58.87307Z","revision":"0f3743769e75011097d781e7d9c14b8fd66681a3","title":"fix: keep resting loops running and verify handoff frames"},{"url":"https://c1054351.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T21:22:23.890564Z","revision":"63612a9a7394d8b4e1ec1d375baaa17eaf265eb9","title":"Merge pull request #88 from 4444J99/docs/studio-ecosystem"},{"url":"https://1ce073eb.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T20:42:26.653193Z","revision":"489c3c39b879f92668d31a868c329af0cb0e6faa","title":"fix: publish boomerang libraries with portable no-clobber writes"},{"url":"https://b459ec4b.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T20:01:55.205037Z","revision":"a41da9ff9d41fa2799b97819e65e67157ce425fb","title":"test: preserve VFR fixtures and verify committed decoded playback"},{"url":"https://5f07482e.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T19:50:59.128801Z","revision":"d7ebe5b1afa82b15b7183fcc1993da3b87f76d28","title":"fix: enforce the four-panel playback budget on touch devices"},{"url":"https://cf2925a6.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T19:10:39.616388Z","revision":"a47578a2b29622ddd389b2a6410ecd6505d815ab","title":"fix: pin Pages builds to the verified boomerang library"},{"url":"https://75cafe28.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T19:08:32.517014Z","revision":"50aba299662fc4ba75aa79835349d9551f3bec7d","title":"Studio ecosystem preview for PR #88"},{"url":"https://c30d12fb.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T19:02:58.003624Z","revision":"50aba299662fc4ba75aa79835349d9551f3bec7d","title":"feat: keep Studio playback continuous and evolve its audiovisual ecosystem"},{"url":"https://be188707.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T17:06:28.235501Z","revision":"b1a35037a01376bfd95bd5b81eb23f3e1471ec0a","title":"docs: propose continuous Studio playback and evolving clip ecology"},{"url":"https://3eb09914.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T16:41:17.261763Z","revision":"8579c13c91018174c0619cab400df82c902174b2","title":"Merge pull request #87 from 4444J99/fix/pages-staged-library"},{"url":"https://559936a6.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T16:37:38.881959Z","revision":"0bee5505d53ab6f1dd8bcda6af251c48536f1cc8","title":"fix(publishing): build Pages from staged Studio and pinned clips"},{"url":"https://7fec0066.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T02:20:41.925379Z","revision":"b81c2170e2d7346a4fcfc2cb6d2fe3775bffee8b","title":"Restore generated fallback audio"},{"url":"https://5fef4067.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-07T02:19:19.02436Z","revision":"b81c2170e2d7346a4fcfc2cb6d2fe3775bffee8b","title":"Restore generated fallback audio"},{"url":"https://439faded.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-06T19:17:56.762274Z","revision":null,"title":"Recorded upload"},{"url":"https://ed33655f.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-06T19:17:05.397855Z","revision":null,"title":"Recorded upload"},{"url":"https://b7ef6276.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-06T18:15:46.418978Z","revision":null,"title":"Recorded upload"},{"url":"https://eae78fa4.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-06T17:45:53.487749Z","revision":null,"title":"Recorded upload"},{"url":"https://d8c2a026.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-06T17:23:16.378185Z","revision":null,"title":"Recorded upload"},{"url":"https://fd79c985.loop-compositor-studio.pages.dev","status":"success","date":"2026-11-06T16:26:59.19257Z","revision":null,"title":"Recorded upload"}]'

SHELL_HTML = _shell_html("watch")
ITERATIONS_HTML = _shell_html("iterations")
