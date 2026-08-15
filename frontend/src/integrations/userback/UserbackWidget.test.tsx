// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import type { AuthUser } from '../../auth'
import UserbackWidget from './UserbackWidget'

const initUserback = vi.fn()
const destroy = vi.fn()

vi.mock('@userback/widget', () => ({
  default: (...args: unknown[]) => initUserback(...args) as unknown,
}))

const user: AuthUser = {
  id: 42,
  username: 'jane.doe',
  email: 'jane.doe@example.com',
  role: 'admin',
  is_admin: true,
  is_super_admin: false,
  permissions: {},
}

async function flush() {
  await new Promise(resolve => setTimeout(resolve, 0))
}

describe('UserbackWidget', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    initUserback.mockReset()
    destroy.mockReset()
    initUserback.mockResolvedValue({ destroy })
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.restoreAllMocks()
  })

  it('initializes for an authenticated user once an access token is configured', async () => {
    await act(async () => {
      root.render(<UserbackWidget user={user} accessToken="ub-token-123" />)
      await flush()
    })
    expect(initUserback).toHaveBeenCalledTimes(1)
    expect(initUserback.mock.calls[0]?.[0]).toBe('ub-token-123')
  })

  it('sends only safe identity metadata - internal id, username, and email', async () => {
    await act(async () => {
      root.render(<UserbackWidget user={user} accessToken="ub-token-123" />)
      await flush()
    })
    const options = initUserback.mock.calls[0]?.[1] as Record<string, unknown>
    expect(options).toEqual({
      user_data: {
        id: '42',
        info: {
          name: 'jane.doe',
          email: 'jane.doe@example.com',
        },
      },
    })
  })

  it('never includes tokens, secrets, or other credential data in the payload', async () => {
    await act(async () => {
      root.render(<UserbackWidget user={user} accessToken="ub-token-123" />)
      await flush()
    })
    const payload = JSON.stringify(initUserback.mock.calls[0]?.[1]).toLowerCase()
    for (const forbidden of ['token', 'password', 'cookie', 'secret', 'authorization', 'credential']) {
      expect(payload).not.toContain(forbidden)
    }
  })

  it('does not initialize when no access token is configured (e.g. unauthenticated/login surface)', async () => {
    await act(async () => {
      root.render(<UserbackWidget user={user} accessToken="" />)
      await flush()
    })
    expect(initUserback).not.toHaveBeenCalled()
  })

  it('does not initialize when the access token is undefined', async () => {
    await act(async () => {
      root.render(<UserbackWidget user={user} accessToken={undefined} />)
      await flush()
    })
    expect(initUserback).not.toHaveBeenCalled()
  })

  it('destroys the widget on unmount', async () => {
    await act(async () => {
      root.render(<UserbackWidget user={user} accessToken="ub-token-123" />)
      await flush()
    })
    expect(initUserback).toHaveBeenCalledTimes(1)
    await act(async () => {
      root.unmount()
      await flush()
    })
    expect(destroy).toHaveBeenCalledTimes(1)
  })

  it('does not throw FlowHub when the Userback SDK fails to load', async () => {
    initUserback.mockRejectedValueOnce(new Error('network blocked'))
    await expect(act(async () => {
      root.render(<UserbackWidget user={user} accessToken="ub-token-123" />)
      await flush()
    })).resolves.not.toThrow()
  })

  it('missing Userback configuration renders nothing and never touches the SDK', async () => {
    await act(async () => {
      root.render(<UserbackWidget user={user} />)
      await flush()
    })
    expect(container.innerHTML).toBe('')
    expect(initUserback).not.toHaveBeenCalled()
  })
})
