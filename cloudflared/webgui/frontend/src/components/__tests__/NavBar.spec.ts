import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import NavBar from '../NavBar.vue'

const HEALTH = {
  status: 'ok',
  supervisor_connected: true,
  addon_version: '1.0.0',
  addon_state: 'started',
  tunnel: { status: 'running', ready_connections: 4, metrics_reachable: true },
  restart_error: null,
}

describe('NavBar', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the Apporo wordmark and links the Apporo Link page', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => HEALTH })))
    const wrapper = mount(NavBar, {
      global: {
        plugins: [createPinia()],
        stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } },
        mocks: { $route: { path: '/paas' } },
      },
    })
    await flushPromises()
    expect(wrapper.get('[data-test="wordmark"]').text()).toBe('Apporo CF Tunnel Web')
    const paas = wrapper.findAll('a').find((a) => a.attributes('href') === '/paas')!
    expect(paas.text()).toBe('Apporo Link')
    expect(paas.classes()).toContain('text-brand-700')
    expect(wrapper.text()).toContain('running')
    wrapper.unmount() // stops the health polling
  })
})
