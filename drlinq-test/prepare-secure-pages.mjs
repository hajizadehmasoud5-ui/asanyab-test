import { readFile, writeFile } from 'node:fs/promises';

const pages = [
  [new URL('implant-intake.html', import.meta.url), '<script src="implant-intake-secure.js"></script>'],
  [new URL('implant-doctor.html', import.meta.url), '<script src="implant-doctor-patient.js"></script>'],
];

for (const [url, tag] of pages) {
  const source = await readFile(url, 'utf8');
  if (source.includes(tag)) continue;
  if (!source.includes('</body>')) throw new Error(`${url.pathname}: closing body tag not found`);
  await writeFile(url, source.replace('</body>', `${tag}\n</body>`), 'utf8');
}
