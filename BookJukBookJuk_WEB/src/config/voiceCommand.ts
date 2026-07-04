/** Empty means commands are accepted directly while the mic is on. */
export const VOICE_WAKE_WORDS = [] as const

/** Command collection window after speech starts. */
export const VOICE_ARM_TIMEOUT_MS = 20_000

/** Silence after speech before auto-submit. */
export const VOICE_SILENCE_MS = 1_200

export const VOICE_MIN_CHARS = 2

/** Delay before resuming mic after TTS / busy. */
export const VOICE_RESUME_DELAY_MS = 300

export const VOICE_LANG = 'ko-KR'
