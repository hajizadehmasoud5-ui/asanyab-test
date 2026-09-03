import { readFile, writeFile } from 'node:fs/promises';

const pages = [
  ['drlinq-test/implant-intake.html', '<script src="implant-intake-secure.js"></script>'],
  ['drlinq-test/implant-doctor.html', '<script src="implant-doctor-patient.js"></script>'],
];

for (const [path, tag] of pages) {
  const source = await readFile(path, 'utf8');
  if (source.includes(tag)) continue;
  if (!source.includes('</body>')) throw new Error(`${path}: closing body tag not found`);
  await writeFile(path, source.replace('</body>', `${tag}\n</body>`), 'utf8');
}
