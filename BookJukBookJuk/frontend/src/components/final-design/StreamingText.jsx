export function StreamingText({ text, streaming = false }) {
  return (
    <span className="fd-streaming-text">
      {text}
      {streaming ? <span className="fd-streaming-cursor" aria-hidden="true">▍</span> : null}
    </span>
  );
}
