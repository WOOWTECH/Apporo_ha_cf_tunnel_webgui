import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api, apiUrl, wsUrl } from '../api'

// Home Assistant serves the GUI under a per-session Ingress prefix; every
// request must stay inside it, so paths resolve against the document.
function useBase(href: string) {
  document.head.querySelector('base')?.remove()
  const base = document.createElement('base')
  base.href = href
  document.head.append(base)
}

describe('api helpers under Home Assistant Ingress', () => {
  beforeEach(() => useBase('http://homeassistant.local:8123/api/hassio_ingress/abc123/'))
  afterEach(() => {
    document.head.querySelector('base')?.remove()
    vi.unstubAllGlobals()
  })

  it('resolves API paths inside the ingress prefix', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({ status: 'ok' }) }))
    vi.stubGlobal('fetch', fetchMock)
    expect(apiUrl('api/health')).toBe('http://homeassistant.local:8123/api/hassio_ingress/abc123/api/health')
    await api('api/paas/bootstrap')
    expect((fetchMock.mock.calls as unknown as [string][])[0][0]).toBe(
      'http://homeassistant.local:8123/api/hassio_ingress/abc123/api/paas/bootstrap'
    )
  })

  it('opens the log stream inside the ingress prefix, over wss on https', () => {
    expect(wsUrl('api/logs/stream')).toBe('ws://homeassistant.local:8123/api/hassio_ingress/abc123/api/logs/stream')
    useBase('https://ha.example.com/api/hassio_ingress/abc123/')
    expect(wsUrl('api/logs/stream')).toBe('wss://ha.example.com/api/hassio_ingress/abc123/api/logs/stream')
  })

  it('turns a FastAPI 422 detail list into field: message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 422,
      json: async () => ({ detail: [{ loc: ['body', 'tunnel_token'], msg: 'bad token', type: 'value_error' }] }),
    })))
    await expect(api('api/options', { method: 'PUT' })).rejects.toThrow('tunnel_token: bad token')
  })

  it('passes a string detail through', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 409,
      json: async () => ({ detail: 'Stop the local connection and finish releasing the remote binding first.' }),
    })))
    await expect(api('api/paas/authorization/revoke', { method: 'POST' })).rejects.toThrow(
      'Stop the local connection and finish releasing the remote binding first.'
    )
  })
})
