import { useCallback, useEffect, useRef, useState } from 'react';

import { computeThinkDelay } from '../data/demoScript.js';
import { useStreamingText } from './useStreamingText.js';

export function useDemoAIReply({ onStreamUpdate } = {}) {
  const [phase, setPhase] = useState('idle');
  const [replyText, setReplyText] = useState('');
  const thinkTimerRef = useRef(null);

  const { displayed, isStreaming, isComplete } = useStreamingText(replyText, {
    active: phase === 'streaming',
    onComplete: () => setPhase('complete'),
  });

  useEffect(() => {
    onStreamUpdate?.();
  }, [displayed, phase, onStreamUpdate]);

  useEffect(() => () => {
    if (thinkTimerRef.current) clearTimeout(thinkTimerRef.current);
  }, []);

  const startReply = useCallback((text, thinkMs) => {
    if (thinkTimerRef.current) clearTimeout(thinkTimerRef.current);
    const delay = thinkMs ?? computeThinkDelay(text);
    setReplyText(text);
    setPhase('thinking');

    thinkTimerRef.current = setTimeout(() => {
      setPhase('streaming');
    }, delay);
  }, []);

  const reset = useCallback(() => {
    if (thinkTimerRef.current) clearTimeout(thinkTimerRef.current);
    setPhase('idle');
    setReplyText('');
  }, []);

  return {
    phase,
    displayed,
    isThinking: phase === 'thinking',
    isStreaming: phase === 'streaming' && isStreaming,
    isComplete: phase === 'complete' && isComplete,
    isBusy: phase === 'thinking' || phase === 'streaming',
    startReply,
    reset,
  };
}
