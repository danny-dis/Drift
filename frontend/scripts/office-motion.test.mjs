import assert from 'node:assert/strict';
import test from 'node:test';
import { officePosition, officeRoute, walkStep } from '../src/office/motion.ts';

test('the panda has distinct activity stations, with a shared computer desk', () => {
  assert.deepEqual(officePosition('idle'), { x: 2.6, y: 8.9 });
  assert.deepEqual(officePosition('writing'), officePosition('browsing'));
  assert.notDeepEqual(officePosition('reading'), officePosition('thinking'));
});

test('walking follows open aisles around the coffee table and arrives without teleporting', () => {
  let position = officePosition('idle');
  const route = officeRoute(position, 'writing');
  assert.ok(route.some(p => p.x === 6 && p.y === 10.5));
  for (const target of route) {
    for (let i = 0; i < 2000 && Math.hypot(target.x-position.x,target.y-position.y) > .001; i++) {
      const next = walkStep(position, target, 50);
      assert.ok(Math.hypot(next.x-position.x,next.y-position.y) <= .081);
      assert.ok(next.x >= 1 && next.x <= 10 && next.y >= 3 && next.y <= 11);
      assert.ok(!(next.x > 3.6 && next.x < 5.3 && next.y > 6.8 && next.y < 8.6));
      position = next;
    }
    assert.deepEqual(position, target);
  }
  assert.deepEqual(position, officePosition('writing'));
});

test('a stationary pose stays stationary and invalid frame deltas cannot jump', () => {
  const p = officePosition('idle');
  assert.deepEqual(walkStep(p,p,50),p);
  for(const delta of [NaN, Infinity, -50, 0]) assert.deepEqual(walkStep(p,officePosition('writing'),delta),p);
});
