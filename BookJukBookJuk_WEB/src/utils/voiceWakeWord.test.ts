import { describe, expect, it } from 'vitest'
import {
  containsWakeWord,
  extractCommandFromTranscript,
  findWakeWordMatch,
  stripWakeWord,
} from './voiceWakeWord'

describe('voiceWakeWord', () => {
  const wakeWords = ['산책아'] as const

  it('detects primary wake word 산책아', () => {
    expect(containsWakeWord('산책아 추천해줘', wakeWords)).toBe(true)
    expect(findWakeWordMatch('산책아 추천해줘', wakeWords)?.word).toBe('산책아')
  })

  it('detects wake word when STT inserts spaces', () => {
    expect(containsWakeWord('산책 아 추천해줘', wakeWords)).toBe(true)
    expect(stripWakeWord('산책 아 추천해줘', wakeWords)).toBe('추천해줘')
    expect(extractCommandFromTranscript('산책 아 추천해줘', wakeWords, false)).toEqual({
      armed: true,
      command: '추천해줘',
    })
  })

  it('strips wake word and leaves command', () => {
    expect(stripWakeWord('산책아 추천해줘', wakeWords)).toBe('추천해줘')
    expect(stripWakeWord('산책아', wakeWords)).toBe('')
  })

  it('extracts command when not yet armed', () => {
    expect(extractCommandFromTranscript('산책아 오케이', wakeWords, false)).toEqual({
      armed: true,
      command: '오케이',
    })
  })

  it('accepts transcript directly when wake words are disabled', () => {
    expect(extractCommandFromTranscript('추천해줘', [], false)).toEqual({
      armed: true,
      command: '추천해줘',
    })
  })

  it('accepts free-form feedback directly when wake words are disabled', () => {
    const feedback = '이 책은 너무 무거운 내용이라 지금은 별로 안 끌려'
    expect(extractCommandFromTranscript(feedback, [], false)).toEqual({
      armed: true,
      command: feedback,
    })
  })

  it('ignores transcript without wake word when idle and wake words are configured', () => {
    expect(extractCommandFromTranscript('추천해줘', wakeWords, false)).toEqual({
      armed: false,
      command: '',
    })
  })

  it('accumulates command when already armed', () => {
    expect(extractCommandFromTranscript('오케이', wakeWords, true)).toEqual({
      armed: true,
      command: '오케이',
    })
  })

  it('strips wake word from transcript when already armed', () => {
    expect(extractCommandFromTranscript('산책아 오케이', wakeWords, true)).toEqual({
      armed: true,
      command: '오케이',
    })
  })

  it('re-arms when wake word appears again while armed', () => {
    expect(extractCommandFromTranscript('산책아 멈춰', wakeWords, true)).toEqual({
      armed: true,
      command: '멈춰',
    })
  })
})
