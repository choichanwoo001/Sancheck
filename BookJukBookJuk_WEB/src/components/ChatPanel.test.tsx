import { fireEvent, render, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentContext } from '../agent/types'
import ChatPanel from './ChatPanel'

const publishVersoEndSessionMock = vi.fn()

vi.mock('../lib/verso/versoMobilityCommands', () => ({
  publishVersoEndSession: () => publishVersoEndSessionMock(),
}))

function createContext(): AgentContext {
  return {
    state: 'SESSION_END',
    mobilityPaused: false,
    listType: 'cart',
    activeUsersId: 'user-1',
    shoppingList: [],
    cartItems: [],
    pendingDwellBook: null,
    awaitingDwellFeedback: false,
    skippedDwellBook: null,
    extendedRouteActive: false,
    transitDetourPhase: 'idle',
    actualStopRouteExtensionPending: false,
    actualTwoBookRouteActive: false,
    resumeLegAfterDetour: null,
    checkoutStatus: 'completed',
    receipt: {
      receiptId: 'receipt-1',
      usersId: 'user-1',
      items: [{ booksId: 'book-1', title: 'Test Book' }],
      purchasedAt: '2026-06-17T00:00:00.000Z',
      qrPayload: 'receipt:receipt-1',
    },
    kakaoPaySession: null,
    recentlyRecommendedBookIds: [],
    recommendationDiversityRound: 0,
    pendingConfirmation: null,
    lastToolResult: null,
    dwellDialogueActiveBookKey: null,
    dwellDialogueStep: null,
  }
}

function renderChatPanel() {
  return render(
    <ChatPanel
      activePane="chat"
      onActivateChat={vi.fn()}
      messages={[]}
      submitUserText={vi.fn()}
      context={createContext()}
      busy={false}
      lastFailedUserText={null}
      acceptConfirmation={vi.fn()}
      cancelConfirmation={vi.fn()}
      retryLastFailed={vi.fn()}
      listLoadStatus="idle"
      listLoadMessage={null}
      ttsSpeaking={false}
      voiceSupported={false}
      voicePermissionDenied={false}
      voiceMicOn={false}
      onToggleVoiceMic={vi.fn()}
      onStartKakaoPayCheckout={vi.fn()}
      onConfirmKakaoPayCheckout={vi.fn()}
      onCancelKakaoPayCheckout={vi.fn()}
    />,
  )
}

describe('ChatPanel shelf registration QR', () => {
  it('publishes end_session when the receipt QR modal closes', async () => {
    publishVersoEndSessionMock.mockClear()

    renderChatPanel()

    await waitFor(() => {
      expect(document.body.querySelector('.shelfRegisterCloseButton')).not.toBeNull()
    })

    fireEvent.click(document.body.querySelector('.shelfRegisterCloseButton')!)

    expect(publishVersoEndSessionMock).toHaveBeenCalledTimes(1)
    expect(document.body.querySelector('.shelfRegisterCloseButton')).toBeNull()
  })
})

describe('ChatPanel mic button', () => {
  it('allows chat text submission while the agent is busy', async () => {
    const submitUserText = vi.fn(async () => {})

    render(
      <ChatPanel
        activePane="chat"
        onActivateChat={vi.fn()}
        messages={[]}
        submitUserText={submitUserText}
        context={createContext()}
        busy={true}
        lastFailedUserText={null}
        acceptConfirmation={vi.fn()}
        cancelConfirmation={vi.fn()}
        retryLastFailed={vi.fn()}
        listLoadStatus="idle"
        listLoadMessage={null}
        ttsSpeaking={false}
        voiceSupported={false}
        voicePermissionDenied={false}
        voiceMicOn={false}
        onToggleVoiceMic={vi.fn()}
        onStartKakaoPayCheckout={vi.fn()}
        onConfirmKakaoPayCheckout={vi.fn()}
        onCancelKakaoPayCheckout={vi.fn()}
      />,
    )

    const textarea = document.body.querySelector('.chatForm textarea') as HTMLTextAreaElement
    expect(textarea).not.toBeDisabled()

    fireEvent.change(textarea, { target: { value: 'ok' } })

    const submitButton = document.body.querySelector('.chatForm button[type="submit"]') as HTMLButtonElement
    expect(submitButton).not.toBeDisabled()

    fireEvent.click(submitButton)

    await waitFor(() => {
      expect(submitUserText).toHaveBeenCalledWith('ok')
    })
    expect(textarea.value).toBe('')
  })

  it('allows mic toggling while the agent is busy', () => {
    const onToggleVoiceMic = vi.fn()

    render(
      <ChatPanel
        activePane="chat"
        onActivateChat={vi.fn()}
        messages={[]}
        submitUserText={vi.fn()}
        context={createContext()}
        busy={true}
        lastFailedUserText={null}
        acceptConfirmation={vi.fn()}
        cancelConfirmation={vi.fn()}
        retryLastFailed={vi.fn()}
        listLoadStatus="idle"
        listLoadMessage={null}
        ttsSpeaking={false}
        voiceSupported={true}
        voicePermissionDenied={false}
        voiceMicOn={true}
        onToggleVoiceMic={onToggleVoiceMic}
        onStartKakaoPayCheckout={vi.fn()}
        onConfirmKakaoPayCheckout={vi.fn()}
        onCancelKakaoPayCheckout={vi.fn()}
      />,
    )

    const micButton = document.body.querySelector('.chatMicButton') as HTMLButtonElement
    expect(micButton).not.toBeDisabled()

    fireEvent.click(micButton)

    expect(onToggleVoiceMic).toHaveBeenCalledTimes(1)
  })
})
