import { useEffect, useState } from 'react';

export function StaggerReveal({ children, delayMs = 0, className = '' }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), delayMs);
    return () => clearTimeout(timer);
  }, [delayMs]);

  return (
    <div className={`fd-stagger-reveal ${visible ? 'is-visible' : ''} ${className}`.trim()}>
      {children}
    </div>
  );
}

export function StaggerList({ items, renderItem, intervalMs = 150, startDelayMs = 0 }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    setCount(0);
    if (!items.length) return undefined;

    let current = 0;
    const startTimer = setTimeout(() => {
      const step = () => {
        current += 1;
        setCount(current);
        if (current < items.length) {
          setTimeout(step, intervalMs);
        }
      };
      step();
    }, startDelayMs);

    return () => clearTimeout(startTimer);
  }, [items, intervalMs, startDelayMs]);

  return items.slice(0, count).map((item, index) => renderItem(item, index));
}
