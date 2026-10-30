import test from 'node:test';
import assert from 'node:assert/strict';
import { buildVisualData, cameraForKey, findClosestTarget, projectPoint, rotatePoint } from './scene.mjs';

test('zero rotation leaves a point in its original 3D position', () => {
  assert.deepEqual(rotatePoint([1, 2, 3], 0, 0).map(n => Math.round(n * 1000) / 1000), [1, 2, 3]);
});

test('perspective keeps center centered and nearer points larger', () => {
  const center = projectPoint([0, 0, 0], 800, 600, 0, 0, 6);
  const far = projectPoint([1, 0, -1], 800, 600, 0, 0, 6);
  const near = projectPoint([1, 0, 1], 800, 600, 0, 0, 6);
  assert.equal(center.x, 400);
  assert.equal(center.y, 300);
  assert.ok(near.x - 400 > far.x - 400);
});

test('matched pairs create purple collision markers and leave other points separate', () => {
  const data = buildVisualData({
    points_3d: {
      jd: [{ id: 'jd-0', label: 'React', position: [1, 0, 0] }, { id: 'jd-1', label: 'SQL', position: [0, 1, 0] }],
      resume: [{ id: 'resume-0', label: 'React.js', position: [0.8, 0, 0] }],
    },
    matched: [{ jd_index: 0, resume_index: 0, similarity: 0.883, credit: 0.708, jd: 'React', resume: 'React.js' }],
  });
  assert.equal(data.jd.length, 2);
  assert.equal(data.resume.length, 1);
  assert.equal(data.collisions.length, 1);
  assert.deepEqual(data.collisions[0].position, [0.9, 0, 0]);
  assert.equal(data.jd[1].matched, false);
  assert.equal(data.resume[0].matched, true);
});

test('hit testing favors the visible purple marker when points overlap', () => {
  const targets = [
    { x: 20, y: 20, radius: 10, text: 'JD · React' },
    { x: 20, y: 20, radius: 10, text: 'RESUME · React' },
    { x: 20, y: 20, radius: 10, text: 'MATCH · React ↔ React' },
  ];
  assert.equal(findClosestTarget(targets, 20, 20).text, 'MATCH · React ↔ React');
  assert.equal(findClosestTarget(targets, 100, 100), null);
});

test('keyboard controls rotate and zoom the 3D camera within bounds', () => {
  const initial = { yaw: 0, pitch: 0, distance: 6 };
  assert.equal(cameraForKey(initial, 'ArrowRight').yaw, 0.18);
  assert.equal(cameraForKey(initial, 'ArrowUp').pitch, -0.18);
  assert.equal(cameraForKey(initial, '+').distance, 5.6);
  assert.equal(cameraForKey({ ...initial, distance: 4.2 }, '+').distance, 4.2);
});
