import { PaigeAvatar } from './FinalDesignComponents.jsx';

export function TypingIndicator() {
  return (
    <article className="fd-chat-row is-ai fd-typing-indicator" aria-label="Paige가 입력 중">
      <PaigeAvatar />
      <div>
        <span className="fd-chat-name">Paige</span>
        <p className="fd-typing-dots">
          <span /><span /><span />
        </p>
      </div>
    </article>
  );
}
