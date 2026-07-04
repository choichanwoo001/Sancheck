const KEYS = {
  user: 'bookjuk.user',
  postedReview: 'bookjuk.postedReview',
};

const DEFAULT_DEMO_SESSION = {
  chatTurns: 0,
  highlightCount: 0,
  readingDays: 1,
  lastPage: 34,
};

/** 새로고침 시 초기화 — 세션 동안만 유지 */
const sectionProgressMap = {};
let demoSessionState = { ...DEFAULT_DEMO_SESSION };
let shelfSyncIds = [];

function readJson(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  window.localStorage.setItem(key, JSON.stringify(value));
}

export function getDemoUser() {
  return readJson(KEYS.user, null);
}

export function setDemoUser(user) {
  writeJson(KEYS.user, user);
}

export function clearDemoUser() {
  window.localStorage.removeItem(KEYS.user);
}

export function getShelfSyncBookIds() {
  return [...shelfSyncIds];
}

export function addShelfSyncBook(bookId) {
  if (!shelfSyncIds.includes(bookId)) {
    shelfSyncIds = [...shelfSyncIds, bookId];
  }
}

export function getDemoSession() {
  return { ...demoSessionState };
}

export function updateDemoSession(patch) {
  demoSessionState = { ...demoSessionState, ...patch };
  return getDemoSession();
}

export function resetDemoSession() {
  demoSessionState = { ...DEFAULT_DEMO_SESSION };
  return getDemoSession();
}

export function incrementChatTurns() {
  const session = getDemoSession();
  return updateDemoSession({ chatTurns: session.chatTurns + 1 });
}

export function saveHighlightSession() {
  const session = getDemoSession();
  return updateDemoSession({ highlightCount: session.highlightCount + 1 });
}

export function getPostedReview() {
  return readJson(KEYS.postedReview, null);
}

export function savePostedReview(review) {
  writeJson(KEYS.postedReview, review);
}

export function getSectionProgress(bookId) {
  return sectionProgressMap[bookId] || 0;
}

export function setSectionProgress(bookId, readCount) {
  sectionProgressMap[bookId] = Math.max(0, Number(readCount) || 0);
}

const JOURNEY_SEGMENT_COUNT = 5;

function getShelfProgressPercent(bookId) {
  const readCount = getSectionProgress(bookId);
  return Math.round((readCount / JOURNEY_SEGMENT_COUNT) * 100);
}

function isNewlyAddedBook(bookId) {
  return getShelfSyncBookIds().includes(bookId) && getSectionProgress(bookId) === 0;
}

export function getShelfBooks() {
  const reading1IsNew = isNewlyAddedBook('reading-1');

  return [
    {
      id: 'reading-1',
      icon: '🌱',
      title: '어른이 된다는 것',
      author: '김혜진',
      pages: 224,
      tone: 'brown',
      progress: getShelfProgressPercent('reading-1'),
      state: reading1IsNew ? 'NEW' : '읽는 중',
      note: reading1IsNew ? '방금 추가된 책이에요' : '1구간을 읽고 있어요',
    },
    {
      id: 'reading-2',
      icon: '🌊',
      title: '오직 두 사람',
      author: '김영하',
      pages: 292,
      tone: 'blue',
      progress: 62,
      state: '읽는 중',
      note: '2구간을 기다리고 있어요',
    },
    {
      id: 'reading-3',
      icon: '🌙',
      title: '단 한 사람',
      author: '정이현',
      pages: 256,
      tone: 'gold',
      progress: 28,
      state: '읽는 중',
      note: '꾸준히 읽고 있어요',
    },
  ];
}
