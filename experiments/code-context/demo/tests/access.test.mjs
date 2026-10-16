import test from 'node:test';
import assert from 'node:assert/strict';
import { canAccessProject } from '../src/auth/permissions.ts';
import { getProject } from '../src/api/projects.ts';

const member = { organizationId:'example' };
const project = { organizationId:'example', archived:false, name:'Demo' };
test('canAccessProject denies an expired trial at its exact boundary', () => {
  assert.equal(canAccessProject(member,project,{plan:'trial',trialEndsAt:100},100),false);
  assert.equal(getProject(member,project,{plan:'trial',trialEndsAt:100},100).status,403);
});
test('canAccessProject retains paid access until the paid-through date after cancellation', () => {
  assert.equal(canAccessProject(member,project,{plan:'paid',trialEndsAt:0,canceledAt:50,paidThrough:200},100),true);
});
test('canAccessProject never crosses organizations or permits an archived project', () => {
  assert.equal(canAccessProject({organizationId:'other'},project,{plan:'paid',trialEndsAt:0,paidThrough:200},100),false);
  assert.equal(canAccessProject(member,{...project,archived:true},{plan:'paid',trialEndsAt:0,paidThrough:200},100),false);
});
