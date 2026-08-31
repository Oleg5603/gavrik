import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { evaluateAnswers } from '../src/rules.js';

test('любой красный флаг ведёт к экстренному результату', () => {
  assert.equal(evaluateAnswers({ urgent: true }), 'emergency');
});

test('утрата навыка требует скорого обращения', () => {
  assert.equal(evaluateAnswers({ urgent: false, regression: true }), 'soon');
});

test('наблюдаемые опасения ведут к плановой консультации', () => {
  assert.equal(evaluateAnswers({ urgent: false, regression: false, movement: true }), 'planned');
  assert.equal(evaluateAnswers({ urgent: false, regression: false, development: true }), 'planned');
});

test('отсутствие отмеченных признаков не превращается в диагноз', () => {
  assert.equal(evaluateAnswers({ urgent: false, regression: false, movement: false, development: false }), 'observe');
});

test('интерактивный скрипт входит в production-сборку как ES-модуль', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /<script type="module" src="src\/static\.js"><\/script>/);
});
