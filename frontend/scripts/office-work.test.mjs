import assert from 'node:assert/strict';
import test from 'node:test';
import { officeWork } from '../src/office/work-context.ts';

test('desk context shows only the task and project actually reported active', () => {
  const tasks=[{id:'task-a',goal:'Read project requirements',project_id:'p1',status:'in_progress'}];
  const projects=[{id:'p1',name:'Actual project'}];
  const active={kind:'reading',active:true,task_id:'task-a',project_id:'p1'};
  const work=officeWork('thinking',active,null,tasks,projects,10000);
  assert.equal(work.kind,'reading');
  assert.equal(work.project?.name,'Actual project');
  assert.equal(work.task?.id,'task-a');
  assert.equal(work.mode,'live');
});

test('idle never pretends a saved report is the current project', () => {
  const work=officeWork('idle',{kind:'reading',active:false,task_id:'old'},null,[{id:'old',goal:'Old work',status:'complete',project_id:'p1'}],[{id:'p1',name:'Old project'}],10000);
  assert.equal(work.kind,'idle');
  assert.equal(work.project,undefined);
  assert.equal(work.task,undefined);
});

test('a real recent document save is labelled recent, then expires to idle', () => {
  const event={kind:'writing',active:false,task_id:'t1',at:'2026-10-18T00:00:00Z',target:'report.md'};
  const now=Date.parse(event.at);
  assert.equal(officeWork('idle',null,event,[],[],now+1000).mode,'recent');
  assert.equal(officeWork('idle',null,event,[],[],now+13000).kind,'idle');
  assert.equal(officeWork('idle',null,{...event,at:'invalid'},[],[],now).kind,'idle');
});

test('a task can briefly illustrate its own freshly read notes while inference is thinking', () => {
  const at='2026-10-18T00:00:00Z', current={kind:'thinking',active:true,task_id:'t1'};
  const last={kind:'reading',active:false,task_id:'t1',at};
  assert.equal(officeWork('thinking',current,last,[],[],Date.parse(at)+1000).kind,'reading');
  assert.equal(officeWork('thinking',current,{...last,task_id:'other'},[],[],Date.parse(at)+1000).kind,'thinking');
  assert.equal(officeWork('thinking',current,last,[],[],Date.parse(at)+13000).kind,'thinking');
});
