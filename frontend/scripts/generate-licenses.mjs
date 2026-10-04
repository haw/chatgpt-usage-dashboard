// Collects the licenses of the client's third-party packages into
// src/generated/third-party-licenses.json (shown under 取込と設定 > バージョン情報).
// Covers the production dependency tree of package-lock.json: everything that can end up
// in the browser bundle. Runs before dev, build and test (see the pre* scripts).
import { chownSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const lock = JSON.parse(readFileSync(join(root, 'package-lock.json'), 'utf8'))
const LICENSE_FILE = /^(licen[cs]e|copying|notice)([.\-_].*)?$/i

function licenseName(manifest) {
  if (typeof manifest.license === 'string') return manifest.license
  if (manifest.license?.type) return manifest.license.type
  return (manifest.licenses ?? []).map((entry) => entry.type).filter(Boolean).join(' OR ')
}

function homepage(manifest) {
  if (manifest.homepage) return manifest.homepage
  const repository = typeof manifest.repository === 'string' ? manifest.repository : manifest.repository?.url
  if (!repository) return ''
  if (/^[\w.-]+\/[\w.-]+$/.test(repository)) return `https://github.com/${repository}`
  return repository.replace(/^git\+/, '').replace(/^git:\/\//, 'https://').replace(/\.git$/, '')
}

const packages = new Map()
for (const [path, entry] of Object.entries(lock.packages)) {
  if (!path.startsWith('node_modules/') || entry.dev || entry.devOptional) continue
  const dir = join(root, path)
  if (!existsSync(join(dir, 'package.json'))) continue // optional package for another platform
  const manifest = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8'))
  const name = manifest.name ?? path.split('node_modules/').pop()
  const version = manifest.version ?? entry.version
  const text = readdirSync(dir)
    .filter((file) => LICENSE_FILE.test(file))
    .sort()
    .map((file) => readFileSync(join(dir, file), 'utf8').trim())
    .join('\n\n')
  packages.set(`${name}@${version}`, { name, version, license: licenseName(manifest), homepage: homepage(manifest), text })
}

const list = [...packages.values()].sort((a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version))
const out = join(root, 'src', 'generated', 'third-party-licenses.json')
mkdirSync(dirname(out), { recursive: true })
writeFileSync(out, JSON.stringify(list))
// The dev and test containers run as root on a bind mount; hand the output to the project's owner.
if (process.getuid?.() === 0) {
  const { uid, gid } = statSync(root)
  for (const path of [dirname(out), out]) chownSync(path, uid, gid)
}
console.log(`third-party licenses: ${list.length} packages -> ${out.slice(root.length + 1)}`)
