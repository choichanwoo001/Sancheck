import paigeMascot from '../../assets/images/paige-widget-mascot.png';
import paigeMascotSad from '../../assets/images/paige-widget-mascot-sad.png';
import { widgetMessage } from '../../data/demoScript.js';

import { Icon } from './FinalDesignComponents.jsx';

const mascotSources = {
  default: paigeMascot,
  sad: paigeMascotSad,
};

export function ReadingWidget({ onClick, message = widgetMessage }) {
  const headlineLines = message.headline.split('\n');
  const mascotSrc = mascotSources[message.mascot] || paigeMascot;

  const variantClass = message.variant === 'nextDay' ? ' fd-reading-widget--next-day' : '';

  return (
    <button className={`fd-reading-widget${variantClass}`} type="button" onClick={onClick}>
      <div className="fd-reading-widget-top">
        <span className="fd-reading-widget-badge">
          <Icon name="bookOpen" size={12} />
          <span>{message.category}</span>
        </span>
        <span className="fd-reading-widget-status">
          <Icon name={message.statusIcon || 'clock'} size={12} />
          <span>{message.statusLabel}</span>
        </span>
      </div>

      <div className="fd-reading-widget-main">
        <div className="fd-reading-widget-copy">
          <h2>
            {headlineLines.map((line, index) => (
              <span key={line}>
                {index > 0 ? <br /> : null}
                {line}
              </span>
            ))}
          </h2>
          <p>{message.subtext}</p>
        </div>
        <div className="fd-reading-widget-mascot-wrap" aria-hidden="true">
          <img className="fd-reading-widget-mascot" src={mascotSrc} alt="" />
        </div>
      </div>

      <span className="fd-reading-widget-cta" aria-hidden="true">
        <Icon name="bookOpen" size={14} />
        <span>{message.cta}</span>
        <span className="fd-reading-widget-cta-chevron">&gt;</span>
      </span>
    </button>
  );
}
