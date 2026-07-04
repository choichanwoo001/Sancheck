import { useEffect, useRef } from 'react'

type MediaSessionMicAction = MediaSessionAction | 'togglemicrophone'

type MediaSessionWithMicToggle = {
  setActionHandler(action: MediaSessionMicAction, handler: MediaSessionActionHandler | null): void
  setMicrophoneActive?(active: boolean): Promise<void>
}

type MediaSessionMicToggleOptions = {
  enabled: boolean
  isMicOn: boolean
  onToggle: () => void
}

const MIC_TOGGLE_ACTIONS: readonly MediaSessionMicAction[] = ['togglemicrophone', 'play', 'pause']

export function useMediaSessionMicToggle({
  enabled,
  isMicOn,
  onToggle,
}: MediaSessionMicToggleOptions) {
  const onToggleRef = useRef(onToggle)

  useEffect(() => {
    onToggleRef.current = onToggle
  }, [onToggle])

  useEffect(() => {
    if (typeof navigator === 'undefined' || !('mediaSession' in navigator) || !enabled) return undefined

    const mediaSession = navigator.mediaSession as MediaSessionWithMicToggle
    const registeredActions: MediaSessionMicAction[] = []
    const handleMicToggle: MediaSessionActionHandler = () => {
      onToggleRef.current()
    }

    for (const action of MIC_TOGGLE_ACTIONS) {
      try {
        mediaSession.setActionHandler(action, handleMicToggle)
        registeredActions.push(action)
      } catch {
        // Some browsers expose Media Session but reject newer actions such as togglemicrophone.
      }
    }

    return () => {
      for (const action of registeredActions) {
        try {
          mediaSession.setActionHandler(action, null)
        } catch {
          // Ignore cleanup failures from partially supported Media Session implementations.
        }
      }
    }
  }, [enabled])

  useEffect(() => {
    if (typeof navigator === 'undefined' || !('mediaSession' in navigator) || !enabled) return

    const mediaSession = navigator.mediaSession as MediaSessionWithMicToggle
    if (!mediaSession.setMicrophoneActive) return

    try {
      void mediaSession.setMicrophoneActive(isMicOn).catch(() => {})
    } catch {
      // Ignore unsupported or transient browser Media Session state sync failures.
    }
  }, [enabled, isMicOn])
}
