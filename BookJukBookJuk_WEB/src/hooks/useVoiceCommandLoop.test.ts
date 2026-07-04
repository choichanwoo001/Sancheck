import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VOICE_RESUME_DELAY_MS } from '../config/voiceCommand'
import { useVoiceCommandLoop } from './useVoiceCommandLoop'

class MockSpeechRecognition {
  static instances: MockSpeechRecognition[] = []
  static startImpl: ((instance: MockSpeechRecognition) => void) | null = null

  continuous = false
  interimResults = false
  lang = ''
  onend: ((this: SpeechRecognition, ev: Event) => void) | null = null
  onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => void) | null = null
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null = null
  onstart: ((this: SpeechRecognition, ev: Event) => void) | null = null
  start = vi.fn(() => {
    MockSpeechRecognition.startImpl?.(this)
  })
  abort = vi.fn()
  stop = vi.fn()

  constructor() {
    MockSpeechRecognition.instances.push(this)
  }
}

describe('useVoiceCommandLoop mic toggle state', () => {
  const originalSpeechRecognition = window.SpeechRecognition
  const originalWebkitSpeechRecognition = window.webkitSpeechRecognition

  beforeEach(() => {
    vi.useFakeTimers()
    MockSpeechRecognition.instances = []
    MockSpeechRecognition.startImpl = null
    Object.defineProperty(window, 'SpeechRecognition', {
      configurable: true,
      writable: true,
      value: MockSpeechRecognition as unknown as SpeechRecognitionConstructor,
    })
    Object.defineProperty(window, 'webkitSpeechRecognition', {
      configurable: true,
      writable: true,
      value: undefined,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    Object.defineProperty(window, 'SpeechRecognition', {
      configurable: true,
      writable: true,
      value: originalSpeechRecognition,
    })
    Object.defineProperty(window, 'webkitSpeechRecognition', {
      configurable: true,
      writable: true,
      value: originalWebkitSpeechRecognition,
    })
  })

  it('stores mic-on intent while paused without starting recognition', () => {
    const { result } = renderHook(() =>
      useVoiceCommandLoop({ onUtteranceComplete: vi.fn(), paused: true }),
    )

    act(() => {
      result.current.startMic()
    })

    expect(result.current.isMicOn).toBe(true)
    expect(MockSpeechRecognition.instances).toHaveLength(0)
  })

  it('starts recognition after a paused mic-on intent resumes', () => {
    const { result, rerender } = renderHook(
      ({ paused }) => useVoiceCommandLoop({ onUtteranceComplete: vi.fn(), paused }),
      { initialProps: { paused: true } },
    )

    act(() => {
      result.current.startMic()
    })

    expect(result.current.isMicOn).toBe(true)
    expect(MockSpeechRecognition.instances).toHaveLength(0)

    rerender({ paused: false })

    act(() => {
      vi.advanceTimersByTime(VOICE_RESUME_DELAY_MS)
    })

    expect(MockSpeechRecognition.instances).toHaveLength(1)
    expect(MockSpeechRecognition.instances[0].start).toHaveBeenCalledTimes(1)
  })

  it('turns the mic off immediately while paused', () => {
    const { result } = renderHook(() =>
      useVoiceCommandLoop({ onUtteranceComplete: vi.fn(), paused: true }),
    )

    act(() => {
      result.current.startMic()
    })
    act(() => {
      result.current.stopMic()
    })

    expect(result.current.isMicOn).toBe(false)
    expect(MockSpeechRecognition.instances).toHaveLength(0)
  })

  it('starts from a fresh recognizer when the mic is turned back on', async () => {
    const { result } = renderHook(() =>
      useVoiceCommandLoop({ onUtteranceComplete: vi.fn() }),
    )

    act(() => {
      result.current.startMic()
    })

    const first = MockSpeechRecognition.instances[0]
    expect(first.start).toHaveBeenCalledTimes(1)

    act(() => {
      result.current.stopMic()
    })
    expect(first.abort).toHaveBeenCalledTimes(1)
    expect(first.stop).not.toHaveBeenCalled()
    expect(first.onend).toBeNull()
    expect(first.onerror).toBeNull()
    expect(first.onresult).toBeNull()

    act(() => {
      result.current.startMic()
    })

    expect(result.current.isMicOn).toBe(true)
    expect(MockSpeechRecognition.instances).toHaveLength(2)
    expect(MockSpeechRecognition.instances[1].start).toHaveBeenCalledTimes(1)

    await act(async () => {
      first.onend?.call(first as unknown as SpeechRecognition, new Event('end'))
    })

    expect(MockSpeechRecognition.instances).toHaveLength(2)
  })

  it('restarts after the browser naturally ends a continuous recognition session', () => {
    const { result } = renderHook(() =>
      useVoiceCommandLoop({ onUtteranceComplete: vi.fn() }),
    )

    act(() => {
      result.current.startMic()
    })

    const first = MockSpeechRecognition.instances[0]

    act(() => {
      first.onend?.call(first as unknown as SpeechRecognition, new Event('end'))
    })

    expect(result.current.isMicOn).toBe(true)
    expect(MockSpeechRecognition.instances).toHaveLength(1)

    act(() => {
      vi.advanceTimersByTime(VOICE_RESUME_DELAY_MS)
    })

    expect(MockSpeechRecognition.instances).toHaveLength(2)
    expect(MockSpeechRecognition.instances[1].start).toHaveBeenCalledTimes(1)
  })

  it('keeps the mic intent on and retries when recognition start fails transiently', () => {
    MockSpeechRecognition.startImpl = vi
      .fn()
      .mockImplementationOnce(() => {
        throw new Error('transient start failure')
      })

    const { result } = renderHook(() =>
      useVoiceCommandLoop({ onUtteranceComplete: vi.fn() }),
    )

    act(() => {
      result.current.startMic()
    })

    expect(result.current.isMicOn).toBe(true)
    expect(MockSpeechRecognition.instances).toHaveLength(1)

    act(() => {
      vi.advanceTimersByTime(VOICE_RESUME_DELAY_MS)
    })

    expect(result.current.isMicOn).toBe(true)
    expect(MockSpeechRecognition.instances).toHaveLength(2)
    expect(MockSpeechRecognition.instances[1].start).toHaveBeenCalledTimes(1)
  })
})
