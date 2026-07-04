import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import {
  Badge,
  BackButton,
  BookCover,
  BookListItem,
  ChatBubble,
  Chip,
  CommunityPost,
  CurrentBookCard,
  Header,
  Icon,
  JourneyTimeline,
  MobileShell,
  ReviewPromptCard,
  PaigeAvatar,
  PrimaryButton,
  SearchBar,
} from '../../components/final-design/FinalDesignComponents.jsx';
import { StaggerReveal } from '../../components/final-design/StaggerReveal.jsx';
import { StreamingText } from '../../components/final-design/StreamingText.jsx';
import { TypingIndicator } from '../../components/final-design/TypingIndicator.jsx';
import {
  DEMO_TIMING,
  defaultUserReview,
  reviewDraftParagraphs,
  reviewDraftVariants,
  reviewMemories,
  reviewQuestions,
  summaryContent,
} from '../../data/demoScript.js';
import { useChatDemo } from '../../hooks/useChatDemo.js';
import { useStreamingText } from '../../hooks/useStreamingText.js';
import {
  communityPosts,
  communitySearches,
  completedJourneySteps,
  currentBook,
  journeySteps,
  libraryBooks,
  recommendedBooks,
  searchResults,
} from '../../data/mockFinalDesign.js';
import {
  getDemoSession,
  getPostedReview,
  getSectionProgress,
  getShelfBooks,
  saveHighlightSession,
  savePostedReview,
  setSectionProgress,
  updateDemoSession,
} from '../../utils/demoStorage.js';

const DEFAULT_BOOK_ID = 'reading-1';

const bookCatalog = libraryBooks.map((book, index) => ({
  ...currentBook,
  ...book,
  id: book.id || `reading-${index + 1}`,
  currentPage: book.progress ?? currentBook.currentPage,
}));

function findBook(bookId) {
  return bookCatalog.find((book) => book.id === bookId) || bookCatalog[0] || { ...currentBook, id: DEFAULT_BOOK_ID };
}

function clampReadCount(value) {
  return Math.min(Math.max(Number(value) || 0, 0), journeySteps.length);
}

function getStoredReadCount(bookId) {
  return clampReadCount(getSectionProgress(bookId));
}

function storeReadCount(bookId, readCount) {
  setSectionProgress(bookId, clampReadCount(readCount));
}

function buildJourneySteps(readCount) {
  const clampedReadCount = clampReadCount(readCount);
  return journeySteps.map((step, index) => ({
    ...step,
    state: index < clampedReadCount ? 'done' : index === clampedReadCount ? 'active' : 'locked',
  }));
}

function getCurrentPage(book, readCount) {
  if (readCount >= journeySteps.length) return book.pages;
  return Math.round((book.pages / journeySteps.length) * readCount);
}

function getPageCountLabel(range) {
  const [start, end] = range.match(/\d+/g)?.map(Number) || [];
  if (!start || !end) return '';
  return `${end - start + 1}페이지`;
}

function useSelectedBook() {
  const { bookId = DEFAULT_BOOK_ID } = useParams();
  const book = findBook(bookId);
  return { book, bookId: book.id };
}

function useBookProgress(bookId) {
  const [readCount, setReadCount] = useState(() => getStoredReadCount(bookId));

  useEffect(() => {
    setReadCount(getStoredReadCount(bookId));
  }, [bookId]);

  const markCurrentSegmentRead = useCallback(() => {
    setReadCount((current) => {
      const next = clampReadCount(current + 1);
      storeReadCount(bookId, next);
      return next;
    });
  }, [bookId]);

  const safeReadCount = clampReadCount(readCount);
  return {
    currentSegment: Math.min(safeReadCount + 1, journeySteps.length),
    journey: buildJourneySteps(safeReadCount),
    markCurrentSegmentRead,
    readCount: safeReadCount,
  };
}

function Greeting() {
  return <Header title="안녕하세요, 지현님!" subtitle="오늘도 함께 읽어요" profile />;
}

export function HomePage() {
  const { book, bookId } = useSelectedBook();
  const { currentSegment, journey, markCurrentSegmentRead, readCount } = useBookProgress(bookId);
  const isComplete = readCount >= journeySteps.length;
  const bookWithProgress = { ...book, currentPage: getCurrentPage(book, readCount) };

  if (isComplete) {
    return (
      <MobileShell activeTab="home">
        <Greeting />
        <main className="fd-scroll fd-home">
          <CurrentBookCard book={{ ...book, currentPage: book.pages }} complete />
          <JourneyTimeline steps={completedJourneySteps} complete showReviewStep />
          <ReviewPromptCard reviewHref={`/books/${bookId}/review`} />
        </main>
      </MobileShell>
    );
  }

  return (
    <MobileShell activeTab="home">
      <Greeting />
      <main className="fd-scroll fd-home">
        <CurrentBookCard book={bookWithProgress} />
        <JourneyTimeline steps={journey} currentSegment={currentSegment} onStepDoubleClick={markCurrentSegmentRead} showReviewStep />
        <section className="fd-prompt-card">
          <h2><Icon name="sparkles" /> 지금 바로 시작해볼까요?</h2>
          <p>첫 페이지를 열면 독서 여정이 시작돼요. Paige가 함께 읽으며 요약과 질문을 준비해드릴게요.</p>
          <PrimaryButton to={`/books/${bookId}/chat`}>{currentSegment}구간 시작하기</PrimaryButton>
        </section>
      </main>
    </MobileShell>
  );
}

export function HomeCompletePage() {
  const { book, bookId } = useSelectedBook();
  return (
    <MobileShell activeTab="home">
      <Greeting />
      <main className="fd-scroll fd-home">
        <CurrentBookCard book={{ ...book, currentPage: book.pages }} complete />
        <JourneyTimeline steps={completedJourneySteps} complete showReviewStep />
        <ReviewPromptCard reviewHref={`/books/${bookId}/review`} />
      </main>
    </MobileShell>
  );
}

export function LibraryPage() {
  const [tab, setTab] = useState('읽는 중 3권');
  const tabs = ['읽는 중 3권', '완독 0권', '읽고 싶은 책 0권'];
  const shelfBooks = getShelfBooks();
  return (
    <MobileShell activeTab="library" className="fd-library-page">
      <header className="fd-library-header">
        <div>
          <h1>나의 책장</h1>
          <p>총 3권 · 완독 0권</p>
        </div>
        <nav aria-label="책장 도구">
          <Link to="/scan" aria-label="QR 스캔"><Icon name="search" size={18} /></Link>
          <Link to="/books/search" aria-label="검색"><Icon name="bookOpen" size={18} /></Link>
          <button type="button" aria-label="정렬"><Icon name="slidersHorizontal" size={18} /></button>
        </nav>
      </header>
      <main className="fd-library-scroll">
        <div className="fd-library-tabs">
          {tabs.map((item) => (
            <button className={tab === item ? 'is-active' : ''} type="button" onClick={() => setTab(item)} key={item}>{item}</button>
          ))}
        </div>
        <div className="fd-library-sort-row">
          <span>{tab}</span>
          <button type="button">최근 순 <Icon name="chevronDown" size={12} /></button>
        </div>
        <section className="fd-library-book-list">
          {shelfBooks.map((book, index) => {
            const currentPage = Math.round((book.pages * book.progress) / 100);
            const isNew = book.state === 'NEW';
            return (
              <StaggerReveal delayMs={index * DEMO_TIMING.staggerCardMs} key={book.id}>
                <article className={`fd-shelf-card ${isNew ? 'is-new' : ''}`}>
                  <button className="fd-shelf-card-more" type="button" aria-label={`${book.title} 더 보기`}>
                    <Icon name="moreHorizontal" size={15} />
                  </button>
                  <div className="fd-shelf-card-main">
                    <BookCover icon={book.icon} tone={book.tone} />
                    <div className="fd-shelf-info">
                      <div className="fd-shelf-title-row">
                        <h2>{book.title}</h2>
                        {isNew ? <Badge>NEW</Badge> : null}
                      </div>
                      <strong>{book.author}</strong>
                      <div className="fd-shelf-progress">
                        <span><i style={{ width: `${book.progress}%` }} /></span>
                        <p><em>{currentPage} / {book.pages} 페이지</em><b>{book.progress}%</b></p>
                      </div>
                    </div>
                  </div>
                  <footer>
                    <span><Icon name="sparkles" size={12} /> {book.note}</span>
                    <Link to={`/books/${book.id}/home`}><Icon name="play" size={11} /> {isNew ? '시작하기' : '이어 읽기'}</Link>
                  </footer>
                </article>
              </StaggerReveal>
            );
          })}
        </section>
      </main>
    </MobileShell>
  );
}

export function ChatPage() {
  const { book, bookId } = useSelectedBook();
  const { currentSegment, journey } = useBookProgress(bookId);
  const currentStep = journey[currentSegment - 1] || journey[0];
  const [draft, setDraft] = useState('');
  const scrollRef = useRef(null);
  const bottomRef = useRef(null);
  const scrollToBottom = useCallback((behavior = 'smooth') => {
    requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ behavior, block: 'end' });
    });
  }, []);
  const { messages, isThinking, isBusy, sendUserMessage } = useChatDemo({ onScroll: () => scrollToBottom('auto') });

  useEffect(() => {
    scrollToBottom(messages.length <= 1 ? 'auto' : 'smooth');
  }, [messages, isThinking, scrollToBottom]);

  const addMessage = (event) => {
    event.preventDefault();
    if (sendUserMessage(draft)) {
      setDraft('');
      scrollToBottom('smooth');
    }
  };

  return (
    <MobileShell showTabBar={false} className="fd-chat-page">
      <Header title="오늘의 독서" backTo={`/books/${bookId}/home`} right={<Link className="fd-soft-button" to={`/books/${bookId}/highlight`}>저장</Link>} />
      <section className="fd-range-card">
        <div>
          <span><Icon name="bookOpen" /> 오늘 읽은 범위</span>
          <h2>{currentStep.pages}</h2>
          <p>{book.title} · {currentSegment}구간</p>
        </div>
        <Icon name="pencil" />
      </section>
      <main className="fd-chat-scroll" ref={scrollRef}>
        {messages.map((message, index) => <ChatBubble message={message} key={`${message.role}-${index}-${message.content.slice(0, 8)}`} />)}
        {isThinking ? <TypingIndicator /> : null}
        <div className="fd-chat-scroll-anchor" ref={bottomRef} aria-hidden="true" />
      </main>
      <form className="fd-input-bar" onSubmit={addMessage}>
        <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Paige에게 말하기..." disabled={isBusy} />
        <button type="submit" aria-label="전송" disabled={isBusy || !draft.trim()}><Icon name="send" size={18} /></button>
      </form>
    </MobileShell>
  );
}

export function HighlightPage() {
  const { book, bookId } = useSelectedBook();
  const navigate = useNavigate();
  const { currentSegment } = useBookProgress(bookId);
  const [saving, setSaving] = useState(false);
  const saveHighlight = () => {
    if (saving) return;
    setSaving(true);
    saveHighlightSession();
    setTimeout(() => {
      navigate(`/books/${bookId}/summary`);
    }, DEMO_TIMING.saveMs);
  };
  return (
    <MobileShell showTabBar={false} className="fd-highlight-page">
      <header className="fd-highlight-header">
        <BackButton onClick={() => navigate(`/books/${bookId}/chat`)} />
        <h1>하이라이트 저장</h1>
        <span aria-hidden="true" />
      </header>
      <main className="fd-highlight-scroll">
        <section className="fd-highlight-context">
          <span className="fd-highlight-book-chip"><Icon name="bookOpen" size={13} /> {book.title} · {currentSegment}구간</span>
          <p>이 문장을 저장하시겠어요?</p>
        </section>
        <section className="fd-highlight-quote-card">
          <blockquote>
            "어른스럽다는 말을 들을수록<br />
            나는 점점 나로부터 멀어지는<br />
            것 같았다."
          </blockquote>
          <cite>- 1장, 23p</cite>
        </section>
        <section className="fd-highlight-section">
          <h2 className="fd-highlight-section-title"><Icon name="bookmark" size={14} /> 감정 태그</h2>
          <div className="fd-highlight-tags">
            {['공감', '인상적', '다시읽기', '의문'].map((tag, index) => <Chip selected={index < 2} key={tag}>{tag}</Chip>)}
          </div>
        </section>
        <section className="fd-highlight-section">
          <h2 className="fd-highlight-section-title"><Icon name="pencil" size={14} /> 내 메모</h2>
          <label className="fd-highlight-memo-card">
            <textarea defaultValue={"취준하면서 자꾸 생각나는 문장.\n'어른답게'가 뭔지 모르겠다."} aria-label="내 메모" />
            <span>26자</span>
          </label>
        </section>
      </main>
      <footer className="fd-highlight-submit-bar">
        <PrimaryButton icon="bookmark" onClick={saveHighlight} loading={saving}>{saving ? '저장 중…' : '저장하기'}</PrimaryButton>
      </footer>
    </MobileShell>
  );
}

export function SummaryPage() {
  const { book, bookId } = useSelectedBook();
  const navigate = useNavigate();
  const { currentSegment, journey } = useBookProgress(bookId);
  const currentStep = journey[currentSegment - 1] || journey[0];
  const pageCountLabel = getPageCountLabel(currentStep.pages);
  const session = getDemoSession();
  const chatTurns = session.chatTurns || 4;
  const highlightCount = session.highlightCount || 1;

  useEffect(() => {
    updateDemoSession({ lastPage: 34 });
  }, []);

  return (
    <MobileShell activeTab="library" className="fd-summary-page">
      <header className="fd-summary-header">
        <BackButton onClick={() => navigate(`/books/${bookId}/highlight`)} />
        <h1>오늘의 요약</h1>
        <span aria-hidden="true" />
      </header>
      <main className="fd-summary-scroll">
        <section className="fd-summary-meta">
          <div className="fd-summary-chip"><Icon name="calendar" size={12} /><span>2025.06.01</span></div>
          <div className="fd-summary-chip"><Icon name="bookOpen" size={12} /><span>{currentStep.pages} · {pageCountLabel}</span></div>
        </section>
        <div className="fd-summary-book-line"><i aria-hidden="true" /> {book.title} · {currentSegment}구간 · {currentStep.subtitle}</div>

        <section className="fd-summary-card fd-paige-summary-card">
          <div className="fd-summary-card-head">
            <div><PaigeAvatar /><h2>Paige의 요약</h2></div>
            <Badge>AI 요약</Badge>
          </div>
          <div className="fd-summary-divider" />
          <div className="fd-summary-accent-body">
            <i />
            <p>{summaryContent.paigeSummary}</p>
          </div>
        </section>

        <section className="fd-summary-card fd-highlight-summary-card">
          <h2><Icon name="quote" size={15} /> 오늘의 하이라이트</h2>
          <div className="fd-highlight-box">
            <div className="fd-summary-accent-body">
              <i />
              <blockquote>
                <span>"어른스럽다는 말을 들을수록</span>
                <span>나는 점점 나로부터 멀어지는 것 같았다"</span>
              </blockquote>
            </div>
            <cite><Icon name="bookmark" size={12} /> 1장, 23p</cite>
          </div>
        </section>

        <section className="fd-summary-keywords">
          <h2><span className="fd-summary-line-icon">◇</span> 오늘의 키워드</h2>
          <div>
            {summaryContent.keywords.map((tag, index) => (
              <span className={index < 3 ? 'is-strong' : ''} key={tag}>{tag}</span>
            ))}
          </div>
        </section>

        <section className="fd-summary-card fd-memo-summary-card">
          <h2><Icon name="pencil" size={15} /> 오늘의 메모</h2>
          <div className="fd-memo-summary-box">
            <p className="fd-memo-summary-text">{summaryContent.memo}</p>
            <div className="fd-memo-tags">
              {summaryContent.memoTags.map((tag) => <span key={tag}>{tag}</span>)}
            </div>
          </div>
        </section>

        <section className="fd-summary-streak-card">
          <div className="fd-streak-head">
            <div>
              <span className="fd-streak-icon">♨</span>
              <section>
                <h2>{session.readingDays}일째</h2>
                <p>독서 여정을 시작했어요</p>
              </section>
            </div>
            <Badge icon="star">첫 기록</Badge>
          </div>
          <div className="fd-summary-divider" />
          <div className="fd-streak-stats">
            <span><Icon name="bookOpen" size={13} /> {pageCountLabel} 읽음</span>
            <span><span className="fd-summary-line-icon">○</span> AI 대화 {chatTurns}회</span>
            <span><Icon name="pencil" size={13} /> {highlightCount}개 저장</span>
          </div>
          <p>오늘의 생각과 문장을 함께 기록했어요. 내일도 이어가볼까요?</p>
        </section>
      </main>
    </MobileShell>
  );
}

export function SearchPage() {
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  const submit = (event) => {
    event.preventDefault();
    navigate('/books/search/results');
  };
  return (
    <MobileShell activeTab="library">
      <Header title="책 추가" backTo="/library" right={<Link className="fd-cancel" to="/library">취소</Link>} />
      <main className="fd-scroll">
        <SearchBar value={query} onChange={setQuery} onSubmit={submit} placeholder="책 제목이나 작가를 검색해보세요" />
        <section className="fd-section">
          <div className="fd-section-title"><h2><Icon name="clock" /> 최근 검색</h2><span>전체 삭제</span></div>
          <div className="fd-wrap">{['채식주의자', '불편한 편의점', '아몬드', '한강'].map((item) => <Chip icon="search" key={item}>{item}</Chip>)}</div>
        </section>
        <section className="fd-section">
          <div className="fd-section-title"><h2><Icon name="sparkles" /> 추천 도서</h2><span>더 보기 <Icon name="chevronRight" size={12} /></span></div>
          {recommendedBooks.map((book) => <BookListItem book={book} key={book.title} />)}
        </section>
        <section className="fd-manual-card">
          <h2><Icon name="bookOpen" /> 직접 책 등록하기</h2>
          <input placeholder="책 제목" />
          <input placeholder="작가" />
          <div><input placeholder="출판사" /><input placeholder="총 페이지 수" /></div>
          <PrimaryButton icon="bookOpen">이 책 읽기 시작</PrimaryButton>
        </section>
      </main>
    </MobileShell>
  );
}

export function SearchResultsPage() {
  const [filter, setFilter] = useState('전체');
  const visible = useMemo(() => (filter === '전체' ? searchResults : searchResults.filter((book) => book.category === filter)), [filter]);
  return (
    <MobileShell activeTab="library">
      <Header title="검색 결과" backTo="/books/search" />
      <main className="fd-scroll">
        <SearchBar value="한강" placeholder="검색어" />
        <div className="fd-result-head"><h2>"한강"</h2><p>총 {searchResults.length}권의 책을 찾았어요</p><Chip selected>{searchResults.length}권</Chip></div>
        <div className="fd-wrap">{['전체', '소설', '에세이', '최신'].map((item) => <Chip selected={filter === item} onClick={() => setFilter(item)} key={item}>{item}</Chip>)}</div>
        {visible.map((book) => <BookListItem book={book} action={book.action} key={book.title} />)}
      </main>
    </MobileShell>
  );
}

export function CommunityPage() {
  const [tab, setTab] = useState('팔로잉');
  const [loading, setLoading] = useState(true);
  const session = getDemoSession();
  const myReview = getPostedReview();

  const posts = useMemo(() => {
    const base = [...communityPosts];
    if (myReview) {
      base.unshift({
        user: myReview.user,
        role: '독자',
        date: myReview.date,
        avatar: myReview.avatar,
        isNew: true,
        book: myReview.book,
        review: myReview.review,
        traces: [
          { label: `${session.readingDays}일 꾸준히`, icon: 'calendar' },
          { label: `대화 ${session.chatTurns}회`, icon: 'quote' },
          { label: `하이라이트 ${session.highlightCount}개`, icon: 'pencil' },
        ],
        quote: myReview.quote,
        spoiler: myReview.spoiler,
      });
    }
    return base;
  }, [myReview, session.chatTurns, session.highlightCount, session.readingDays]);

  useEffect(() => {
    const timer = setTimeout(() => setLoading(false), DEMO_TIMING.feedSkeletonMs);
    return () => clearTimeout(timer);
  }, []);

  return (
    <MobileShell activeTab="community" className="fd-community-page">
      <Header title="커뮤니티" subtitle="팔로우한 사람들의 독서 후기를 확인해보세요" searchTo="/community/search" right={<Link className="fd-icon-button" to="/demo/phone-home" aria-label="알림"><Icon name="bell" /></Link>} />
      <main className="fd-scroll">
        <div className="fd-wrap">{['팔로잉', '추천', '평론가', '독자'].map((item) => <Chip selected={tab === item} onClick={() => setTab(item)} key={item}>{item}</Chip>)}</div>
        {loading ? (
          <>
            <article className="fd-community-card fd-community-skeleton" />
            <article className="fd-community-card fd-community-skeleton" />
          </>
        ) : (
          posts.map((post, index) => (
            <CommunityPost post={post} staggerDelay={index * DEMO_TIMING.staggerCardMs} key={`${post.user}-${post.date}`} />
          ))
        )}
        <section className="fd-prompt-card">
          <h2><Icon name="check" /> 왜 이 리뷰를 신뢰할 수 있나요?</h2>
          <p>별점만이 아니라 읽은 기간, 저장 횟수, 하이라이트 같은 독서 흔적을 함께 보여드려요.</p>
        </section>
      </main>
    </MobileShell>
  );
}

export function CommunitySearchPage() {
  const [query, setQuery] = useState('');
  return (
    <MobileShell activeTab="community">
      <Header title="검색" subtitle="커뮤니티에서 사람과 책을 찾아보세요" backTo="/community" />
      <main className="fd-scroll">
        <SearchBar value={query} onChange={setQuery} placeholder="평론가, 독자, 책 제목을 검색해보세요" />
        <section className="fd-section">
          <h2 className="fd-mini-title">추천 검색</h2>
          <div className="fd-wrap">{communitySearches.map((item) => <Chip icon="search" key={item}>{item}</Chip>)}</div>
        </section>
        <section className="fd-section">
          <div className="fd-section-title"><h2>최근 검색</h2><span>전체 삭제</span></div>
          <div className="fd-search-history">{['지은', '작별하지 않는다', '무라카미 류'].map((item) => <span key={item}><Icon name="clock" /> {item}</span>)}</div>
        </section>
      </main>
    </MobileShell>
  );
}

function DraftStreamingParagraphs({ paragraphs, active, showComplete, onComplete }) {
  const [index, setIndex] = useState(0);
  const current = paragraphs[index] || '';
  const { displayed, isStreaming, isComplete } = useStreamingText(current, {
    active: active && Boolean(current),
    onComplete: () => {
      if (index < paragraphs.length - 1) {
        setIndex((value) => value + 1);
      } else {
        onComplete?.();
      }
    },
  });

  if (!active && !showComplete) return null;

  if (showComplete) {
    return (
      <>
        {paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
      </>
    );
  }

  return (
    <>
      {paragraphs.slice(0, index).map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
      {current ? <p><StreamingText text={displayed} streaming={isStreaming && !isComplete} /></p> : null}
    </>
  );
}

export function AiReviewPage() {
  const { book, bookId } = useSelectedBook();
  const navigate = useNavigate();
  const [memoryCount, setMemoryCount] = useState(0);
  const [showQuestions, setShowQuestions] = useState(false);
  const [draftPhase, setDraftPhase] = useState('waiting');
  const [draftVersion, setDraftVersion] = useState(0);
  const [draftParagraphs, setDraftParagraphs] = useState(reviewDraftParagraphs);
  const [userReview, setUserReview] = useState(defaultUserReview);
  const [posting, setPosting] = useState(false);
  const isGeneratingDraft = draftPhase === 'thinking' || draftPhase === 'streaming';

  useEffect(() => {
    const timers = reviewMemories.map((_, index) =>
      setTimeout(() => setMemoryCount(index + 1), (index + 1) * DEMO_TIMING.memoryRevealMs),
    );
    const questionsTimer = setTimeout(
      () => setShowQuestions(true),
      reviewMemories.length * DEMO_TIMING.memoryRevealMs + DEMO_TIMING.staggerSectionMs,
    );
    return () => {
      timers.forEach(clearTimeout);
      clearTimeout(questionsTimer);
    };
  }, []);

  const startDraftGeneration = (paragraphs) => {
    setDraftParagraphs(paragraphs);
    setDraftVersion((value) => value + 1);
    setDraftPhase('thinking');
    setTimeout(() => setDraftPhase('streaming'), DEMO_TIMING.reviewDraftThinkMs);
  };

  const generateDraft = () => {
    if (isGeneratingDraft) return;
    startDraftGeneration(reviewDraftParagraphs);
  };

  const applyDraftVariant = (variant) => {
    if (isGeneratingDraft) return;
    startDraftGeneration(reviewDraftVariants[variant] || reviewDraftParagraphs);
  };

  const regenerateDraft = () => {
    if (isGeneratingDraft) return;
    startDraftGeneration([...reviewDraftParagraphs].reverse());
  };

  const publishReview = () => {
    if (posting) return;
    setPosting(true);
    savePostedReview({
      user: '지현',
      avatar: '지',
      date: new Date().toLocaleDateString('ko-KR').replace(/\./g, '.').slice(0, -1),
      book: { icon: book.icon, title: book.title, author: book.author, rating: '4.0' },
      review: `"${userReview.split('\n')[0]}"`,
      quote: '"어른스럽다는 말을 들을수록 나는 점점 나로부터 멀어지는 것 같았다"',
      spoiler: '관계 속에서 스스로를 바라보게 되는 장면이 오래 남았어요.',
      body: userReview,
    });
    setTimeout(() => navigate(`/books/${bookId}/completion`), 600);
  };

  return (
    <MobileShell showTabBar={false} className="fd-ai-review-page">
      <header className="fd-review-header">
        <BackButton onClick={() => navigate(`/books/${bookId}/home-complete`)} />
        <h1>리뷰 작성</h1>
        <span>지</span>
      </header>
      <main className="fd-review-scroll">
        <section className="fd-review-book-head">
          <div className="fd-review-cover" aria-hidden="true"><span /></div>
          <div>
            <h2>{book.title} <Badge>완독</Badge></h2>
            <p>{book.author} · {book.pages}페이지 · 1~5구간 완료</p>
          </div>
        </section>

        <section className="fd-review-panel fd-review-listened">
          <div className="fd-review-panel-head">
            <PaigeAvatar />
            <h2>Paige가 우리 독서 대화를 돌아봤어요</h2>
            <Badge>AI 회고</Badge>
          </div>
          <div className="fd-review-divider" />
          <div className="fd-memory-list">
            {reviewMemories.slice(0, memoryCount).map((item) => (
              <article className="fd-review-memory is-visible" key={item.date}>
                <b>{item.date}</b>
                <p>{item.text}</p>
              </article>
            ))}
          </div>
        </section>

        {showQuestions ? (
          <StaggerReveal>
            <section className="fd-review-question-section">
              <h2><Icon name="search" size={15} /> 리뷰 작성에 도움이 될 질문이에요</h2>
              {reviewQuestions.map((item) => (
                <article className={`fd-review-question ${item.tone === 'purple' ? 'is-purple' : ''}`} key={item.label}>
                  <span>{item.label}</span>
                  {item.quote ? <blockquote>{item.quote}</blockquote> : null}
                  <p>{item.text}</p>
                </article>
              ))}
            </section>
          </StaggerReveal>
        ) : null}

        <section className="fd-review-panel fd-review-draft">
          <div className="fd-review-panel-head">
            <PaigeAvatar />
            <h2>Paige의 리뷰 초안</h2>
            <Badge
              icon="sparkles"
              onClick={generateDraft}
              disabled={isGeneratingDraft}
            >
              {draftPhase === 'thinking' ? '생성 중…' : 'AI 생성'}
            </Badge>
          </div>
          <div className="fd-review-divider" />
          <div className="fd-draft-box">
            {draftPhase === 'thinking' ? <p className="fd-draft-loading">초안 생성 중…</p> : null}
            <DraftStreamingParagraphs
              key={`${draftVersion}-${draftParagraphs.join('|')}`}
              paragraphs={draftParagraphs}
              active={draftPhase === 'streaming'}
              showComplete={draftPhase === 'complete'}
              onComplete={() => setDraftPhase('complete')}
            />
          </div>
          <p className="fd-draft-caption">이 초안은 이전 대화와 하이라이트를 바탕으로 생성되었어요</p>
        </section>

        <section className="fd-my-review-section">
          <div className="fd-my-review-head">
            <h2><Icon name="pencil" size={15} /> 내 리뷰</h2>
            <span>초안 기반으로 수정 중</span>
          </div>
          <div className="fd-review-tools" aria-label="리뷰 수정 제안">
            <button type="button" onClick={() => applyDraftVariant('shorter')}>더 짧게</button>
            <button type="button" onClick={() => applyDraftVariant('emotional')}>더 감성적으로</button>
            <button type="button" onClick={() => applyDraftVariant('honest')}>더 솔직하게</button>
            <button className="is-purple" type="button" onClick={regenerateDraft}>다시 제안</button>
          </div>
          <label className="fd-review-editor-wrap">
            <textarea
              className="fd-review-editor"
              value={userReview}
              onChange={(event) => setUserReview(event.target.value)}
            />
            <span>{userReview.length}자</span>
          </label>
        </section>
      </main>
      <footer className="fd-review-submit-bar">
        <PrimaryButton icon="send" onClick={publishReview} loading={posting}>리뷰 게시하기</PrimaryButton>
      </footer>
    </MobileShell>
  );
}

const COMPLETION_JOURNEY = [
  { title: '1구간 읽음', subtitle: '낯선 어른의 시작', pages: '1p - 45p' },
  { title: '2구간 읽음', subtitle: '관계 속에서 흔들리는 나', pages: '46p - 90p' },
  { title: '3구간 읽음', subtitle: '책임과 선택의 무게', pages: '91p - 135p' },
  { title: '4구간 읽음', subtitle: '나만의 기준을 세우는 시간', pages: '136p - 180p' },
  { title: '5구간 읽음', subtitle: '어른이 된다는 것의 의미', pages: '181p - 224p' },
];

const COMPLETION_KEYWORDS = ['#자아', '#억압', '#몸', '#저항', '#꿈', '#사회'];

export function CompletionPage() {
  const { book, bookId } = useSelectedBook();
  const navigate = useNavigate();

  return (
    <MobileShell activeTab="library" className="fd-complete-page">
      <header className="fd-review-header fd-complete-header">
        <BackButton onClick={() => navigate(`/books/${bookId}/home-complete`)} />
        <h1>완독 완료</h1>
        <button className="fd-icon-button" type="button" aria-label="공유"><Icon name="moreHorizontal" size={18} /></button>
      </header>

      <main className="fd-complete-scroll">
        <section className="fd-complete-hero">
          <div className="fd-sparkle-row" aria-hidden="true"><span>✨</span><span>☆</span><span>✨</span></div>
          <div className="fd-party-icon" aria-hidden="true">🎉</div>
          <h2>완독을 축하해요!</h2>
          <p>{book.title}을 끝까지 함께 읽었어요.</p>
        </section>

        <section className="fd-complete-book-card">
          <div className="fd-complete-chips">
            <span><Icon name="check" size={12} /> 독서 완료</span>
            <span><Icon name="calendar" size={12} /> 2024.05.22 완독</span>
          </div>
          <div className="fd-complete-book-main">
            <BookCover icon={book.icon} tone={book.tone || 'brown'} large />
            <div>
              <h2>{book.title}</h2>
              <strong>{book.author}</strong>
              <p>{book.pages}페이지</p>
              <span>★★★★<i>☆</i> <b>4.0</b></span>
            </div>
          </div>
        </section>

        <section className="fd-complete-panel fd-complete-journey-panel">
          <h2><Icon name="layers" size={15} /> 나의 독서 여정</h2>
          <div className="fd-complete-stats">
            <article><span><Icon name="calendar" size={18} /></span><strong>12일</strong><p>독서일수</p></article>
            <article><span><Icon name="bookOpen" size={18} /></span><strong>224p</strong><p>읽은 페이지</p></article>
            <article><span><Icon name="pencil" size={18} /></span><strong>8개</strong><p>남긴 기록</p></article>
          </div>
          <div className="fd-complete-section-head">
            <h3><Icon name="mapPin" size={15} /> 나의 독서 여정</h3>
            <span><Icon name="check" size={12} /> 5 / 5 구간 완료</span>
          </div>
          <div className="fd-complete-timeline">
            {COMPLETION_JOURNEY.map((step) => (
              <article className="fd-complete-step" key={step.title}>
                <div><span>✓</span><i /></div>
                <section>
                  <h4>{step.title}</h4>
                  <strong>{step.subtitle}</strong>
                  <p>{step.pages}</p>
                </section>
              </article>
            ))}
            <article className="fd-complete-step fd-complete-step--review-done">
              <div><span><Icon name="pencil" size={10} /></span></div>
              <section>
                <h4>리뷰 남기기 <Badge icon="sparkles">AI가 도와줘요</Badge></h4>
                <strong>Paige와 함께 리뷰 작성 완료</strong>
              </section>
            </article>
          </div>
        </section>

        <section className="fd-complete-panel fd-complete-ai-card">
          <div className="fd-complete-card-head">
            <h2><span className="fd-complete-ai-icon" aria-hidden="true"><Icon name="sparkles" size={14} /></span> AI의 한마디</h2>
            <Badge>+ AI</Badge>
          </div>
          <p>이 책을 읽으며 당신은 인물의 선택과 사회적 시선에 대해 깊이 생각했어요. 기록 속 키워드는 &apos;자아&apos;, &apos;억압&apos;, &apos;몸&apos;, &apos;저항&apos;이 가장 많이 등장했어요.</p>
          <small><Icon name="sparkles" size={12} /> 12일간의 독서 기록을 분석했어요</small>
        </section>

        <section className="fd-complete-panel fd-one-line-review">
          <div className="fd-complete-card-head">
            <h2><Icon name="quote" size={15} /> 나의 한 줄 평</h2>
            <Badge icon="pencil">수정</Badge>
          </div>
          <blockquote>이해받지 못한 선택이 한 사람의 삶을 어떻게 바꾸는지 보여주는 책.</blockquote>
        </section>

        <section className="fd-complete-panel fd-keyword-card">
          <div className="fd-complete-card-head">
            <h2><span className="fd-hash-mark">#</span> 많이 남긴 키워드</h2>
            <Badge>6개</Badge>
          </div>
          <div>
            {COMPLETION_KEYWORDS.map((tag) => <span key={tag}>{tag}</span>)}
          </div>
        </section>

        <section className="fd-complete-panel fd-next-card">
          <h2><Icon name="chevronRight" size={15} /> 다음으로</h2>
          <div>
            <Link to={`/books/${bookId}/home-complete`}>
              <span className="fd-next-icon is-green"><Icon name="bookmark" size={16} /></span>
              <div>
                <strong>완독 기록 확인하기</strong>
                <p>완독 탭에서 기록 보기</p>
              </div>
              <Icon name="chevronRight" size={14} />
            </Link>
            <Link to="/books/search">
              <span className="fd-next-icon"><Icon name="sparkles" size={16} /></span>
              <div>
                <strong>비슷한 책 추천받기</strong>
                <p>AI가 고른 다음 책 보기</p>
              </div>
              <Icon name="chevronRight" size={14} />
            </Link>
          </div>
        </section>
        <div className="fd-complete-action">
          <PrimaryButton to={`/books/${bookId}/home-complete`} icon="star">완독 기록 보기</PrimaryButton>
        </div>
      </main>
    </MobileShell>
  );
}
