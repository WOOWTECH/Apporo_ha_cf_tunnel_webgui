import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PaasLink from '../PaasLink.vue'

// The page runs behind Home Assistant Ingress: every API call must stay
// inside the per-session prefix the document was served from.
const INGRESS = 'http://homeassistant.local:8123/api/hassio_ingress/abc123/'
const PORTAL = 'https://www.apporo.ai/woow#/workspaces'

const BOOTSTRAP = {
  authorized: false,
  portal_url: PORTAL,
  connection: null,
  release_pending: false,
}

const ROUTE = { hostname: 'ha.example.com', public: true, protected: false, awaiting_publication: false }

const LINKED = {
  bootstrap: { ...BOOTSTRAP, authorized: true, connection: { access_id: 7, workspace_id: 3, name: 'Home access' } },
  workspaces: { workspaces: [{ id: 3, name: 'My home', portal_url: 'https://www.apporo.ai/woow#/workspace/3' }] },
  accesses: { accesses: [{ id: 7, name: 'Home access', state: 'active' }] },
  review: {
    ready: true,
    issues: [],
    public_routes: ['ha.example.com'],
    awaiting_publication: false,
    access: {
      id: 7,
      name: 'Home access',
      state: 'active',
      binding_state: 'claimed',
      subscription: { state: 'in_progress', plan_name: 'Starter', ac_max_access_seats: 0, ac_used_access_seats: 0 },
      routes: [ROUTE],
    },
    portal_access_url: 'https://www.apporo.ai/woow#/workspace/3/security-access/7/access',
    portal_routes_url: 'https://www.apporo.ai/woow#/workspace/3/security-access/7/application',
  },
  status: {
    connected: true,
    subscription: { state: 'in_progress' },
    access_ready: true,
    service_ready: true,
    public_routes: ['ha.example.com'],
    routes: [ROUTE],
    awaiting_publication: false,
    issues: [],
    tunnel_status: 'running',
    checked_at: 1700000000,
    external: [{ hostname: 'ha.example.com', status: 'public_response', http_status: 200 }],
  },
}

function ok(body: unknown) {
  return { ok: true, json: async () => body }
}

function mountPage() {
  return mount(PaasLink, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
}

function link(wrapper: ReturnType<typeof mountPage>, text: string) {
  return wrapper.findAll('a').find((a) => a.text().includes(text))!
}

describe('PaasLink', () => {
  beforeEach(() => {
    const base = document.createElement('base')
    base.href = INGRESS
    document.head.append(base)
  })
  afterEach(() => {
    document.head.querySelector('base')?.remove()
    vi.unstubAllGlobals()
  })

  it('explains the Apporo Security Access link and opens the portal the backend returns', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === `${INGRESS}api/paas/bootstrap`) return ok(BOOTSTRAP)
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountPage()
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Link this Home Assistant to Apporo Security Access')
    expect(link(wrapper, 'Subscribe on Apporo').attributes('href')).toBe(PORTAL)
  })

  it('falls back to the Apporo portal when the backend cannot be read', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 502, json: async () => ({ detail: 'down' }) })))
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('down')
    expect(link(wrapper, 'Subscribe on Apporo').attributes('href')).toBe(PORTAL)
  })

  it('shows the device code and the verification page the platform returns', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === `${INGRESS}api/paas/bootstrap`) return ok(BOOTSTRAP)
      if (url === `${INGRESS}api/paas/authorization` && init?.method === 'POST') {
        return ok({ user_code: 'WDJB-MJHT', verification_url: 'https://www.apporo.ai/device?user_code=WDJB-MJHT', expires_in: 900, interval: 5 })
      }
      throw new Error(`unexpected fetch ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === 'Get device code')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('WDJB-MJHT')
    expect(wrapper.text()).toContain('Waiting for you to allow the connection on Apporo')
    expect(link(wrapper, 'Open the device page').attributes('href')).toBe('https://www.apporo.ai/device?user_code=WDJB-MJHT')
    wrapper.unmount() // clears the pending authorization poll
  })

  it('reviews a linked service and its status in English', async () => {
    const replies: Record<string, unknown> = {
      [`${INGRESS}api/paas/bootstrap`]: LINKED.bootstrap,
      [`${INGRESS}api/paas/workspaces`]: LINKED.workspaces,
      [`${INGRESS}api/paas/workspaces/3/accesses`]: LINKED.accesses,
      [`${INGRESS}api/paas/accesses/7/review`]: LINKED.review,
      [`${INGRESS}api/paas/connection/status`]: LINKED.status,
    }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url in replies) return ok(replies[url])
      throw new Error(`unexpected fetch ${url}`)
    }))
    const wrapper = mountPage()
    await flushPromises()
    await flushPromises()
    const text = wrapper.text()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(text).toContain('✓ Apporo account connected')
    expect(text).toContain('Home access · Ready to connect (includes public hostnames)')
    expect(text).toContain('Subscription: Starter (Active) · Service: Active · Binding: Bound to one device')
    expect(text).toContain('Access seats: 0 of 0 in use.')
    expect(text).toContain('Public route, Cloudflare Access not enabled')
    expect(text).toContain('Not protected by Cloudflare Access: ha.example.com.')
    expect(text).toContain('✓ Linked to Home access.')
    expect(text).toContain('1 public hostname (no Access)')
    expect(text).toContain('Online')
    expect(text).toMatch(/Checked Nov \d{1,2}, 2023/)
    expect(text).toContain('Public route answers directly; make sure the origin service has its own login')
    expect(link(wrapper, 'Manage routes on Apporo').attributes('href')).toBe(LINKED.review.portal_routes_url)
    expect(link(wrapper, 'Access protection (optional)').attributes('href')).toBe(LINKED.review.portal_access_url)
  })
})
