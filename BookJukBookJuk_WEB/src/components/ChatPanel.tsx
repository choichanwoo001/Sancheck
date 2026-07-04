import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { ConfirmationCard } from './ConfirmationCard'
import { KakaoPayQrModal } from './KakaoPayQrModal'
import { ShelfRegisterQrModal } from './ShelfRegisterQrModal'
import { mapListTypeToShelfType } from '../lib/supabase/shelves'
import { publishVersoEndSession } from '../lib/verso/versoMobilityCommands'
import type { AgentContext, AgentMessage, ShoppingListEntry } from '../agent/types'

type BookListVariant = 'visit' | 'cart'

function ChatBookListSection({
  variant,
  title,
  meta,
  emptyText,
  books,
  actions,
  status,
}: {
  variant: BookListVariant
  title: string
  meta: string
  emptyText: string
  books: ShoppingListEntry[]
  actions?: ReactNode
  status?: { kind: 'loading' | 'error'; message: string } | null
}) {
  return (
    <section className="chatBookList" data-variant={variant} aria-label={title}>
      <div className="chatBookListHead">
        <div className="chatBookListTitleRow">
          <span className="chatBookListTitle">{title}</span>
          <span className="chatBookListMeta">{meta}</span>
        </div>
        {actions ? <div className="chatBookListActions">{actions}</div> : null}
      </div>

      {status ? (
        <p className={`chatBookListEmpty chatBookList${status.kind === 'loading' ? 'Loading' : 'Error'}`}>
          {status.message}
        </p>
      ) : books.length === 0 ? (
        <p className="chatBookListEmpty">{emptyText}</p>
      ) : (
        <ul className="chatBookListItems">
          {books.map((book) => (
            <li key={book.booksId} className="chatBookListItem" title={book.booksId}>
              <div className="chatBookThumbWrap" aria-hidden>
                {book.coverImageUrl ? (
                  <img className="chatBookThumb" src={book.coverImageUrl} alt="" loading="lazy" />
                ) : (
                  <div className="chatBookThumb chatBookThumbPlaceholder">NO IMAGE</div>
                )}
              </div>
              <div className="chatBookText">
                <p className="chatBookTitle">{book.title}</p>
                <p className="chatBookAuthor">{book.authors?.trim() || '작가 정보 없음'}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ChatPanel({
  activePane,
  onActivateChat,
  messages,
  submitUserText,
  context,
  busy,
  lastFailedUserText,
  acceptConfirmation,
  cancelConfirmation,
  retryLastFailed,
  listLoadStatus,
  listLoadMessage,
  ttsSpeaking,
  voiceSupported,
  voicePermissionDenied,
  voiceMicOn,
  onToggleVoiceMic,
  onStartKakaoPayCheckout,
  onConfirmKakaoPayCheckout,
  onCancelKakaoPayCheckout,
}: {
  activePane: 'map' | 'chat'
  onActivateChat: () => void
  messages: AgentMessage[]
  submitUserText: (text: string) => Promise<void>
  context: AgentContext
  busy: boolean
  lastFailedUserText: string | null
  acceptConfirmation: () => void
  cancelConfirmation: () => void
  retryLastFailed: () => void
  listLoadStatus: 'idle' | 'loading' | 'ok' | 'error'
  listLoadMessage: string | null
  ttsSpeaking: boolean
  voiceSupported: boolean
  voicePermissionDenied: boolean
  voiceMicOn: boolean
  onToggleVoiceMic: () => void
  onStartKakaoPayCheckout: () => void
  onConfirmKakaoPayCheckout: () => void
  onCancelKakaoPayCheckout: () => void
}) {
  const [draft, setDraft] = useState('')
  const [shelfRegisterQrOpen, setShelfRegisterQrOpen] = useState(false)
  const messageListRef = useRef<HTMLDivElement | null>(null)
  const lastReceiptIdRef = useRef<string | null>(null)

  useEffect(() => {
    const receiptId = context.receipt?.receiptId ?? null
    if (!receiptId || receiptId === lastReceiptIdRef.current) return
    lastReceiptIdRef.current = receiptId
    setShelfRegisterQrOpen(true)
  }, [context.receipt])

  const canSend = useMemo(() => draft.trim().length > 0, [draft])
  const shelfKind = mapListTypeToShelfType(context.listType)
  const visitItems = context.shoppingList
  const cartItems = context.cartItems
  const canStartCheckout = cartItems.length > 0 && context.kakaoPaySession === null
  const visitStatus =
    listLoadStatus === 'loading'
      ? { kind: 'loading' as const, message: '방문 목록을 불러오는 중이에요.' }
      : listLoadStatus === 'error'
        ? { kind: 'error' as const, message: listLoadMessage ?? '방문 목록을 불러오지 못했어요.' }
        : null

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!draft.trim()) return
    const submittedText = draft
    setDraft('')
    await submitUserText(submittedText)
  }

  const handleShelfRegisterQrClose = () => {
    publishVersoEndSession()
    setShelfRegisterQrOpen(false)
  }

  useEffect(() => {
    const listEl = messageListRef.current
    if (!listEl) return
    listEl.scrollTop = listEl.scrollHeight
  }, [messages])

  return (
    <div
      className="chatPanelWrap"
      data-active-pane={activePane === 'chat'}
      onPointerDown={onActivateChat}
      onFocusCapture={onActivateChat}
    >
      <div className="chatPanel">
        <ChatBookListSection
          variant="visit"
          title="방문 목록"
          meta={`목적지 ${visitItems.length}권`}
          emptyText="시작 전 추천에서 담은 책이나 경로에 추가된 목적지가 여기에 표시돼요."
          books={visitItems}
          status={visitStatus}
        />

        <ChatBookListSection
          variant="cart"
          title="쇼핑 리스트"
          meta={`${shelfKind}${context.listType !== shelfKind ? ` · 표시: ${context.listType}` : ''} · ${cartItems.length}권`}
          emptyText="표지 인식이나 제스처로 담은 책이 여기에 표시되고, 계산 영수증에 들어가요."
          books={cartItems}
          actions={
            <>
              {context.receipt && (
                <button
                  type="button"
                  className="chatReceiptTrigger"
                  aria-label="내 책장 등록 QR 보기"
                  aria-expanded={shelfRegisterQrOpen}
                  onClick={() => setShelfRegisterQrOpen(true)}
                >
                  책장 등록 QR
                </button>
              )}
              <button
                type="button"
                className="chatShelfLoadButton"
                onClick={() => void onStartKakaoPayCheckout()}
                disabled={!canStartCheckout}
              >
                계산하기
              </button>
            </>
          }
        />

        {context.kakaoPaySession && (
          <KakaoPayQrModal
            session={context.kakaoPaySession}
            busy={busy}
            onPaymentComplete={() => void onConfirmKakaoPayCheckout()}
            onCancel={onCancelKakaoPayCheckout}
          />
        )}

        {context.receipt && shelfRegisterQrOpen && (
          <ShelfRegisterQrModal
            receipt={context.receipt}
            onClose={handleShelfRegisterQrClose}
          />
        )}

        {context.pendingConfirmation && (
          <ConfirmationCard
            pending={context.pendingConfirmation}
            onConfirm={acceptConfirmation}
            onCancel={cancelConfirmation}
          />
        )}

        <div ref={messageListRef} className="chatMessages">
          {messages.map((message) => (
            <article
              key={message.id}
              className={`chatBubble breakAnywhere ${
                message.role === 'recognition'
                  ? 'recognition'
                  : message.role === 'user'
                    ? 'user'
                    : 'assistant'
              }`}
              data-recognition-kind={message.recognitionKind}
            >
              <div>{message.text}</div>
              {message.attachments && message.attachments.length > 0 && (
                <ul className="chatBubbleAttachments">
                  {message.attachments.map((line, index) => (
                    <li key={`${message.id}-a-${index}`}>{line}</li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>

        {lastFailedUserText && (
          <div className="chatBusyRow">
            <div className="chatRetryRow">
              <span>마지막 요청이 실패했어요.</span>
              <button type="button" onClick={() => retryLastFailed()}>
                다시 시도
              </button>
            </div>
          </div>
        )}

        <div className="chatVoiceBar">
          <div className="chatVoiceBarControls">
            {voiceSupported && (
              <button
                type="button"
                className="chatMicButton"
                data-listening={voiceMicOn || undefined}
                disabled={voicePermissionDenied}
                onClick={onToggleVoiceMic}
                aria-pressed={voiceMicOn}
                aria-label={voiceMicOn ? '마이크 끄기' : '마이크 켜기'}
              >
                <svg
                  className="chatMicIcon"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden
                >
                  <path
                    d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z"
                    fill="currentColor"
                  />
                  <path
                    d="M19 11a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.92V21H9a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2h-2v-3.08A7 7 0 0 0 19 11Z"
                    fill="currentColor"
                  />
                </svg>
                <span className="chatMicButtonLabel">{voiceMicOn ? '듣는 중' : '마이크'}</span>
              </button>
            )}
            {ttsSpeaking && (
              <span className="chatTtsSpeaking" aria-live="polite">
                읽는 중
              </span>
            )}
          </div>
        </div>

        <form className="chatForm" onSubmit={handleSubmit}>
          <div className="chatFormInputRow">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  const form = event.currentTarget.form
                  if (form) form.requestSubmit()
                }
              }}
              placeholder="메시지를 입력하세요"
              aria-label="메시지 입력"
              rows={1}
            />
            <button type="submit" disabled={!canSend}>
              전송
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ChatPanel
