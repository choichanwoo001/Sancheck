import { fireEvent, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { KakaoPaySession } from '../lib/payment/kakaoPay'
import { KakaoPayQrModal } from './KakaoPayQrModal'

const session: KakaoPaySession = {
  orderId: 'order-1',
  amountKrw: 15000,
  itemCount: 1,
  qrPayload: 'https://pay.example.test/order-1',
  lineItems: [{ booksId: 'book-1', title: 'Test Book', priceKrw: 15000 }],
  itemName: 'Test Book',
  status: 'pending',
  createdAt: '2026-06-17T00:00:00.000Z',
}

describe('KakaoPayQrModal', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('does not complete payment automatically while the QR is shown', () => {
    vi.useFakeTimers()
    const onPaymentComplete = vi.fn()

    render(
      <KakaoPayQrModal
        session={session}
        busy={false}
        onPaymentComplete={onPaymentComplete}
        onCancel={vi.fn()}
      />,
    )

    vi.advanceTimersByTime(10_000)

    expect(onPaymentComplete).not.toHaveBeenCalled()
  })

  it('completes payment when the confirm button is clicked', () => {
    const onPaymentComplete = vi.fn()

    render(
      <KakaoPayQrModal
        session={session}
        busy={false}
        onPaymentComplete={onPaymentComplete}
        onCancel={vi.fn()}
      />,
    )

    fireEvent.click(document.body.querySelector('.kakaoPayConfirmButton')!)
    fireEvent.click(document.body.querySelector('.kakaoPayConfirmButton')!)

    expect(onPaymentComplete).toHaveBeenCalledTimes(1)
  })

  it('keeps the confirm button available while the app is busy', () => {
    const onPaymentComplete = vi.fn()

    render(
      <KakaoPayQrModal
        session={session}
        busy
        onPaymentComplete={onPaymentComplete}
        onCancel={vi.fn()}
      />,
    )

    const confirmButton = document.body.querySelector<HTMLButtonElement>('.kakaoPayConfirmButton')!
    expect(confirmButton).not.toBeDisabled()

    fireEvent.click(confirmButton)

    expect(onPaymentComplete).toHaveBeenCalledTimes(1)
  })
})
