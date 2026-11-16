import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'fs'
import { join, relative, resolve } from 'path'

// Guards the Apporo fork against upstream merges: the UI is English only and
// carries no WOOW branding. Tests themselves are not scanned.
const FRONTEND = resolve(__dirname, '../..')
const CJK = /[　-〿㐀-䶿一-鿿豈-﫿＀-￯]/
// "PaaS" is what the upstream UI calls WOOW's platform; here it is "Apporo".
// API paths (api/paas/...) and the /paas route are lowercase and stay.
const OLD_BRAND = [/woowtech/i, /\bW(OOW|oow)\b/, /\bPaaS\b/]
// The Cloudflare orange is gone from tailwind.config.js, so an upstream
// `bg-cf-orange` would silently render without any colour.
const OFF_PALETTE = [/\bcf-(orange|dark)\b/, /\borange-\d/, /#F6821F/i]

function uiSources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return name === '__tests__' ? [] : uiSources(path)
    return /\.(vue|ts)$/.test(name) ? [path] : []
  })
}

function offending(patterns: RegExp[]): string[] {
  const files = [...uiSources(join(FRONTEND, 'src')), join(FRONTEND, 'index.html')]
  return files.flatMap((file) =>
    readFileSync(file, 'utf8')
      .split('\n')
      .flatMap((line, i) => (patterns.some((p) => p.test(line)) ? [`${relative(FRONTEND, file)}:${i + 1}`] : []))
  )
}

describe('Apporo branding', () => {
  it('has no Chinese text in the UI sources', () => {
    expect(offending([CJK])).toEqual([])
  })

  it('has no WOOW branding in the UI sources', () => {
    expect(offending(OLD_BRAND)).toEqual([])
  })

  it('uses the Apporo palette, not the Cloudflare orange', () => {
    expect(offending(OFF_PALETTE)).toEqual([])
  })

  it('names the page Apporo CF Tunnel Web', () => {
    expect(readFileSync(join(FRONTEND, 'index.html'), 'utf8')).toContain('<title>Apporo CF Tunnel Web</title>')
  })

  it('uses the Apporo icon', () => {
    const icon = readFileSync(join(FRONTEND, 'public', 'favicon.svg'), 'utf8')
    expect(icon).toContain('#8B6B24')
    expect(icon).not.toMatch(/#F6821F/i)
  })
})
