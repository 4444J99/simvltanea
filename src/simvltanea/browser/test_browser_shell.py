"""Persistent navigation and a directly reachable historical catalog."""
import json
from html.parser import HTMLParser
import shutil
import subprocess
import unittest

from .browser_iterations import ENGINEERED_ITERATIONS
from .browser_shell import ITERATIONS_HTML, ITERATIONS_JSON, SHELL_HTML, SHELL_JS
from .browser_studio import studio_files


class PageElements(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.elements = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


NODE_HARNESS = r"""
const vm=require('node:vm'), assert=require('node:assert/strict');
function makeShell(defaultView='watch') {
 const events={}, nodes={}, messages=[], mounted=[];
 function element(){return {hidden:false,dataset:{},setAttribute(k,v){this[k]=v},
  removeAttribute(k){delete this[k]},append(){},addEventListener(){}};}
 const links=['watch','compose','iterations'].map(name=>
  Object.assign(element(),{dataset:{view:name}}));
 nodes.views={append(frame){mounted.push(frame)}};
 nodes.iterations=element();nodes.builds={append(){}};
 const document={hidden:false,title:'',body:{dataset:{defaultView}},
  getElementById:id=>nodes[id],querySelectorAll:()=>links,
  addEventListener:(n,f)=>events[n]=f,createElement:tag=>{
   const e=element();
   if(tag==='iframe'){
    e.contentWindow={postMessage(message,origin){
     assert.equal(message.type,'simvltanea:pause');
     assert.equal(origin,'https://example.test');messages.push(e);
    }};
    e.contentDocument={createElement:element,head:{append(){}}};
   }
   return e;
  }};
 const context=vm.createContext({document,
  location:{hash:'',search:'?seed=7',origin:'https://example.test'},
  addEventListener:(n,f)=>events[n]=f,
  fetch:()=>Promise.resolve({ok:true,json:()=>Promise.resolve([])})});
 vm.runInContext(SOURCE,context);
 return {context,document,events,nodes,links,messages,mounted,
  value:source=>vm.runInContext(source,context),
  go(hash){context.location.hash=hash;events.hashchange();}};
}
"""


class ShellTests(unittest.TestCase):
    def run_node(self, assertions):
        if not shutil.which('node'):
            self.skipTest('Node required')
        script = 'const SOURCE=' + json.dumps(SHELL_JS) + ';\n' + NODE_HARNESS + assertions
        result = subprocess.run(['node', '-e', script], capture_output=True,
                                text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_navigation_preserves_views_and_pauses_departing_transport(self):
        self.run_node(r"""
const s=makeShell();
assert.equal(s.value('frames.size'),1);
const original=s.value("frames.get('watch')");
assert.equal(original.src,'watch.html?seed=7');
s.go('#compose');assert.deepEqual(s.messages,[original]);
assert.equal(original.hidden,true);
const compose=s.value("frames.get('compose')");
assert.equal(compose.src,'workspace.html');
s.go('#watch');
assert.equal(s.value("frames.get('watch')"),original);
assert.equal(s.value('frames.size'),2);
assert.deepEqual(s.messages,[original,compose]);
s.go('#iterations');assert.equal(s.nodes.iterations.hidden,false);
assert.equal(s.value('frames.size'),2);
assert.equal(original.hidden,true);assert.equal(compose.hidden,true);
s.go('#nonsense');assert.equal(original.hidden,false);
s.document.hidden=true;s.events.visibilitychange();
assert.equal(s.messages.at(-1),original);
assert.equal(s.links[0]['aria-current'],'page');
""")

    def test_direct_catalog_route_does_not_start_a_watch_session(self):
        self.run_node(r"""
const s=makeShell('iterations');
assert.equal(s.value('frames.size'),0);
assert.equal(s.mounted.length,0);
assert.equal(s.nodes.iterations.hidden,false);
assert.equal(s.links[2]['aria-current'],'page');
assert.equal(s.document.title,'SIMVLTANEA · Iterations');
s.go('#compose');
assert.equal(s.value('frames.size'),1);
const compose=s.value("frames.get('compose')");
s.go('#iterations');assert.deepEqual(s.messages,[compose]);
assert.equal(s.value('frames.size'),1);
""")

    def test_catalog_links_exist_before_javascript_runs(self):
        expected_urls = {item['url'] for item in ENGINEERED_ITERATIONS}
        for markup in (SHELL_HTML, ITERATIONS_HTML):
            with self.subTest(page='direct' if markup == ITERATIONS_HTML else 'shell'):
                page = PageElements(markup)
                entries = [attrs for tag, attrs in page.elements
                           if tag == 'a' and attrs.get('class') == 'iteration-open']
                self.assertEqual({entry['href'] for entry in entries}, expected_urls)
                self.assertEqual(len(entries), len(ENGINEERED_ITERATIONS))
                self.assertTrue(all(entry.get('target') == '_blank' and
                                    entry.get('rel') == 'noopener' for entry in entries))
                self.assertIn('current public clip library', markup)
                self.assertIn('UTC', markup)
                self.assertNotIn('still await playable reconstruction', markup)
                history = [attrs for tag, attrs in page.elements
                           if tag == 'details' and attrs.get('id') == 'deployment-history']
                self.assertEqual(len(history), 1)
                self.assertNotIn('open', history[0])

    def test_direct_catalog_is_visible_without_javascript(self):
        page = PageElements(ITERATIONS_HTML)
        body = next(attrs for tag, attrs in page.elements if tag == 'body')
        catalog = next(attrs for tag, attrs in page.elements
                       if tag == 'section' and attrs.get('id') == 'iterations')
        self.assertEqual(body['data-default-view'], 'iterations')
        self.assertNotIn('hidden', catalog)

    def test_catalog_and_original_build_history_are_both_published(self):
        files = studio_files()
        self.assertEqual(files['iterations.html'].decode(), ITERATIONS_HTML)
        self.assertEqual(json.loads(files['engineered-iterations.json']),
                         list(ENGINEERED_ITERATIONS))
        history = json.loads(files['iterations.json'])
        self.assertEqual(history, json.loads(ITERATIONS_JSON))
        self.assertEqual(len(history), 57)
        self.assertEqual(history[0]['revision'],
                         'd6b61b72fc197455837c0fd824a9bfd0dcfafb55')


if __name__ == '__main__':
    unittest.main()
