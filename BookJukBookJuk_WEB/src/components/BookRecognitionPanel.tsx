import { useCallback, useEffect, useRef, useState } from 'react'

import { getBookRecognitionClient } from '../agent/bridges/bookRecognitionBridge'
import { DESTINATION_ARRIVAL_PAUSE_MS, SERENDIPITY_BROWSE_DWELL_MS } from '../config/constants'
import { findDemoBookByTitle } from '../data/demoScenario'
import { GESTURE_CONFIRM_FRAMES, GESTURE_LABELS_KO, type GestureId } from '../lib/gestureClassifiers'
import { useBookRecognitionCamera } from '../hooks/useBookRecognitionCamera'
import { useGestureRecognition } from '../hooks/useGestureRecognition'

export type RecognizedBookPreview = {
  title: string
  author?: string
}

export type BookRecognitionPanelProps = {
  busy: boolean
  /** 레거시 UI 캡처 (현재 패널에서는 미사용). */
  onCapture?: (
    reason: 'add' | 'remove' | 'browse',
    imageBase64: string,
    trigger?: 'gesture' | 'ui',
  ) => void | Promise<void>
  /** 표지 인식 후 제스처로 담기/빼기 (인식된 제목 기준). */
  onGestureBookDecision?: (
    reason: 'add' | 'remove',
    book: RecognizedBookPreview,
  ) => void | Promise<void>
  onBrowse?: (imageBase64: string) => void | Promise<void>
  onGestureConfirmed?: (gestureId: GestureId) => void
  /** 데모 시나리오: 서가/우연한 발견 구간에서 표시할 책. */
  activeBook?: RecognizedBookPreview | null
  /** 카메라 켜진 뒤 책 살펴보기 카운트다운 표시. */
  dwellCountdownActive?: boolean
  dwellCountdownMs?: number
  /** 카운트다운 완료 시 관심 있음으로 보고 (우연한 발견). */
  trackBrowseInterest?: boolean
  onBrowseInterestDetected?: (book: RecognizedBookPreview) => void
  /** 우연한 발견: serendipity_nav 중 카메라 ORB 스캔. */
  serendipityBrowseScan?: boolean
  targetBookTitle?: string
  dwellAfterRecognitionMs?: number
  onSerendipityBrowseComplete?: (book: RecognizedBookPreview) => void
  autoStartCamera?: boolean
  autoEnableGestures?: boolean
  scanEnabled?: boolean
  placement?: 'map' | 'chat'
}

const IDENTIFY_POLL_MS = 1400
const RECOGNITION_CONFIRM_MATCHES = 2
const SCENARIO_RECOGNITION_BOOK_KEYS = new Set(['serendipity', 'book2', 'book1'])

type ConfirmedScenarioBook = RecognizedBookPreview & {
  key: string
}

function titlesMatch(recognized: string, target: string): boolean {
  const def = findDemoBookByTitle(recognized)
  const targetDef = findDemoBookByTitle(target)
  if (def && targetDef) return def.key === targetDef.key
  const norm = (s: string) => s.trim().replace(/\s+/g, '')
  return norm(recognized) === norm(target)
}

function toDisplayScenarioBook(book: RecognizedBookPreview): ConfirmedScenarioBook | null {
  const def = findDemoBookByTitle(book.title)
  if (!def || !SCENARIO_RECOGNITION_BOOK_KEYS.has(def.key)) return null
  return {
    key: def.key,
    title: def.title,
    author: book.author?.trim() || def.authors,
  }
}

export function BookRecognitionPanel({
  busy,
  onGestureBookDecision,
  onGestureConfirmed,
  activeBook = null,
  dwellCountdownActive = false,
  dwellCountdownMs = DESTINATION_ARRIVAL_PAUSE_MS,
  trackBrowseInterest = false,
  onBrowseInterestDetected,
  serendipityBrowseScan = false,
  targetBookTitle,
  dwellAfterRecognitionMs = SERENDIPITY_BROWSE_DWELL_MS,
  onSerendipityBrowseComplete,
  autoStartCamera = false,
  scanEnabled = true,
  placement = 'map',
}: BookRecognitionPanelProps) {
  const [identifying, setIdentifying] = useState(false)
  const [recognizedBook, setRecognizedBook] = useState<RecognizedBookPreview | null>(null)
  const [countdownSec, setCountdownSec] = useState<number | null>(null)
  const scanInFlightRef = useRef(false)
  const interestReportedRef = useRef(false)
  const serendipityRecognizedRef = useRef(false)
  const serendipityBrowseCompleteRef = useRef(false)
  const autoStartAttemptedRef = useRef(false)
  const recognitionCandidateRef = useRef<{ key: string; count: number } | null>(null)

  const {
    videoRef,
    isActive,
    error,
    start,
    captureFrameBase64,
  } = useBookRecognitionCamera()

  useEffect(() => {
    if (!autoStartCamera || autoStartAttemptedRef.current || isActive) return
    autoStartAttemptedRef.current = true
    void start()
  }, [autoStartCamera, isActive, start])

  useEffect(() => {
    if (!serendipityBrowseScan) {
      serendipityRecognizedRef.current = false
      serendipityBrowseCompleteRef.current = false
    }
  }, [serendipityBrowseScan])

  useEffect(() => {
    interestReportedRef.current = false
    setCountdownSec(null)
    if (serendipityBrowseScan) return undefined
    if (!dwellCountdownActive || !isActive || !activeBook) return undefined

    const totalMs = dwellCountdownMs
    const startedAt = Date.now()
    setCountdownSec(Math.ceil(totalMs / 1000))

    const timerId = window.setInterval(() => {
      const remaining = Math.max(0, totalMs - (Date.now() - startedAt))
      setCountdownSec(Math.ceil(remaining / 1000))
      if (remaining <= 0) {
        window.clearInterval(timerId)
        if (trackBrowseInterest && !interestReportedRef.current) {
          interestReportedRef.current = true
          onBrowseInterestDetected?.(activeBook)
        }
      }
    }, 200)

    return () => window.clearInterval(timerId)
  }, [
    activeBook,
    dwellCountdownActive,
    dwellCountdownMs,
    isActive,
    onBrowseInterestDetected,
    serendipityBrowseScan,
    trackBrowseInterest,
  ])

  useEffect(() => {
    const isSerendipity = recognizedBook && (recognizedBook.title === '단 한 사람' || titlesMatch(recognizedBook.title, '단 한 사람'))
    if (!isSerendipity || serendipityBrowseCompleteRef.current) {
      if (!isSerendipity) setCountdownSec(null)
      return undefined
    }

    const totalMs = dwellAfterRecognitionMs
    const startedAt = Date.now()
    setCountdownSec(Math.ceil(totalMs / 1000))

    const timerId = window.setInterval(() => {
      const remaining = Math.max(0, totalMs - (Date.now() - startedAt))
      setCountdownSec(Math.ceil(remaining / 1000))
      if (remaining <= 0) {
        window.clearInterval(timerId)
        if (!serendipityBrowseCompleteRef.current) {
          serendipityBrowseCompleteRef.current = true
          onSerendipityBrowseComplete?.({
            title: recognizedBook.title,
            author: recognizedBook.author,
          })
        }
      }
    }, 200)

    return () => window.clearInterval(timerId)
  }, [dwellAfterRecognitionMs, onSerendipityBrowseComplete, recognizedBook])

  useEffect(() => {
    if (!scanEnabled) {
      setRecognizedBook(null)
      recognitionCandidateRef.current = null
    }
  }, [scanEnabled])

  useEffect(() => {
    if (!isActive || busy || identifying) return undefined
    if (!scanEnabled) return undefined

    const tick = async () => {
      if (scanInFlightRef.current) return
      if (serendipityBrowseScan && serendipityRecognizedRef.current) return
      const frame = captureFrameBase64()
      if (!frame) return

      scanInFlightRef.current = true
      try {
        const result = await getBookRecognitionClient().identifyBook({
          reason: serendipityBrowseScan ? 'browse' : 'add',
          imageBase64: frame,
        })
        if (result.ok && result.title?.trim()) {
          const rawBook = {
            title: result.title.trim(),
            author: result.author?.trim() || undefined,
          }
          const book = toDisplayScenarioBook(rawBook)
          if (!book) {
            recognitionCandidateRef.current = null
            setRecognizedBook(null)
            return
          }
          if (serendipityBrowseScan) {
            if (!targetBookTitle || !titlesMatch(book.title, targetBookTitle)) {
              recognitionCandidateRef.current = null
              return
            }
          }

          const prev = recognitionCandidateRef.current
          const count = prev?.key === book.key ? prev.count + 1 : 1
          recognitionCandidateRef.current = { key: book.key, count }
          if (count < RECOGNITION_CONFIRM_MATCHES) return

          if (serendipityBrowseScan) {
            serendipityRecognizedRef.current = true
          }
          setRecognizedBook(book)
        } else {
          recognitionCandidateRef.current = null
          setRecognizedBook(null)
        }
      } finally {
        scanInFlightRef.current = false
      }
    }

    void tick()
    const timerId = window.setInterval(() => {
      void tick()
    }, IDENTIFY_POLL_MS)
    return () => window.clearInterval(timerId)
  }, [
    busy,
    captureFrameBase64,
    identifying,
    isActive,
    scanEnabled,
    serendipityBrowseScan,
    targetBookTitle,
  ])

  const runGestureDecision = useCallback(
    (reason: 'add' | 'remove') => {
      if (busy || identifying || !onGestureBookDecision) return
      if (!recognizedBook) {
        return
      }
      setIdentifying(true)
      void Promise.resolve(onGestureBookDecision(reason, recognizedBook)).finally(() => {
        setIdentifying(false)
      })
    },
    [busy, identifying, onGestureBookDecision, recognizedBook],
  )

  const gestureEnabled = isActive && Boolean(onGestureConfirmed || onGestureBookDecision)

  const handleGestureConfirmed = useCallback(
    (gestureId: GestureId) => {
      onGestureConfirmed?.(gestureId)

      if (!gestureEnabled) return

      if (gestureId === 'thumbs_up') {
        runGestureDecision('add')
      } else if (gestureId === 'thumbs_down') {
        runGestureDecision('remove')
      }
    },
    [gestureEnabled, onGestureConfirmed, runGestureDecision],
  )

  const gesture = useGestureRecognition({
    videoRef,
    isActive,
    enabled: isActive && gestureEnabled && Boolean(onGestureConfirmed || onGestureBookDecision),
    onConfirmed: handleGestureConfirmed,
  })

  const previewLabel = gesture.previewGesture ? GESTURE_LABELS_KO[gesture.previewGesture] : null
  const showBrowseComplete =
    serendipityBrowseScan && countdownSec === 0 && serendipityBrowseCompleteRef.current

  return (
    <div
      className={`bookRecognitionPanel${placement === 'map' ? ' mapCameraPip' : ''}`}
      data-placement={placement}
    >
      <div className="bookRecognitionHeader">
        <span className="bookRecognitionTitle">책 표지 인식</span>
      </div>

      <div className="bookRecognitionPreviewWrap">
        <video
          ref={videoRef}
          className="bookRecognitionVideo"
          playsInline
          muted
          aria-label="책 표지 인식 카메라 미리보기"
        />
        {!isActive && (
          <div className="bookRecognitionVideoPlaceholder">카메라 미리보기</div>
        )}
        {isActive && countdownSec !== null && countdownSec > 0 && (
          <div className="bookRecognitionCountdownOverlay" aria-live="polite">
            <span className="bookRecognitionCountdownLabel">책 살펴보기</span>
            <span className="bookRecognitionCountdownValue">{countdownSec}초</span>
          </div>
        )}
        {isActive && showBrowseComplete && (
          <div className="bookRecognitionCountdownOverlay" aria-live="polite">
            <span className="bookRecognitionCountdownDone">관심 있음으로 기록됨</span>
          </div>
        )}
        {isActive && !showBrowseComplete && countdownSec === 0 && trackBrowseInterest && !serendipityBrowseScan && (
          <div className="bookRecognitionCountdownOverlay" aria-live="polite">
            <span className="bookRecognitionCountdownDone">관심 있음으로 기록됨</span>
          </div>
        )}
        {isActive && gestureEnabled && (
          <div className="bookRecognitionGestureOverlay" aria-live="polite">
            {gesture.loading ? (
              <span className="bookRecognitionGestureChip">제스처 로딩…</span>
            ) : previewLabel ? (
              <span className="bookRecognitionGestureChip" data-confirmed={gesture.previewStreak >= GESTURE_CONFIRM_FRAMES}>
                {previewLabel}
                <span className="bookRecognitionGestureStreak">
                  {gesture.previewStreak}/{GESTURE_CONFIRM_FRAMES}
                </span>
              </span>
            ) : null}
          </div>
        )}
      </div>

      {isActive && recognizedBook && (
        <div className="bookRecognitionDetected" aria-live="polite">
          <span className="bookRecognitionDetectedLabel">인식 결과</span>
          <strong className="bookRecognitionDetectedTitle">{recognizedBook.title}</strong>
          {recognizedBook.author ? (
            <span className="bookRecognitionDetectedAuthor">{recognizedBook.author}</span>
          ) : null}
          {gestureEnabled ? (
            <span className="bookRecognitionDetectedHint">엄지 ↑ 담기 · ↓ 빼기</span>
          ) : null}
        </div>
      )}

      {error && (
        <p className="bookRecognitionError" role="alert">
          {error}
        </p>
      )}
      {gestureEnabled && gesture.error && (
        <p className="bookRecognitionError" role="alert">
          {gesture.error}
        </p>
      )}
    </div>
  )
}
