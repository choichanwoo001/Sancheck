import { useCallback, useEffect, useRef, useState } from 'react';

import { chatGreeting, chatTurns, computeThinkDelay, findChatTurn } from '../data/demoScript.js';
import { incrementChatTurns } from '../utils/demoStorage.js';
import { useStreamingText } from './useStreamingText.js';

export function useChatDemo({ onScroll }) {
  const [messages, setMessages] = useState([]);
  const [turnIndex, setTurnIndex] = useState(0);
  const [phase, setPhase] = useState('thinking');
  const [streamTarget, setStreamTarget] = useState('');
  const thinkTimerRef = useRef(null);
  const streamTargetRef = useRef('');

  const handleStreamComplete = useCallback(() => {
    const fullText = streamTargetRef.current;
    setMessages((current) => {
      const next = [...current];
      const last = next[next.length - 1];
      if (last?.role === 'ai') {
        next[next.length - 1] = { ...last, content: fullText, status: 'complete' };
      }
      return next;
    });
    setPhase('idle');
    streamTargetRef.current = '';
    setStreamTarget('');
  }, []);

  const { displayed, isStreaming } = useStreamingText(streamTarget, {
    active: phase === 'streaming',
    onComplete: handleStreamComplete,
  });

  useEffect(() => {
    onScroll?.();
  }, [messages, displayed, phase, onScroll]);

  useEffect(() => {
    if (phase !== 'streaming') return;
    setMessages((current) => {
      const next = [...current];
      const last = next[next.length - 1];
      if (last?.role === 'ai') {
        next[next.length - 1] = {
          ...last,
          content: displayed,
          status: isStreaming ? 'streaming' : 'complete',
        };
      }
      return next;
    });
  }, [displayed, phase, isStreaming]);

  const queueAiReply = useCallback((text, thinkMs) => {
    if (thinkTimerRef.current) clearTimeout(thinkTimerRef.current);
    setPhase('thinking');
    thinkTimerRef.current = setTimeout(() => {
      streamTargetRef.current = text;
      setMessages((current) => [...current, { role: 'ai', content: '', status: 'streaming' }]);
      setStreamTarget(text);
      setPhase('streaming');
    }, thinkMs ?? computeThinkDelay(text));
  }, []);

  useEffect(() => {
    queueAiReply(chatGreeting.ai, computeThinkDelay(chatGreeting.ai));
    return () => {
      if (thinkTimerRef.current) clearTimeout(thinkTimerRef.current);
    };
  }, [queueAiReply]);

  const sendUserMessage = useCallback((text) => {
    const trimmed = text.trim();
    if (!trimmed || phase === 'thinking' || phase === 'streaming') return false;

    const turn = findChatTurn(trimmed, turnIndex);
    setMessages((current) => [...current, { role: 'user', content: trimmed, status: 'complete' }]);
    setTurnIndex((current) => current + 1);
    incrementChatTurns();
    queueAiReply(turn.ai, turn.thinkMs);
    return true;
  }, [phase, queueAiReply, turnIndex]);

  const suggestedReplies = chatTurns.slice(turnIndex).map((turn) => turn.user);
  const isBusy = phase === 'thinking' || phase === 'streaming';

  return {
    messages,
    isThinking: phase === 'thinking',
    isBusy,
    suggestedReplies,
    sendUserMessage,
  };
}
