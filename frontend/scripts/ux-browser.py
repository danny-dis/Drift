"""Isolated rendered UI acceptance with intercepted API fixtures; no live writes."""
import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
BASE=os.environ.get('DRIFT_TEST_BASE','http://127.0.0.1:5197')
OUT=Path(os.environ['DRIFT_TEST_OUTPUT'])
OUT.mkdir(parents=True,exist_ok=True)
def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True,args=['--disable-gpu'])
  page=browser.new_page(viewport={'width':1440,'height':1000})
  errors=[]; console_errors=[]; expected_http_errors=[]; writes=[]; conflict=[False]; fail_list=[False]; fail_capture=[False]; fail_aux=['']; fail_wiki=[False]
  def on_console(message):
   if message.type in ['error','warning']:
    (expected_http_errors if message.text.startswith('Failed to load resource:') else console_errors).append(message.text)
  page.on('console',on_console)
  page.on('pageerror',lambda e:errors.append(str(e)))
  data={'ideas':[{'id':'i1','text':'Long original idea','revision':0,'archived':False,'status':'captured'}], 'projects':[{'id':'p1','name':'Fixture project','repo':'','importance':0.5,'revision':0,'archived':False}], 'captures':[{'id':'c1','text':'Exact original thought','current_text':'Current thought','revision':0,'archived':False,'created_at':'2026-01-01','status':'captured'}]}
  def intercept(route):
   req=route.request; path=req.url.split('/api/')[-1].split('?')[0]; status=200; result={}
   if req.method!='GET':writes.append((req.method,path,req.post_data_json))
   bits=path.split('/'); resource=bits[1] if len(bits)>1 else ''
   if resource in data:
    rows=data[resource]; body=req.post_data_json if req.method!='GET' else {}
    if len(bits)==2:
     if req.method=='POST' and resource=='captures' and fail_capture[0]:status=503;fail_capture[0]=False
     elif req.method=='POST':
      item={'id':f'new-{resource}-{len(rows)}','revision':0,'archived':False,**body}
      if resource=='captures':item.update(created_at='2026-01-01',status='captured')
      rows.append(item); result={resource[:-1] if resource!='captures' else 'capture':item}
     elif fail_list[0]: status=401;result={'detail':'Token needed'}
     else: result={resource:rows,'total':len(rows),'has_more':False}
    else:
     item=next((x for x in rows if x['id']==bits[2]),None)
     if item is None:status=404
     elif req.method=='PATCH':
      if conflict[0]:
       status=409;result={'detail':'Revision conflict'};conflict[0]=False;item['revision']+=1;item['text']='Changed elsewhere'
      elif body.get('expected_revision')!=item['revision']:status=409;result={'detail':'Revision conflict'}
      else:
       for k,v in body.items():
        if k!='expected_revision':item['current_text' if k=='text' and resource=='captures' else k]=v
       item['revision']+=1
     elif req.method=='DELETE':item['archived']=True
     elif req.method=='POST':item['archived']=False
     if item and status==200:result={resource[:-1] if resource!='captures' else 'capture':item,'events':[],'ideas':[],'drift_md':''}
   elif path=='ui/mind-map':result={'nodes':[{'id':'i:i1','kind':'idea','label':'Long original idea','target':{'section':'ideas','id':'i1'}},{'id':'p:p1','kind':'project','label':'Fixture project','target':{'section':'projects','id':'p1'}},{'id':'c:c1','kind':'thought','label':'Exact original thought','target':{'section':'inbox','id':'c1'}}],'edges':[{'source':'i:i1','target':'p:p1','relation':'about'}]}
   elif path=='ui/wiki':result={'pages':[{'id':'w1','title':'Saved wiki','status':'complete','revision':0}]}
   elif path=='ui/wiki/generate':result={'page':{'id':'w2','title':'New wiki','text':'','status':'blocked','sources':[],'verified':False},'task_id':'t1'}
   elif path=='ui/wiki/w2' and fail_wiki[0]:status=503;result={'detail':'Page read unavailable'}
   elif path.startswith('ui/wiki/'):
    result={'page':{'id':bits[-1],'title':'Saved wiki' if bits[-1]=='w1' else 'New wiki','text':'Untrusted <script>not HTML</script>' if bits[-1]=='w1' else '', 'status':'complete' if bits[-1]=='w1' else 'blocked','sources':[{'kind':'idea','id':'i1','label':'Long original idea'}],'verified':False,'stale':True,'omitted_source_count':9,'truncated_source_count':1,'errors':['Retained generation issue'],'partial_text':'Retained unfinished answer'}}
   elif path==fail_aux[0]:status=503;result={'detail':'Fixture service unavailable'}
   elif path=='status':result={'state':'idle'}
   elif path=='ui/budget':result={'remaining':0}
   elif path=='ui/research/sessions':result={'sessions':[]}
   elif path=='ui/approvals':result={'pending':[]}
   elif path=='ui/tasks':result={'tasks':[]}
   elif path.endswith('/insights'):result={'available':False}
   route.fulfill(status=status,content_type='application/json',body=json.dumps(result))
  page.route('**/api/**',intercept)
  page.goto(BASE+'/#/ideas')
  page.get_by_role('tab',name='Ideas',exact=True).focus()
  page.keyboard.press('ArrowRight')
  expect(page.get_by_role('tab',name='Projects',exact=True)).to_be_focused()
  page.goto(BASE+'/#/ideas')
  expect(page.get_by_role('heading',name='Ideas',exact=True)).to_be_visible()
  page.get_by_role('link',name='Skip to page content',exact=True).focus()
  page.keyboard.press('Enter')
  expect(page.locator('#drift-panel-ideas')).to_be_focused()
  page.get_by_role('link',name='Long original idea',exact=True).click()
  expect(page.get_by_role('heading',name='Long original idea',exact=True)).to_be_focused()
  page.get_by_role('button',name='Edit idea',exact=True).click()
  page.get_by_label('Idea text',exact=True).fill('Edited idea')
  conflict[0]=True
  page.get_by_role('button',name='Save changes',exact=True).click()
  expect(page.get_by_role('alert')).to_contain_text('changed')
  expect(page.get_by_label('Idea text',exact=True)).to_have_value('Edited idea')
  page.get_by_role('button',name='Reload latest revision (keep my edits)',exact=True).click()
  expect(page.get_by_label('Latest saved version')).to_have_text('Changed elsewhere')
  expect(page.get_by_label('Idea text',exact=True)).to_have_value('Edited idea')
  page.get_by_role('button',name='Save changes',exact=True).click()
  expect(page.get_by_role('heading',name='Edited idea',exact=True)).to_be_visible()
  page.reload();expect(page.get_by_role('heading',name='Edited idea',exact=True)).to_be_visible()
  page.get_by_role('button',name='Archive idea',exact=True).click()
  expect(page.get_by_role('button',name='Cancel',exact=True)).to_be_focused()
  page.get_by_role('button',name='Confirm archive',exact=True).click()
  page.get_by_role('button',name='Restore idea',exact=True).click()
  expect(page.get_by_text('Active · revision 2',exact=True)).to_be_visible()
  for section,heading in [('projects','Projects'),('inbox','Thoughts')]:
   page.goto(BASE+'/#/'+section)
   page.get_by_role('link',name='Fixture project' if section=='projects' else 'Current thought',exact=True).click()
   page.get_by_role('button',name='Edit project' if section=='projects' else 'Edit thought',exact=True).click()
   if section=='projects':page.get_by_label('Name',exact=True).fill('Renamed project')
   else:page.get_by_label('Current thought text',exact=True).fill('Updated thought')
   page.get_by_role('button',name='Save changes',exact=True).click()
   if section=='inbox':expect(page.get_by_label('Full original thought',exact=True)).to_have_text('Exact original thought')
   kind='project' if section=='projects' else 'thought'
   page.get_by_role('button',name='Archive '+kind,exact=True).click()
   expect(page.get_by_role('button',name='Cancel',exact=True)).to_be_focused()
   page.get_by_role('button',name='Cancel',exact=True).click()
   expect(page.get_by_text('Active · revision 1',exact=True)).to_be_visible()
   page.get_by_role('button',name='Archive '+kind,exact=True).click()
   page.get_by_role('button',name='Confirm archive',exact=True).click()
   page.reload();expect(page.get_by_text('Archived · revision 1',exact=True)).to_be_visible()
   page.get_by_role('button',name='Restore '+kind,exact=True).click()
   expect(page.get_by_text('Active · revision 1',exact=True)).to_be_visible()
  for section,kind in [('ideas','idea'),('projects','project')]:
   page.goto(BASE+'/#/'+section)
   page.get_by_role('button',name='Add '+kind,exact=True).click()
   page.get_by_label('Idea text' if kind=='idea' else 'Name',exact=True).fill('Created '+kind)
   page.get_by_role('button',name='Add '+kind,exact=True).click()
   expect(page.get_by_role('heading',name='Created '+kind,exact=True)).to_be_focused()
   page.reload();expect(page.get_by_role('heading',name='Created '+kind,exact=True)).to_be_visible()
  page.goto(BASE+'/#/inbox')
  page.get_by_role('button',name='Add thought',exact=True).click()
  draft=page.get_by_label('Capture a thought',exact=True)
  draft.fill('Retry exact original')
  fail_capture[0]=True
  page.get_by_role('button',name='Save thought',exact=True).click()
  expect(page.get_by_role('alert')).to_contain_text('could not confirm')
  page.reload();page.get_by_role('button',name='Add thought',exact=True).click()
  expect(draft).to_have_value('Retry exact original')
  draft.fill('Newer draft survives original retry')
  page.get_by_role('button',name='Save thought',exact=True).click()
  expect(page.get_by_text('Saved in Drift. Capturing is separate from processing.',exact=True)).to_be_visible()
  expect(draft).to_have_value('Newer draft survives original retry')
  capture_writes=[x for x in writes if x[0]=='POST' and x[1]=='ui/captures']
  assert capture_writes[-1][2]==capture_writes[-2][2]
  page.get_by_role('button',name='Close composer',exact=True).click()
  page.get_by_role('link',name='Retry exact original',exact=True).click()
  expect(page.get_by_label('Full original thought',exact=True)).to_have_text('Retry exact original')
  page.goto(BASE+'/#/mind-map')
  expect(page.get_by_role('link',name='thought: Exact original thought',exact=True)).to_have_count(2)
  page.get_by_role('link',name='thought: Exact original thought',exact=True).first.click()
  expect(page.get_by_role('heading',name='Updated thought',exact=True)).to_be_focused()
  page.go_back();expect(page.get_by_role('heading',name='Mind map',exact=True)).to_be_visible()
  page.go_forward();expect(page.get_by_role('heading',name='Updated thought',exact=True)).to_be_focused()
  page.go_back();expect(page.get_by_role('heading',name='Mind map',exact=True)).to_be_visible()
  for label,title in [('idea: Long original idea','Edited idea'),('project: Fixture project','Renamed project')]:
   page.get_by_role('link',name=label,exact=True).first.click()
   expect(page.get_by_role('heading',name=title,exact=True)).to_be_focused()
   page.go_back();expect(page.get_by_role('heading',name='Mind map',exact=True)).to_be_visible()
  page.goto(BASE+'/#/wiki')
  expect(page.get_by_role('heading',name='Wiki',exact=True)).to_be_visible()
  page.get_by_role('link',name='Saved wiki',exact=True).click()
  expect(page.get_by_text('Untrusted <script>not HTML</script>',exact=True)).to_be_visible()
  expect(page.get_by_text('Sources have changed since this page was generated.',exact=False)).to_be_visible()
  expect(page.get_by_text('9 sources omitted',exact=False)).to_be_visible()
  expect(page.get_by_text('1 source excerpt shortened',exact=False)).to_be_visible()
  expect(page.get_by_text('Retained generation issue',exact=True)).to_be_visible()
  page.get_by_text('Read unfinished output',exact=True).click()
  expect(page.get_by_text('Retained unfinished answer',exact=True)).to_be_visible()
  page.get_by_role('link',name='Long original idea',exact=True).click()
  expect(page.get_by_role('heading',name='Edited idea',exact=True)).to_be_visible()
  page.goto(BASE+'/#/wiki')
  page.get_by_role('button',name='Generate wiki page',exact=True).click()
  page.get_by_label('Page title',exact=True).fill('New wiki')
  page.get_by_role('combobox',name='Project scope',exact=True).select_option('p1')
  assert not any(x[1]=='ui/wiki/generate' for x in writes)
  fail_wiki[0]=True
  page.get_by_role('button',name='Confirm and queue generation',exact=True).click()
  expect(page).to_have_url(BASE+'/#/wiki/w2')
  expect(page.get_by_role('alert')).to_contain_text('503')
  fail_wiki[0]=False
  page.get_by_role('button',name='Retry',exact=True).click()
  expect(page.get_by_text('Status: blocked',exact=True)).to_be_visible()
  assert len([x for x in writes if x[1]=='ui/wiki/generate'])==1
  data['ideas'].extend({'id':f'older-{i}','text':f'Older searchable idea {i}','archived':False,'revision':0} for i in range(25))
  page.goto(BASE+'/#/ideas')
  page.get_by_label('Search all ideas',exact=True).fill('Older searchable idea 24')
  expect(page.get_by_role('link',name='Older searchable idea 24',exact=True)).to_be_visible()
  page.get_by_label('Search all ideas',exact=True).fill('')
  page.get_by_role('button',name='Next',exact=True).click()
  expect(page.get_by_role('link',name='Older searchable idea 24',exact=True)).to_be_visible()
  page.get_by_role('link',name='Older searchable idea 24',exact=True).click()
  page.get_by_role('button',name='Archive idea',exact=True).click()
  page.get_by_role('button',name='Confirm archive',exact=True).click()
  page.goto(BASE+'/#/ideas')
  page.get_by_label('Search all ideas',exact=True).fill('Older searchable idea 24')
  expect(page.get_by_role('link',name='Older searchable idea 24',exact=True)).to_have_count(0)
  page.get_by_role('checkbox',name='Archived',exact=True).check()
  page.get_by_role('link',name='Older searchable idea 24',exact=True).click()
  page.get_by_role('button',name='Restore idea',exact=True).click()
  expect(page.get_by_text('Active · revision 0',exact=True)).to_be_visible()
  for width in [320,390,768,1024,1440]:
   page.set_viewport_size({'width':width,'height':1000})
   for section in ['inbox','ideas','projects','mind-map','wiki','office','research','attention','approvals','status']:
    if width<=600:
     page.get_by_label('Go to page',exact=True).select_option(section)
    else:
     page.get_by_role('tab',name={'inbox':'Thoughts','ideas':'Ideas','projects':'Projects','mind-map':'Mind map','wiki':'Wiki','office':'Office','research':'Research','attention':'Activity & budget','approvals':'Needs approval','status':'Workspace'}[section],exact=True).click()
    expect(page.locator('#drift-panel-'+section)).to_be_visible()
    if width==1440:
     page.reload();expect(page.locator('#drift-panel-'+section)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(width,section)
    if section in ['inbox','projects','mind-map','wiki']:
     expect(page.get_by_text('Loading saved data…',exact=True)).to_have_count(0)
     page.screenshot(path=str(OUT/f'{section}-{width}.png'),full_page=True)
   page.screenshot(path=str(OUT/f'workspace-{width}.png'),full_page=True)
  fail_list[0]=True;page.goto(BASE+'/#/ideas');expect(page.get_by_role('alert')).to_contain_text('token')
  fail_list[0]=False;page.get_by_role('button',name='Retry',exact=True).click();expect(page.get_by_role('link',name='Edited idea',exact=True)).to_be_visible()
  fail_aux[0]='ui/approvals';page.goto(BASE+'/#/approvals');page.reload()
  expect(page.get_by_role('alert')).to_contain_text('503')
  expect(page.get_by_text('No approvals to show.',exact=False)).to_have_count(0)
  fail_aux[0]='';page.get_by_role('button',name='Retry page data',exact=True).click()
  expect(page.get_by_role('alert')).to_have_count(0)
  assert not errors,errors
  assert not console_errors,console_errors
  assert all(body.get('confirm') is True and 'expected_revision' in body for method,path,body in writes if method=='DELETE')
  assert all(body=={'confirm':True} for method,path,body in writes if path.endswith('/restore'))
  assert all('expected_revision' in body for method,path,body in writes if method=='PATCH')
  print(json.dumps({'result':'PASS','fixture_api':True,'writes':len(writes),'widths':[320,390,768,1024,1440],'screenshots':str(OUT),'pageerrors':errors,'console_errors':console_errors,'expected_http_errors':len(expected_http_errors)}))
  browser.close()
if __name__=='__main__':run()
