import { renderHook, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useTts } from './useTts'

class MockAudio {
  static urls: string[] = []

  preload = ''
  playbackRate = 1
  src = ''
  onended: (() => void) | null = null
  onerror: (() => void) | null = null
  error: MediaError | null = null

  constructor(url: string) {
    MockAudio.urls.push(url)
  }

  play = vi.fn(async () => {
    queueMicrotask(() => this.onended?.())
  })

  pause = vi.fn()
}

describe('useTts', () => {
  const originalAudio = globalThis.Audio
  const originalFetch = globalThis.fetch
  const originalCreateObjectUrl = URL.createObjectURL
  const originalRevokeObjectUrl = URL.revokeObjectURL

  beforeEach(() => {
    MockAudio.urls = []
    localStorage.clear()
    globalThis.Audio = MockAudio as unknown as typeof Audio
  })

  afterEach(() => {
    vi.restoreAllMocks()
    globalThis.Audio = originalAudio
    globalThis.fetch = originalFetch
    URL.createObjectURL = originalCreateObjectUrl
    URL.revokeObjectURL = originalRevokeObjectUrl
  })

  it('plays cached mp3 files through HTMLAudioElement', async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 200 })) as typeof fetch

    const { result } = renderHook(() => useTts())

    await act(async () => {
      await result.current.speakAndWait('준비되면 오케이 제스처를 취해주세요.')
    })

    expect(MockAudio.urls).toEqual(['/audio/tts/준비되면오케이제스처를취해주세요.mp3'])
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/audio/tts/준비되면오케이제스처를취해주세요.mp3',
      { method: 'HEAD' },
    )
  })

  it('plays OpenAI fallback audio through the same HTMLAudioElement path', async () => {
    vi.stubEnv('VITE_OPENAI_API_KEY', 'test-key')
    URL.createObjectURL = vi.fn(() => 'blob:tts-audio')
    URL.revokeObjectURL = vi.fn()
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(new Response(new Blob(['mp3']), { status: 200 })) as typeof fetch

    const { result } = renderHook(() => useTts())

    await act(async () => {
      await result.current.speakAndWait('캐시에 없는 안내')
    })

    expect(MockAudio.urls).toEqual(['blob:tts-audio'])
    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:tts-audio')
    expect(globalThis.fetch).toHaveBeenNthCalledWith(
      2,
      'https://api.openai.com/v1/audio/speech',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
