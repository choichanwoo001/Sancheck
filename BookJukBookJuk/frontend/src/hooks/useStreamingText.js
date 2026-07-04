import { useCallback, useEffect, useRef, useState } from 'react';

import { DEMO_TIMING } from '../data/demoScript.js';

function getChunkSize() {
  return 2 + Math.floor(Math.random() * 3);
}

function getPauseAfterChar(char) {
  return char === '.' || char === '?' || char === '!' ? DEMO_TIMING.streamPauseMs : 0;
}

export function useStreamingText(fullText, { active = false, onComplete, chunkMs = DEMO_TIMING.streamChunkMs } = {}) {
  const [displayed, setDisplayed] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const indexRef = useRef(0);
  const timerRef = useRef(null);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  const reset = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    indexRef.current = 0;
    setDisplayed('');
    setIsStreaming(false);
  }, []);

  useEffect(() => {
    if (!active || !fullText) {
      reset();
      return undefined;
    }

    setIsStreaming(true);
    indexRef.current = 0;
    setDisplayed('');

    const tick = () => {
      const nextIndex = Math.min(fullText.length, indexRef.current + getChunkSize());
      const slice = fullText.slice(0, nextIndex);
      indexRef.current = nextIndex;
      setDisplayed(slice);

      if (nextIndex >= fullText.length) {
        setIsStreaming(false);
        queueMicrotask(() => onCompleteRef.current?.());
        return;
      }

      const lastChar = fullText[nextIndex - 1];
      timerRef.current = setTimeout(tick, chunkMs + getPauseAfterChar(lastChar));
    };

    timerRef.current = setTimeout(tick, chunkMs);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [active, fullText, chunkMs, reset]);

  return { displayed, isStreaming, isComplete: Boolean(fullText) && displayed === fullText && !isStreaming };
}
