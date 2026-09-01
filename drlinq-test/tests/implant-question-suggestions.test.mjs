import assert from 'node:assert/strict';
import fs from 'node:fs';

const html = fs.readFileSync(new URL('../implant-intake.html', import.meta.url), 'utf8');
const inlineScripts = [...html.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)].map(match => match[1]);

assert.equal(inlineScripts.length, 1, 'implant intake should have one inline application script');
assert.doesNotThrow(() => new Function(inlineScripts[0]), 'inline JavaScript must parse');

const setsMatch = html.match(/const questionSets=(\{[\s\S]*?\});\s*const medical=/);
assert.ok(setsMatch, 'question sets must be defined');
const questionSets = Function(`"use strict";return (${setsMatch[1]})`)();

for (const key of ['single', 'multiple', 'full', 'salvage', 'existing']) {
  assert.equal(questionSets[key].length, 4, `${key} must expose exactly four suggestions`);
  assert.equal(new Set(questionSets[key]).size, 4, `${key} suggestions must be unique`);
}

assert.match(questionSets.single.join(' '), /پیوند استخوان|سینوس‌لیفت/);
assert.match(questionSets.multiple.join(' '), /چند پایه ایمپلنت/);
assert.match(questionSets.full.join(' '), /پروتز ثابت|اوردنچر/);
assert.match(questionSets.existing.join(' '), /ایمپلنت قبلی/);
assert.match(html, /s\.suggestedQuestions\.length>=2/);
assert.match(html, /data-suggested-question/);
assert.match(html, /سؤال دیگری دارم/);
assert.match(html, /سؤال‌های بیمار/);

console.log('implant question suggestions: PASS');
