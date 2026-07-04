import { describe, expect, it } from 'vitest'
import type { AgentMessage } from '../agent/types'
import { resolveVisibleDwellDialogueFromMessages } from './useChatAgent'

function assistant(text: string): AgentMessage {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    text,
    createdAt: Date.now(),
  }
}

describe('resolveVisibleDwellDialogueFromMessages', () => {
  it('recovers book2 intro dialogue from the visible arrival question', () => {
    expect(resolveVisibleDwellDialogueFromMessages([assistant('직접 보시니까 어떠세요?')])).toEqual({
      bookKey: 'book2',
      step: 'intro',
    })
  })

  it('recovers book1 intro dialogue from the visible arrival question', () => {
    expect(
      resolveVisibleDwellDialogueFromMessages([
        assistant('원하는 현실적인 부분이 있는 책인가요?'),
      ]),
    ).toEqual({
      bookKey: 'book1',
      step: 'intro',
    })
  })

  it('recovers feedback dialogue from the visible purchase question', () => {
    expect(
      resolveVisibleDwellDialogueFromMessages([
        assistant('사용자님이 김영하 작가의 따뜻한 문체를 좋아할 줄 알았어요. 사실건가요?'),
      ]),
    ).toEqual({
      bookKey: 'book2',
      step: 'feedback',
    })
  })
})
