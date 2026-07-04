import { useCallback, useEffect, useRef, useState } from 'react'
import {
  VOICE_ARM_TIMEOUT_MS,
  VOICE_LANG,
  VOICE_MIN_CHARS,
  VOICE_RESUME_DELAY_MS,
  VOICE_SILENCE_MS,
  VOICE_WAKE_WORDS,
} from '../config/voiceCommand'
import { getSpeechRecognitionCtor } from '../lib/speechRecognition'
import { isUtteranceSubmittable } from '../utils/voiceUtterance'
import { extractCommandFromTranscript, findWakeWordMatch } from '../utils/voiceWakeWord'

export type VoiceCommandPhase = 'unsupported' | 'off' | 'idle' | 'armed' | 'paused'

type VoiceCommandLoopOptions = {
  onUtteranceComplete: (transcript: string) => void
  paused?: boolean
  enabled?: boolean
  wakeWords?: readonly string[]
  armTimeoutMs?: number
  silenceMs?: number
  lang?: string
}

export type UseVoiceCommandLoopReturn = {
  phase: VoiceCommandPhase
  livePreview: string
  isSupported: boolean
  permissionDenied: boolean
  armRemainingMs: number | null
  isMicOn: boolean
  startMic: () => void
  stopMic: () => void
  toggleMic: () => void
}

type ListenPhase = 'idle' | 'armed'

export function useVoiceCommandLoop({
  onUtteranceComplete,
  paused = false,
  enabled = true,
  wakeWords = VOICE_WAKE_WORDS,
  armTimeoutMs = VOICE_ARM_TIMEOUT_MS,
  silenceMs = VOICE_SILENCE_MS,
  lang = VOICE_LANG,
}: VoiceCommandLoopOptions): UseVoiceCommandLoopReturn {
  const [isMicOn, setIsMicOn] = useState(false)
  const [listenPhase, setListenPhase] = useState<ListenPhase>('idle')
  const [livePreview, setLivePreview] = useState('')
  const [permissionDenied, setPermissionDenied] = useState(false)
  const [armRemainingMs, setArmRemainingMs] = useState<number | null>(null)

  const onUtteranceCompleteRef = useRef(onUtteranceComplete)
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const recognitionSessionIdRef = useRef(0)
  const micSessionRef = useRef(false)
  const isMicOnRef = useRef(false)
  const userRequestedStopRef = useRef(false)
  const discardOnStopRef = useRef(false)
  const finalBufferRef = useRef('')
  const lastInterimRef = useRef('')
  const listenPhaseRef = useRef<ListenPhase>('idle')
  const commandBufferRef = useRef('')
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const armTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const armDeadlineRef = useRef<number | null>(null)
  const armTickRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const resumeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const recognitionRestartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pausedRef = useRef(paused)
  const enabledRef = useRef(enabled)
  const startRecognitionRef = useRef<() => void>(() => {})

  const isSupported = Boolean(getSpeechRecognitionCtor())

  useEffect(() => {
    onUtteranceCompleteRef.current = onUtteranceComplete
  }, [onUtteranceComplete])

  useEffect(() => {
    listenPhaseRef.current = listenPhase
  }, [listenPhase])

  useEffect(() => {
    pausedRef.current = paused
  }, [paused])

  useEffect(() => {
    enabledRef.current = enabled
  }, [enabled])

  useEffect(() => {
    isMicOnRef.current = isMicOn
  }, [isMicOn])

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
  }, [])

  const clearArmTimerRefs = useCallback(() => {
    if (armTimerRef.current) {
      clearTimeout(armTimerRef.current)
      armTimerRef.current = null
    }
    if (armTickRef.current) {
      clearInterval(armTickRef.current)
      armTickRef.current = null
    }
    armDeadlineRef.current = null
  }, [])

  const clearRecognitionRestartTimer = useCallback(() => {
    if (recognitionRestartTimerRef.current) {
      clearTimeout(recognitionRestartTimerRef.current)
      recognitionRestartTimerRef.current = null
    }
  }, [])

  const scheduleRecognitionRestart = useCallback(() => {
    clearRecognitionRestartTimer()
    recognitionRestartTimerRef.current = setTimeout(() => {
      recognitionRestartTimerRef.current = null
      if (micSessionRef.current && isMicOnRef.current && !pausedRef.current && enabledRef.current) {
        startRecognitionRef.current()
      }
    }, VOICE_RESUME_DELAY_MS)
  }, [clearRecognitionRestartTimer])

  const getFullTranscript = useCallback(() => {
    return (finalBufferRef.current + lastInterimRef.current).trim()
  }, [])

  const resetListenStateRefs = useCallback(() => {
    listenPhaseRef.current = 'idle'
    commandBufferRef.current = ''
    clearSilenceTimer()
    clearArmTimerRefs()
  }, [clearArmTimerRefs, clearSilenceTimer])

  const resetListenState = useCallback(() => {
    resetListenStateRefs()
    setListenPhase('idle')
    setLivePreview('')
    setArmRemainingMs(null)
  }, [resetListenStateRefs])

  const flushRecognitionBuffers = useCallback(() => {
    finalBufferRef.current = ''
    lastInterimRef.current = ''
  }, [])

  const releaseRecognition = useCallback((recognition: SpeechRecognition | null) => {
    if (!recognition) return
    recognition.onresult = null
    recognition.onerror = null
    recognition.onend = null
    recognition.onstart = null
    try {
      const maybeAbort = (recognition as SpeechRecognition & { abort?: () => void }).abort
      if (typeof maybeAbort === 'function') {
        maybeAbort.call(recognition)
      } else {
        recognition.stop()
      }
    } catch {
      // The browser may already have ended this recognition instance.
    }
  }, [])

  const resetRecognitionRuntimeRefs = useCallback(
    (options?: { keepMicSession?: boolean }) => {
      clearSilenceTimer()
      clearArmTimerRefs()
      clearRecognitionRestartTimer()
      recognitionSessionIdRef.current += 1
      const recognition = recognitionRef.current
      recognitionRef.current = null
      userRequestedStopRef.current = false
      discardOnStopRef.current = false
      if (!options?.keepMicSession) {
        micSessionRef.current = false
      }
      releaseRecognition(recognition)
      flushRecognitionBuffers()
      resetListenStateRefs()
    },
    [
      clearArmTimerRefs,
      clearRecognitionRestartTimer,
      clearSilenceTimer,
      flushRecognitionBuffers,
      releaseRecognition,
      resetListenStateRefs,
    ],
  )

  const resetRecognitionRuntime = useCallback(() => {
    resetRecognitionRuntimeRefs()
    resetListenState()
  }, [resetListenState, resetRecognitionRuntimeRefs])

  const submitCommand = useCallback(() => {
    const command = commandBufferRef.current.trim()
    if (!isUtteranceSubmittable(command, VOICE_MIN_CHARS)) return false

    resetListenState()
    flushRecognitionBuffers()
    onUtteranceCompleteRef.current(command)
    return true
  }, [flushRecognitionBuffers, resetListenState])

  const scheduleSilenceSubmit = useCallback(() => {
    clearSilenceTimer()
    silenceTimerRef.current = setTimeout(() => {
      silenceTimerRef.current = null
      if (listenPhaseRef.current !== 'armed' || pausedRef.current || !isMicOnRef.current) return
      if (submitCommand()) {
        discardOnStopRef.current = true
        userRequestedStopRef.current = true
        recognitionRef.current?.stop()
      }
    }, silenceMs)
  }, [clearSilenceTimer, silenceMs, submitCommand])

  const startArmTimer = useCallback(() => {
    clearArmTimerRefs()
    const deadline = Date.now() + armTimeoutMs
    armDeadlineRef.current = deadline
    setArmRemainingMs(armTimeoutMs)

    armTickRef.current = setInterval(() => {
      const remaining = armDeadlineRef.current ? Math.max(0, armDeadlineRef.current - Date.now()) : 0
      setArmRemainingMs(remaining > 0 ? remaining : null)
    }, 250)

    armTimerRef.current = setTimeout(() => {
      armTimerRef.current = null
      if (listenPhaseRef.current !== 'armed') return
      resetListenState()
      flushRecognitionBuffers()
      discardOnStopRef.current = true
      userRequestedStopRef.current = true
      recognitionRef.current?.stop()
    }, armTimeoutMs)
  }, [armTimeoutMs, clearArmTimerRefs, flushRecognitionBuffers, resetListenState])

  const processTranscript = useCallback(() => {
    if (pausedRef.current || !isMicOnRef.current) return

    const transcript = getFullTranscript()
    const hadWake = findWakeWordMatch(transcript, wakeWords) !== null
    const { armed, command } = extractCommandFromTranscript(
      transcript,
      wakeWords,
      listenPhaseRef.current === 'armed',
    )

    if (!armed) {
      if (listenPhaseRef.current === 'armed') {
        resetListenState()
      } else {
        finalBufferRef.current = ''
      }
      return
    }

    const wasIdle = listenPhaseRef.current === 'idle'
    listenPhaseRef.current = 'armed'
    setListenPhase('armed')
    commandBufferRef.current = command
    setLivePreview(command)

    if (wasIdle || hadWake) {
      startArmTimer()
    }

    if (command) {
      scheduleSilenceSubmit()
    }
  }, [getFullTranscript, resetListenState, scheduleSilenceSubmit, startArmTimer, wakeWords])

  const startRecognitionInstance = useCallback(() => {
    const Ctor = getSpeechRecognitionCtor()
    if (
      !Ctor ||
      !micSessionRef.current ||
      !isMicOnRef.current ||
      userRequestedStopRef.current ||
      pausedRef.current ||
      !enabledRef.current
    ) {
      return
    }

    const recognition = new Ctor()
    const sessionId = recognitionSessionIdRef.current + 1
    recognitionSessionIdRef.current = sessionId
    recognition.lang = lang
    recognition.continuous = true
    recognition.interimResults = true

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      if (recognitionRef.current !== recognition || recognitionSessionIdRef.current !== sessionId) return
      let interimPiece = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const row = event.results[i]
        const piece = row[0]?.transcript ?? ''
        if (row.isFinal) {
          finalBufferRef.current += piece
          lastInterimRef.current = ''
        } else {
          interimPiece += piece
        }
      }
      if (interimPiece) {
        lastInterimRef.current = interimPiece
      }
      processTranscript()
    }

    recognition.onerror = (ev: SpeechRecognitionErrorEvent) => {
      if (recognitionRef.current !== recognition || recognitionSessionIdRef.current !== sessionId) return
      if (ev.error === 'aborted') return
      if (ev.error === 'not-allowed' || ev.error === 'audio-capture') {
        micSessionRef.current = false
        isMicOnRef.current = false
        userRequestedStopRef.current = false
        discardOnStopRef.current = false
        flushRecognitionBuffers()
        recognitionRef.current = null
        resetListenState()
        setIsMicOn(false)
        setPermissionDenied(true)
      }
    }

    recognition.onend = () => {
      if (recognitionRef.current !== recognition || recognitionSessionIdRef.current !== sessionId) return
      recognitionRef.current = null

      if (userRequestedStopRef.current) {
        userRequestedStopRef.current = false
        if (discardOnStopRef.current) {
          discardOnStopRef.current = false
          flushRecognitionBuffers()
        }
        if (micSessionRef.current && isMicOnRef.current && !pausedRef.current && enabledRef.current) {
          scheduleRecognitionRestart()
        } else {
          micSessionRef.current = false
        }
        return
      }

      if (micSessionRef.current && isMicOnRef.current && !pausedRef.current && enabledRef.current) {
        scheduleRecognitionRestart()
      } else {
        micSessionRef.current = false
      }
    }

    recognitionRef.current = recognition
    try {
      recognition.start()
    } catch {
      if (recognitionSessionIdRef.current !== sessionId) return
      userRequestedStopRef.current = false
      discardOnStopRef.current = false
      recognitionRef.current = null
      resetListenState()
      if (micSessionRef.current && isMicOnRef.current && !pausedRef.current && enabledRef.current) {
        scheduleRecognitionRestart()
      } else {
        micSessionRef.current = false
        setIsMicOn(false)
      }
    }
  }, [flushRecognitionBuffers, lang, processTranscript, resetListenState, scheduleRecognitionRestart])

  useEffect(() => {
    startRecognitionRef.current = startRecognitionInstance
  }, [startRecognitionInstance])

  const startListening = useCallback(() => {
    const Ctor = getSpeechRecognitionCtor()
    if (!Ctor || pausedRef.current || !enabledRef.current || permissionDenied || !isMicOnRef.current) return
    if (micSessionRef.current && recognitionRef.current) return

    micSessionRef.current = true
    clearRecognitionRestartTimer()
    userRequestedStopRef.current = false
    discardOnStopRef.current = false
    flushRecognitionBuffers()
    resetListenState()
    if (recognitionRef.current) return
    startRecognitionInstance()
  }, [
    clearRecognitionRestartTimer,
    flushRecognitionBuffers,
    permissionDenied,
    resetListenState,
    startRecognitionInstance,
  ])

  const stopMic = useCallback(() => {
    setIsMicOn(false)
    isMicOnRef.current = false
    resetRecognitionRuntime()
  }, [resetRecognitionRuntime])

  const startMic = useCallback(() => {
    if (!isSupported || permissionDenied || !enabledRef.current) return
    setIsMicOn(true)
    isMicOnRef.current = true
    if (!pausedRef.current) {
      startListening()
    }
  }, [isSupported, permissionDenied, startListening])

  const toggleMic = useCallback(() => {
    if (isMicOnRef.current) {
      stopMic()
      return
    }
    startMic()
  }, [startMic, stopMic])

  useEffect(() => {
    if (!isSupported || !enabled || !isMicOn) return undefined

    if (paused) {
      if (resumeTimerRef.current) {
        clearTimeout(resumeTimerRef.current)
        resumeTimerRef.current = null
      }
      clearRecognitionRestartTimer()
      resetRecognitionRuntimeRefs()
      const frameId = requestAnimationFrame(() => {
        setListenPhase('idle')
        setLivePreview('')
        setArmRemainingMs(null)
      })
      return () => {
        cancelAnimationFrame(frameId)
      }
    }

    if (!micSessionRef.current && !recognitionRef.current) {
      resumeTimerRef.current = setTimeout(() => {
        resumeTimerRef.current = null
        if (isMicOnRef.current && !pausedRef.current) {
          startListening()
        }
      }, VOICE_RESUME_DELAY_MS)
    }

    return () => {
      if (resumeTimerRef.current) {
        clearTimeout(resumeTimerRef.current)
        resumeTimerRef.current = null
      }
    }
  }, [
    enabled,
    clearRecognitionRestartTimer,
    flushRecognitionBuffers,
    isMicOn,
    isSupported,
    paused,
    resetRecognitionRuntimeRefs,
    startListening,
  ])

  useEffect(() => {
    return () => {
      clearSilenceTimer()
      clearArmTimerRefs()
      clearRecognitionRestartTimer()
      if (resumeTimerRef.current) clearTimeout(resumeTimerRef.current)
      micSessionRef.current = false
      isMicOnRef.current = false
      userRequestedStopRef.current = false
      discardOnStopRef.current = false
      recognitionSessionIdRef.current += 1
      releaseRecognition(recognitionRef.current)
      recognitionRef.current = null
    }
  }, [clearArmTimerRefs, clearRecognitionRestartTimer, clearSilenceTimer, releaseRecognition])

  const phase: VoiceCommandPhase = !isSupported
    ? 'unsupported'
    : !isMicOn
      ? 'off'
      : paused
        ? 'paused'
        : listenPhase

  return {
    phase,
    livePreview,
    isSupported,
    permissionDenied,
    armRemainingMs,
    isMicOn,
    startMic,
    stopMic,
    toggleMic,
  }
}
