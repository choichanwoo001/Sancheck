import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setBookRecognitionClientForTests } from '../agent/bridges/bookRecognitionBridge'
import { SERENDIPITY_BROWSE_DWELL_MS } from '../config/constants'
import { DEMO_BOOKS } from '../data/demoScenario'
import { BookRecognitionPanel } from './BookRecognitionPanel'

let mockCameraActive = false
let startMock = vi.fn()
let stopMock = vi.fn()
let captureFrameMock = vi.fn(() => 'frame')

vi.mock('../hooks/useBookRecognitionCamera', () => ({
  useBookRecognitionCamera: () => ({
    videoRef: { current: null },
    isActive: mockCameraActive,
    error: null,
    start: startMock,
    stop: stopMock,
    captureFrameBase64: captureFrameMock,
  }),
}))

vi.mock('../hooks/useGestureRecognition', () => ({
  useGestureRecognition: () => ({
    loading: false,
    error: null,
    previewGesture: null,
    previewStreak: 0,
  }),
}))

describe('BookRecognitionPanel dwell countdown', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockCameraActive = false
    startMock = vi.fn()
    stopMock = vi.fn()
    captureFrameMock = vi.fn(() => 'frame')
    setBookRecognitionClientForTests(null)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
    setBookRecognitionClientForTests(null)
  })

  it('reports browse interest once after the active demo book is viewed for 10 seconds', () => {
    mockCameraActive = true
    const onBrowseInterestDetected = vi.fn()
    const activeBook = { title: '단 한 사람', author: '최진영' }

    render(
      <BookRecognitionPanel
        busy={false}
        activeBook={activeBook}
        dwellCountdownActive
        dwellCountdownMs={10_000}
        trackBrowseInterest
        onBrowseInterestDetected={onBrowseInterestDetected}
      />,
    )

    act(() => {
      vi.advanceTimersByTime(10_000)
    })

    expect(onBrowseInterestDetected).toHaveBeenCalledTimes(1)
    expect(onBrowseInterestDetected).toHaveBeenCalledWith(activeBook)

    act(() => {
      vi.advanceTimersByTime(5_000)
    })

    expect(onBrowseInterestDetected).toHaveBeenCalledTimes(1)
  })

  it('does not count dwell time while the camera is off', () => {
    const onBrowseInterestDetected = vi.fn()

    render(
      <BookRecognitionPanel
        busy={false}
        activeBook={{ title: '단 한 사람', author: '최진영' }}
        dwellCountdownActive
        dwellCountdownMs={10_000}
        trackBrowseInterest
        onBrowseInterestDetected={onBrowseInterestDetected}
      />,
    )

    act(() => {
      vi.advanceTimersByTime(15_000)
    })

    expect(onBrowseInterestDetected).not.toHaveBeenCalled()
  })

  it('starts the camera and enables gestures automatically when requested', async () => {
    const { container } = render(
      <BookRecognitionPanel
        busy={false}
        autoStartCamera
        autoEnableGestures
      />,
    )

    await act(async () => {})

    expect(startMock).toHaveBeenCalledTimes(1)
    const gestureToggle = container.querySelector('.bookRecognitionGestureToggle')
    expect(gestureToggle).toBeNull()
  })
})

describe('BookRecognitionPanel serendipity browse scan', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockCameraActive = true
    captureFrameMock = vi.fn(() => 'frame')
    setBookRecognitionClientForTests({
      identifyBook: vi.fn(async () => ({
        ok: true,
        title: '단 한 사람',
        author: '최진영',
        message: 'ok',
      })),
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    setBookRecognitionClientForTests(null)
  })

  it('calls onSerendipityBrowseComplete after the configured dwell delay once 단 한 사람 is first recognized', async () => {
    const onSerendipityBrowseComplete = vi.fn()

    render(
      <BookRecognitionPanel
        busy={false}
        serendipityBrowseScan
        targetBookTitle="단 한 사람"
        dwellAfterRecognitionMs={SERENDIPITY_BROWSE_DWELL_MS}
        onSerendipityBrowseComplete={onSerendipityBrowseComplete}
      />,
    )

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500)
    })

    expect(onSerendipityBrowseComplete).not.toHaveBeenCalled()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(SERENDIPITY_BROWSE_DWELL_MS)
    })

    expect(onSerendipityBrowseComplete).toHaveBeenCalledTimes(1)
    expect(onSerendipityBrowseComplete).toHaveBeenCalledWith({
      title: '단 한 사람',
      author: '최진영',
    })
  })

  it('does not start countdown when recognition fails', async () => {
    setBookRecognitionClientForTests({
      identifyBook: vi.fn(async () => ({
        ok: false,
        message: 'fail',
        errorCode: 'BOOK_NOT_RECOGNIZED',
      })),
    })
    const onSerendipityBrowseComplete = vi.fn()

    render(
      <BookRecognitionPanel
        busy={false}
        serendipityBrowseScan
        targetBookTitle="단 한 사람"
        onSerendipityBrowseComplete={onSerendipityBrowseComplete}
      />,
    )

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000)
    })

    expect(onSerendipityBrowseComplete).not.toHaveBeenCalled()
  })

  it('ignores non-target book titles', async () => {
    setBookRecognitionClientForTests({
      identifyBook: vi.fn(async () => ({
        ok: true,
        title: '오직 두 사람',
        author: '김영하',
        message: 'ok',
      })),
    })
    const onSerendipityBrowseComplete = vi.fn()

    render(
      <BookRecognitionPanel
        busy={false}
        serendipityBrowseScan
        targetBookTitle="단 한 사람"
        onSerendipityBrowseComplete={onSerendipityBrowseComplete}
      />,
    )

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000)
    })

    expect(onSerendipityBrowseComplete).not.toHaveBeenCalled()
  })

  it('does not display recognized books outside the three scenario recognition books', async () => {
    setBookRecognitionClientForTests({
      identifyBook: vi.fn(async () => ({
        ok: true,
        title: DEMO_BOOKS.alternative.title,
        author: DEMO_BOOKS.alternative.authors,
        message: 'ok',
      })),
    })

    const { container } = render(
      <BookRecognitionPanel
        busy={false}
      />,
    )

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000)
    })

    expect(container.querySelector('.bookRecognitionDetected')).toBeNull()
  })
})
