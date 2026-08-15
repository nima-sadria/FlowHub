// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import type { AuthUser } from '../../auth'
import UserbackWidget from './UserbackWidget'

const identify = vi.fn()

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
    identify.mockReset()
    delete (window as { Userback?: unknown }).Userback
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    delete (window as { Userback?: unknown }).Userback
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('identifies the signed-in user once the widget is already loaded', async () => {
    window.Userback = { identify } as never
    await act(async () => {
      root.render(<UserbackWidget user={user} />)
      await flush()
    })
    expect(identify).toHaveBeenCalledTimes(1)
    expect(identify.mock.calls[0]?.[0]).toBe('42')
  })

  it('sends only safe identity metadata - internal id, username, and email', async () => {
    window.Userback = { identify } as never
    await act(async () => {
      root.render(<UserbackWidget user={user} />)
      await flush()
    })
    expect(identify.mock.calls[0]?.[1]).toEqual({ name: 'jane.doe', email: 'jane.doe@example.com' })
  })

  it('never includes tokens, secrets, or other credential data in the identify payload', async () => {
    window.Userback = { identify } as never
    await act(async () => {
      root.render(<UserbackWidget user={user} />)
      await flush()
    })
    const payload = JSON.stringify(identify.mock.calls[0]).toLowerCase()
    for (const forbidden of ['token', 'password', 'cookie', 'secret', 'authorization', 'credential']) {
      expect(payload).not.toContain(forbidden)
    }
  })

  it('waits for the widget to finish loading before identifying', async () => {
    vi.useFakeTimers()
    await act(async () => {
      root.render(<UserbackWidget user={user} />)
    })
    expect(identify).not.toHaveBeenCalled()

    window.Userback = { identify } as never
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250)
    })
    expect(identify).toHaveBeenCalledTimes(1)
  })

  it('gives up quietly if the widget never loads (missing/blocked configuration)', async () => {
    vi.useFakeTimers()
    await act(async () => {
      root.render(<UserbackWidget user={user} />)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000)
    })
    expect(identify).not.toHaveBeenCalled()
    expect(container.innerHTML).toBe('')
  })

  it('does not throw when the loaded widget rejects the identify call', async () => {
    window.Userback = {
      identify: () => { throw new Error('boom') },
    } as never
    await expect(act(async () => {
      root.render(<UserbackWidget user={user} />)
      await flush()
    })).resolves.not.toThrow()
  })

  it('does not re-identify on re-render when identity has not changed', async () => {
    window.Userback = { identify } as never
    await act(async () => {
      root.render(<UserbackWidget user={user} />)
      await flush()
    })
    await act(async () => {
      root.render(<UserbackWidget user={{ ...user }} />)
      await flush()
    })
    expect(identify).toHaveBeenCalledTimes(1)
  })

  it('re-identifies when the user identity actually changes', async () => {
    window.Userback = { identify } as never
    await act(async () => {
      root.render(<UserbackWidget user={user} />)
      await flush()
    })
    await act(async () => {
      root.render(<UserbackWidget user={{ ...user, email: 'new-email@example.com' }} />)
      await flush()
    })
    expect(identify).toHaveBeenCalledTimes(2)
    expect(identify.mock.calls[1]?.[1]).toEqual({ name: 'jane.doe', email: 'new-email@example.com' })
  })
})
