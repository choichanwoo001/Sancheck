import { describe, expect, it, vi } from 'vitest'
import type { Dispatch, SetStateAction } from 'react'
import type { AgentMessage } from '../../agent/types'
import { appendUserMessageAndStore } from './helpers'
import { appendConversationMessage } from '../../lib/supabase/conversation'

vi.mock('../../lib/supabase/conversation', () => ({
  appendConversationMessage: vi.fn(),
}))

describe('chatAgent helpers', () => {
  it('does not block local chat flow while persisting the user message', async () => {
    vi.mocked(appendConversationMessage).mockReturnValueOnce(new Promise(() => {}) as Promise<boolean>)
    const setMessagesMock = vi.fn((value: SetStateAction<AgentMessage[]>) => {
      return typeof value === 'function' ? value([]) : value
    })
    const setMessages = setMessagesMock as Dispatch<SetStateAction<AgentMessage[]>>

    await expect(
      appendUserMessageAndStore({
        text: 'I like the style',
        conversationId: 'conversation-1',
        intent: 'unknown',
        setMessages,
      }),
    ).resolves.toBeUndefined()

    expect(setMessagesMock).toHaveBeenCalledOnce()
    expect(appendConversationMessage).toHaveBeenCalledWith({
      conversationId: 'conversation-1',
      role: 'user',
      content: 'I like the style',
      intent: 'unknown',
    })
  })
})
