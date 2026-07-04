import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMediaSessionMicToggle } from './useMediaSessionMicToggle'

function installMediaSession(
  overrides: Partial<{
    setActionHandler: (action: string, handler: MediaSessionActionHandler | null) => void
    setMicrophoneActive: (active: boolean) => Promise<void>
  }> = {},
) {
  const originalDescriptor = Object.getOwnPropertyDescriptor(Navigator.prototype, 'mediaSession')
  const handlers: Record<string, MediaSessionActionHandler | null> = {}
  const mediaSession = {
    setActionHandler: vi.fn((action: string, handler: MediaSessionActionHandler | null) => {
      overrides.setActionHandler?.(action, handler)
      handlers[action] = handler
    }),
    setMicrophoneActive: vi.fn((active: boolean) => {
      if (overrides.setMicrophoneActive) return overrides.setMicrophoneActive(active)
      return Promise.resolve()
    }),
  }

  Object.defineProperty(Navigator.prototype, 'mediaSession', {
    configurable: true,
    get: () => mediaSession,
  })

  return {
    handlers,
    mediaSession,
    restore: () => {
      if (originalDescriptor) {
        Object.defineProperty(Navigator.prototype, 'mediaSession', originalDescriptor)
      } else {
        delete (Navigator.prototype as { mediaSession?: MediaSession }).mediaSession
      }
    },
  }
}

describe('useMediaSessionMicToggle', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('registers microphone and media key actions to toggle the mic', () => {
    const fake = installMediaSession()
    const onToggle = vi.fn()

    const { unmount } = renderHook(() =>
      useMediaSessionMicToggle({ enabled: true, isMicOn: false, onToggle }),
    )

    expect(fake.mediaSession.setActionHandler).toHaveBeenCalledWith('togglemicrophone', expect.any(Function))
    expect(fake.mediaSession.setActionHandler).toHaveBeenCalledWith('play', expect.any(Function))
    expect(fake.mediaSession.setActionHandler).toHaveBeenCalledWith('pause', expect.any(Function))

    fake.handlers.togglemicrophone?.({ action: 'togglemicrophone' } as unknown as MediaSessionActionDetails)
    fake.handlers.play?.({ action: 'play' } as MediaSessionActionDetails)
    fake.handlers.pause?.({ action: 'pause' } as MediaSessionActionDetails)

    expect(onToggle).toHaveBeenCalledTimes(3)

    unmount()

    expect(fake.mediaSession.setActionHandler).toHaveBeenCalledWith('togglemicrophone', null)
    expect(fake.mediaSession.setActionHandler).toHaveBeenCalledWith('play', null)
    expect(fake.mediaSession.setActionHandler).toHaveBeenCalledWith('pause', null)

    fake.restore()
  })

  it('ignores unsupported media session actions and keeps registering supported actions', () => {
    const fake = installMediaSession({
      setActionHandler: (action) => {
        if (action === 'togglemicrophone') throw new TypeError('unsupported action')
      },
    })
    const onToggle = vi.fn()

    expect(() => {
      renderHook(() => useMediaSessionMicToggle({ enabled: true, isMicOn: false, onToggle }))
    }).not.toThrow()

    expect(fake.handlers.togglemicrophone).toBeUndefined()
    expect(fake.handlers.play).toEqual(expect.any(Function))
    expect(fake.handlers.pause).toEqual(expect.any(Function))

    fake.restore()
  })

  it('syncs microphone active state when the browser supports it', () => {
    const fake = installMediaSession()
    const onToggle = vi.fn()

    const { rerender } = renderHook(
      ({ isMicOn }) => useMediaSessionMicToggle({ enabled: true, isMicOn, onToggle }),
      { initialProps: { isMicOn: false } },
    )

    expect(fake.mediaSession.setMicrophoneActive).toHaveBeenLastCalledWith(false)

    rerender({ isMicOn: true })

    expect(fake.mediaSession.setMicrophoneActive).toHaveBeenLastCalledWith(true)

    fake.restore()
  })
})
