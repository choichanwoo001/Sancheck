import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';

import { StreamingText } from './StreamingText.jsx';

import alertCircle from '../../assets/figma/alert-circle.svg';
import bell from '../../assets/figma/bell.svg';
import bookOpen from '../../assets/figma/book-open.svg';
import bookmark from '../../assets/figma/bookmark.svg';
import calendar from '../../assets/figma/calendar.svg';
import check from '../../assets/figma/check.svg';
import chevronDown from '../../assets/figma/chevron-down.svg';
import chevronLeft from '../../assets/figma/chevron-left.svg';
import chevronRight from '../../assets/figma/chevron-right.svg';
import clock from '../../assets/figma/clock.svg';
import home from '../../assets/figma/home.svg';
import layers from '../../assets/figma/layers.svg';
import library from '../../assets/figma/library.svg';
import lock from '../../assets/figma/lock.svg';
import mapPin from '../../assets/figma/map-pin.svg';
import moreHorizontal from '../../assets/figma/more-horizontal.svg';
import pencil from '../../assets/figma/pencil.svg';
import play from '../../assets/figma/play.svg';
import plus from '../../assets/figma/plus.svg';
import quote from '../../assets/figma/quote.svg';
import search from '../../assets/figma/search.svg';
import send from '../../assets/figma/send.svg';
import slidersHorizontal from '../../assets/figma/sliders-horizontal.svg';
import sparkles from '../../assets/figma/sparkles.svg';
import star from '../../assets/figma/star.svg';
import users from '../../assets/figma/users.svg';
import xIcon from '../../assets/figma/x.svg';

export const icons = {
  alertCircle,
  bell,
  bookOpen,
  bookmark,
  calendar,
  check,
  chevronDown,
  chevronLeft,
  chevronRight,
  clock,
  home,
  layers,
  library,
  lock,
  mapPin,
  moreHorizontal,
  pencil,
  play,
  plus,
  quote,
  search,
  send,
  slidersHorizontal,
  sparkles,
  star,
  users,
  x: xIcon,
};

export function Icon({ name, size = 16, alt = '' }) {
  return <img className="fd-icon" src={icons[name]} alt={alt} style={{ '--icon-size': `${size / 16}rem` }} />;
}

export function MobileShell({ children, showTabBar = true, activeTab = 'home', className = '' }) {
  return (
    <div className={`fd-page-shell ${className}`}>
      {children}
      {showTabBar ? <BottomTabBar activeTab={activeTab} /> : null}
    </div>
  );
}

export function BackButton({ onClick, size = 16 }) {
  return (
    <button className="fd-back-button" type="button" onClick={onClick} aria-label="뒤로">
      <Icon name="chevronLeft" size={size} />
    </button>
  );
}

export function Header({ title, subtitle, backTo, right, profile = false, searchTo }) {
  const navigate = useNavigate();
  return (
    <header className="fd-header">
      <div className="fd-header-left">
        {backTo ? <BackButton onClick={() => navigate(backTo)} /> : null}
        <div>
          <h1>{title}</h1>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
      </div>
      <div className="fd-header-actions">
        {searchTo ? (
          <Link className="fd-icon-button" to={searchTo} aria-label="검색">
            <Icon name="search" />
          </Link>
        ) : null}
        {right}
        {profile ? (
          <>
            <Link className="fd-icon-button" to="/demo/phone-home" aria-label="알림">
              <Icon name="bell" />
            </Link>
            <Link className="fd-avatar" to="/books/reading-1/completion">지</Link>
          </>
        ) : null}
      </div>
    </header>
  );
}

export function BottomTabBar({ activeTab }) {
  const tabs = [
    { id: 'home', label: '홈', to: '/', icon: 'home' },
    { id: 'library', label: '책장', to: '/library', icon: 'library' },
    { id: 'community', label: '커뮤니티', to: '/community', icon: 'users' },
    { id: 'record', label: '나의 기록', to: '/books/reading-1/completion', icon: 'bookmark' },
  ];
  return (
    <nav className="fd-bottom-tab" aria-label="주요 메뉴">
      {tabs.map((tab) => (
        <NavLink className={tab.id === activeTab ? 'is-active' : ''} to={tab.to} key={tab.id}>
          <Icon name={tab.icon} size={22} />
          <span>{tab.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export function Chip({ children, icon, selected = false, onClick }) {
  return (
    <button className={`fd-chip ${selected ? 'is-selected' : ''}`} type="button" onClick={onClick}>
      {icon ? <Icon name={icon} size={13} /> : null}
      <span>{children}</span>
    </button>
  );
}

export function Badge({ children, icon, tone = 'warm', onClick, disabled = false }) {
  const badgeIcon = icon === 'star' ? <span className="fd-badge-symbol" aria-hidden="true">★</span> : icon ? <Icon name={icon} size={11} /> : null;
  const className = `fd-badge fd-badge--${tone}${onClick ? ' fd-badge--action' : ''}`;
  const content = (
    <>
      {badgeIcon}
      <span>{children}</span>
    </>
  );

  if (onClick) {
    return (
      <button type="button" className={className} onClick={onClick} disabled={disabled}>
        {content}
      </button>
    );
  }

  return <span className={className}>{content}</span>;
}

export function PrimaryButton({ children, icon = 'play', to, onClick, variant = 'primary', disabled = false, loading = false }) {
  const content = (
    <>
      {loading ? <span className="fd-button-spinner" aria-hidden="true" /> : icon ? <Icon name={icon} size={18} /> : null}
      <span>{children}</span>
    </>
  );
  if (to && !disabled && !loading) {
    return <Link className={`fd-primary-button fd-primary-button--${variant}`} to={to}>{content}</Link>;
  }
  return (
    <button
      className={`fd-primary-button fd-primary-button--${variant} ${loading ? 'is-loading' : ''}`}
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
    >
      {content}
    </button>
  );
}

export function SearchBar({ value, placeholder, onChange, onSubmit }) {
  return (
    <form className="fd-search-bar" onSubmit={onSubmit}>
      <Icon name="search" size={18} />
      <input value={value} placeholder={placeholder} onChange={(event) => onChange?.(event.target.value)} />
      {value ? (
        <button type="button" onClick={() => onChange?.('')} aria-label="검색어 지우기">
          <Icon name="x" size={14} />
        </button>
      ) : null}
    </form>
  );
}

export function BookCover({ icon, tone = 'brown', large = false }) {
  return <div className={`fd-book-cover fd-book-cover--${tone} ${large ? 'is-large' : ''}`}><span>{icon}</span></div>;
}

export function CurrentBookCard({ book, complete = false }) {
  const percent = complete ? 100 : Math.round((book.currentPage / book.pages) * 100);
  return (
    <section className={`fd-current-card ${complete ? 'is-complete' : ''}`}>
      <div className="fd-card-row">
        <Chip icon={complete ? 'check' : 'bookOpen'}>{complete ? '완독' : '읽는 중'}</Chip>
        <span className="fd-card-badge">{complete ? '5구간 완료' : 'NEW'}</span>
      </div>
      <div className="fd-book-main">
        <BookCover icon={book.icon} large />
        <div>
          <h2>{book.title}</h2>
          <strong>{book.author}</strong>
          <p>{book.pages}페이지</p>
          <div className="fd-progress-row">
            <span className="fd-progress-track"><span style={{ width: `${Math.max(percent, complete ? 100 : 1)}%` }} /></span>
            <b>{percent}%</b>
          </div>
        </div>
      </div>
      <div className="fd-card-foot">
        <span><Icon name="bookOpen" size={12} /> {complete ? book.pages : book.currentPage} / {book.pages} 페이지</span>
        <div className="fd-card-foot-actions">
          <span><Icon name="calendar" size={12} /> {complete ? '오늘 완독' : '오늘 시작'}</span>
          <span>{complete ? '리뷰 작성 전' : 'D+0'}</span>
        </div>
      </div>
    </section>
  );
}

const REVIEW_TIMELINE_COPY = {
  title: '리뷰 남기기',
  description: 'Paige가 1~5구간 대화와 하이라이트를 바탕으로 리뷰 작성을 도와줄게요',
};

export function ReviewPromptCard({ reviewHref }) {
  return (
    <section className="fd-prompt-card">
      <h2><Icon name="sparkles" /> 이제 리뷰를 남겨볼까요?</h2>
      <p>
        1~5구간 동안 나눈 AI 대화와 저장한 하이라이트를 바탕으로 리뷰를 정리할 수 있어요. Paige가 과거 대화
        기록 기반으로 리뷰 초안을 함께 만들어줄게요.
      </p>
      <PrimaryButton to={reviewHref} icon="pencil">
        AI와 리뷰 쓰기
      </PrimaryButton>
    </section>
  );
}

export function JourneyTimeline({
  steps,
  complete = false,
  currentSegment = 1,
  onStepDoubleClick,
  showReviewStep = false,
}) {
  const allReadingDone = steps.length > 0 && steps.every((step) => step.state === 'done');
  const reviewState = allReadingDone ? 'active' : 'locked';
  const activeIndex = steps.findIndex((step) => step.state === 'active');
  const prevActiveIndexRef = useRef(activeIndex);
  const [openedIndex, setOpenedIndex] = useState(-1);

  useEffect(() => {
    if (activeIndex > prevActiveIndexRef.current) {
      setOpenedIndex(activeIndex);
      const timer = setTimeout(() => setOpenedIndex(-1), 2400);
      prevActiveIndexRef.current = activeIndex;
      return () => clearTimeout(timer);
    }
    prevActiveIndexRef.current = activeIndex;
    return undefined;
  }, [activeIndex]);

  return (
    <section className="fd-section">
      <div className="fd-section-title">
        <h2><Icon name="mapPin" size={15} /> 나의 독서 여정</h2>
        <span className={`fd-section-state ${complete ? 'is-complete' : ''}`}>
          <Icon name={complete ? 'check' : 'layers'} size={12} />
          {complete ? `${steps.length} / ${steps.length} 구간 완료` : `${currentSegment} / ${steps.length} 구간`}
        </span>
      </div>
      <div className="fd-timeline-card">
        {steps.map((step, index) => {
          const isJustOpened = step.state === 'active' && index === openedIndex;
          return (
          <article
            className={`fd-timeline-step is-${step.state}${isJustOpened ? ' is-opening' : ''}`}
            key={step.title}
            onDoubleClick={step.state === 'active' ? () => onStepDoubleClick?.() : undefined}
          >
            <div className="fd-timeline-rail">
              <span>{step.state === 'done' ? <Icon name="check" size={12} /> : step.state === 'active' ? <Icon name="star" size={12} /> : <Icon name="lock" size={11} />}</span>
              <i />
            </div>
            <div>
              <h3>
                {step.title}
                {step.state === 'active' ? <em>{isJustOpened ? '다음 구간 열림' : '현재 위치'}</em> : null}
              </h3>
              <strong>{step.subtitle}</strong>
              <p>{step.pages}</p>
            </div>
          </article>
          );
        })}
        {showReviewStep ? (
          <article className={`fd-timeline-step fd-timeline-step--review is-${reviewState}`}>
            <div className="fd-timeline-rail">
              <span>
                {reviewState === 'active' ? <Icon name="pencil" size={12} /> : <Icon name="lock" size={11} />}
              </span>
            </div>
            <div>
              <h3>
                {REVIEW_TIMELINE_COPY.title}
                <Badge icon="sparkles">AI가 도와줘요</Badge>
              </h3>
              <p>{REVIEW_TIMELINE_COPY.description}</p>
            </div>
          </article>
        ) : null}
      </div>
    </section>
  );
}

export function BookListItem({ book, action = '추가', onAction }) {
  return (
    <article className="fd-book-list-item">
      <BookCover icon={book.icon} tone={book.tone || 'pink'} />
      <div>
        <h3>{book.title}</h3>
        <strong>{book.author}</strong>
        <p>{book.meta || `${book.pages || 224}페이지`}</p>
        {book.summary ? <small>{book.summary}</small> : null}
      </div>
      <button type="button" onClick={onAction}>
        <Icon name={action === '읽기 시작' ? 'play' : 'plus'} size={12} />
        {action}
      </button>
    </article>
  );
}

export function PaigeAvatar() {
  return <span className="fd-paige-avatar">P</span>;
}

export function ChatBubble({ message }) {
  const isUser = message.role === 'user';
  const isStreaming = message.status === 'streaming' && message.content.length > 0;
  return (
    <article className={`fd-chat-row ${isUser ? 'is-user' : 'is-ai'}`}>
      {!isUser ? <PaigeAvatar /> : null}
      <div>
        {!isUser ? <span className="fd-chat-name">Paige</span> : null}
        <p>
          {!isUser ? (
            <StreamingText text={message.content} streaming={isStreaming} />
          ) : (
            message.content
          )}
        </p>
      </div>
    </article>
  );
}

export function CommunityPost({ post, staggerDelay = 0 }) {
  const [spoilerVisible, setSpoilerVisible] = useState(false);
  const [visible, setVisible] = useState(staggerDelay === 0);
  const traces = post.traces.map((trace) => (typeof trace === 'string' ? { label: trace, icon: 'calendar' } : trace));

  useEffect(() => {
    if (staggerDelay <= 0) {
      setVisible(true);
      return undefined;
    }
    const timer = setTimeout(() => setVisible(true), staggerDelay);
    return () => clearTimeout(timer);
  }, [staggerDelay]);

  if (!visible) {
    return <article className="fd-community-card fd-community-skeleton" aria-hidden="true" />;
  }

  return (
    <article className="fd-community-card is-visible">
      <div className="fd-reviewer-row">
        <span className="fd-avatar">{post.avatar}</span>
        <div>
          <h3>
            {post.user}
            <em>{post.role}</em>
            {post.isNew ? <Badge tone="warm">방금 게시</Badge> : null}
          </h3>
          <p>{post.date}</p>
        </div>
        <Chip icon="check" selected>팔로잉</Chip>
      </div>
      <div className="fd-community-book">
        <BookCover icon={post.book.icon} tone="purple" />
        <div>
          <h4>{post.book.title}</h4>
          <p>{post.book.author}</p>
          <span>★★★★<i>☆</i> {post.book.rating}</span>
        </div>
      </div>
      <blockquote>{post.review}</blockquote>
      <h5 className="fd-community-label"><Icon name="layers" size={13} /> 읽은 흔적</h5>
      <div className="fd-traces">
        {traces.map((trace) => <Chip icon={trace.icon || 'calendar'} key={trace.label}>{trace.label}</Chip>)}
      </div>
      <h5 className="fd-community-label"><Icon name="quote" size={13} /> 하이라이트 미리보기</h5>
      <div className="fd-quote-line">
        <i />
        <span>{post.quote}</span>
      </div>
      {post.spoiler ? (
        <button
          className={`fd-spoiler-preview ${spoilerVisible ? 'is-visible' : ''}`}
          type="button"
          onClick={() => setSpoilerVisible((visible) => !visible)}
          aria-expanded={spoilerVisible}
        >
          <span className="fd-spoiler-content">{post.spoiler}</span>
          {!spoilerVisible ? <strong>스포 내용 보기</strong> : null}
        </button>
      ) : null}
      <div className="fd-card-actions">
        <button type="button"><Icon name="bookmark" size={14} /> 책장에 담기</button>
        <button type="button"><Icon name="search" size={14} /> 리뷰 전체보기</button>
      </div>
    </article>
  );
}
