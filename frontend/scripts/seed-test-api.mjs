// Loads the synthetic fixtures into the no-login test API (compose service `test-api`) so the
// component tests see real response shapes. FIXTURES and BACKEND come from the environment.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const backend = process.env.BACKEND ?? 'http://localhost:8001'
const fixtures = process.env.FIXTURES ?? '../tests/fixtures'
const form = new FormData()
for (const name of ['workspace-tokens-2026-09.json', 'workspace-active-users-2026-09.json']) {
  form.append('files', new Blob([readFileSync(join(fixtures, name))], { type: 'application/json' }), name)
}
const response = await fetch(`${backend}/api/import`, { method: 'POST', body: form })
if (!response.ok) throw new Error(`seeding ${backend} failed: ${response.status} ${await response.text()}`)
console.log(`seeded ${backend} with the workspace fixtures`)
