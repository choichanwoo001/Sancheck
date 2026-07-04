import { useCallback, useEffect, useRef, useState } from 'react'

import { readLlmEnv } from '../agent/runtime/llmEnv'



const LS_KEY = 'ttsEnabled'

const MAX_TEXT_LENGTH = 300

/** 채팅 나레이션(TTS) 재생 배속. */

const TTS_PLAYBACK_RATE = 1.5
const TTS_FETCH_TIMEOUT_MS = 10000



function readTtsVoice(): string {

  const v = (import.meta.env.VITE_TTS_VOICE as string | undefined)?.trim()

  return v || 'nova'

}



function readInitialEnabled(): boolean {

  try {

    const stored = localStorage.getItem(LS_KEY)

    return stored === null ? true : stored === 'true'

  } catch {

    return true

  }

}



export type UseTtsReturn = {

  speak: (text: string) => Promise<void>

  speakAndWait: (text: string) => Promise<void>

  cancel: () => void

  enabled: boolean

  setEnabled: (v: boolean) => void

  speaking: boolean

  isEnabled: () => boolean

}



export function useTts(): UseTtsReturn {

  const [enabled, setEnabledState] = useState(readInitialEnabled)

  const [speaking, setSpeaking] = useState(false)



  const queueRef = useRef<string[]>([])

  const playingRef = useRef(false)

  const currentAudioRef = useRef<HTMLAudioElement | null>(null)

  const enabledRef = useRef(enabled)

  const waitResolversRef = useRef<Array<() => void>>([])



  useEffect(() => {

    enabledRef.current = enabled

  }, [enabled])



  const playNextRef = useRef<(() => Promise<void>) | null>(null)



  const resolveWaiters = useCallback(() => {

    const resolvers = waitResolversRef.current.splice(0)

    for (const resolve of resolvers) resolve()

  }, [])



  const stopCurrentSource = useCallback(() => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause()
      currentAudioRef.current.src = ''
      currentAudioRef.current = null
    }

  }, [])

  const getCachedAudioUrl = useCallback(async (text: string): Promise<string | null> => {
    const normalizedKey = text.toLowerCase().replace(/[^a-z0-9가-힣]/g, '')
    const localUrl = `/audio/tts/${normalizedKey}.mp3`

    try {
      const localResponse = await fetch(localUrl, { method: 'HEAD' })
      if (localResponse.ok) {
        console.log('[TTS] Local mp3 cache hit:', localUrl)
        return localUrl
      }
    } catch (err) {
      console.warn('[TTS] Local mp3 cache check failed:', err)
    }

    return null
  }, [])

  const playAudioElement = useCallback(
    (url: string, options: { revokeWhenDone?: boolean } = {}): Promise<void> =>
      new Promise((resolve) => {
        const audio = new Audio(url)
        audio.preload = 'auto'
        audio.playbackRate = TTS_PLAYBACK_RATE
        currentAudioRef.current = audio
        playingRef.current = true
        setSpeaking(true)

        const cleanup = () => {
          if (options.revokeWhenDone) URL.revokeObjectURL(url)
          if (currentAudioRef.current === audio) {
            currentAudioRef.current = null
          }
          playingRef.current = false
          setSpeaking(false)
          resolve()
          resolveWaiters()
          void playNextRef.current?.()
        }

        audio.onended = cleanup
        audio.onerror = () => {
          console.warn('[TTS] HTMLAudioElement playback error:', audio.error)
          cleanup()
        }

        void audio.play().catch((err) => {
          console.warn('[TTS] HTMLAudioElement play() was blocked or failed:', err)
          cleanup()
        })
      }),
    [resolveWaiters],
  )

  const fetchRemoteAudioUrl = useCallback(async (text: string): Promise<string | null> => {
    const env = readLlmEnv()

    if (!env) {
      console.warn('[TTS] readLlmEnv() returned null. Local cache missed and VITE_OPENAI_API_KEY is missing or empty in .env.')
      return null
    }

    console.log('[TTS] Fetching audio from OpenAI TTS for text:', text)

    const controller = new AbortController()
    const timeoutId = setTimeout(() => {
      console.warn('[TTS] Fetch timed out, aborting request.')
      controller.abort()
    }, TTS_FETCH_TIMEOUT_MS)

    try {
      const response = await fetch('https://api.openai.com/v1/audio/speech', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${env.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: 'tts-1',
          input: text.slice(0, MAX_TEXT_LENGTH),
          voice: readTtsVoice(),
          response_format: 'mp3',
        }),
        signal: controller.signal,
      })
      clearTimeout(timeoutId)

      if (!response.ok) {
        console.warn('[TTS] OpenAI API request failed with status:', response.status)
        try {
          const errText = await response.text()
          console.warn('[TTS] OpenAI API error body:', errText)
        } catch {}
        return null
      }

      console.log('[TTS] OpenAI API request succeeded. Preparing audio element playback...')
      const blob = await response.blob()
      return URL.createObjectURL(blob)
    } catch (err) {
      clearTimeout(timeoutId)
      console.error('[TTS] Fetch failed:', err)
      return null
    }
  }, [])



  const playNext = useCallback(async () => {

    if (playingRef.current) return

    const text = queueRef.current.shift()

    if (!text) return



    try {
      const cachedUrl = await getCachedAudioUrl(text)
      if (cachedUrl) {
        await playAudioElement(cachedUrl)
        return
      }

      const remoteUrl = await fetchRemoteAudioUrl(text)

      if (!remoteUrl) {

        playingRef.current = false

        setSpeaking(false)

        void playNextRef.current?.()

        return

      }

      await playAudioElement(remoteUrl, { revokeWhenDone: true })

    } catch (err) {

      console.warn('[TTS] playback error', err)

      playingRef.current = false

      setSpeaking(false)

      void playNextRef.current?.()

    }

  }, [fetchRemoteAudioUrl, getCachedAudioUrl, playAudioElement])



  useEffect(() => {

    playNextRef.current = playNext

  }, [playNext])



  const speak = useCallback(

    async (text: string) => {

      if (!enabledRef.current) {

        console.log('[TTS] speak() skipped because TTS is disabled. enabled = false')

        return

      }

      const trimmed = text.trim()

      if (!trimmed) return

      queueRef.current.push(trimmed)

      await playNext()

    },

    [playNext],

  )



  const speakAndWait = useCallback(

    async (text: string) => {

      if (!enabledRef.current) {

        console.log('[TTS] speakAndWait() skipped because TTS is disabled. enabled = false')

        return

      }

      const trimmed = text.trim()

      if (!trimmed) return



      stopCurrentSource()

      queueRef.current = []

      playingRef.current = false



      try {
        const cachedUrl = await getCachedAudioUrl(trimmed)
        if (cachedUrl) {
          await playAudioElement(cachedUrl)
          return
        }

        const remoteUrl = await fetchRemoteAudioUrl(trimmed)

        if (!remoteUrl) return

        await playAudioElement(remoteUrl, { revokeWhenDone: true })

      } catch (err) {

        console.warn('[TTS] speakAndWait error', err)

        playingRef.current = false

        setSpeaking(false)

      }

    },

    [fetchRemoteAudioUrl, getCachedAudioUrl, playAudioElement, stopCurrentSource],

  )



  const cancel = useCallback(() => {

    stopCurrentSource()

    queueRef.current = []

    playingRef.current = false

    setSpeaking(false)

    resolveWaiters()

  }, [resolveWaiters, stopCurrentSource])



  const setEnabled = useCallback(

    (v: boolean) => {

      setEnabledState(v)

      try {

        localStorage.setItem(LS_KEY, String(v))

      } catch {

        // ignore storage errors

      }

      if (!v) cancel()

    },

    [cancel],

  )



  const isEnabled = useCallback(() => enabledRef.current, [])



  useEffect(() => {

    return () => {

      stopCurrentSource()

    }

  }, [stopCurrentSource])



  return { speak, speakAndWait, cancel, enabled, setEnabled, speaking, isEnabled }

}


