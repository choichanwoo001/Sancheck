export const currentBook = {
  icon: '🌱',
  title: '어른이 된다는 것',
  author: '김혜진',
  pages: 224,
  currentPage: 0,
  rating: 4.0,
};

export const journeySteps = [
  { title: '1구간 읽음', subtitle: '낯선 어른의 시작', pages: '1p ~ 45p', state: 'active' },
  { title: '2구간 읽음', subtitle: '관계 속에서 흔들리는 나', pages: '46p ~ 90p', state: 'locked' },
  { title: '3구간 읽음', subtitle: '책임과 선택의 무게', pages: '91p ~ 135p', state: 'locked' },
  { title: '4구간 읽음', subtitle: '나만의 기준을 세우는 시간', pages: '136p ~ 180p', state: 'locked' },
  { title: '5구간 읽음', subtitle: '어른이 된다는 것의 의미', pages: '181p ~ 224p', state: 'locked' },
];

export const completedJourneySteps = journeySteps.map((step) => ({ ...step, state: 'done' }));

export const libraryBooks = [
  { id: 'reading-1', icon: '🌱', title: '어른이 된다는 것', author: '김혜진', pages: 224, progress: 0, note: '방금 추가된 책이에요', state: 'NEW' },
  { id: 'reading-2', icon: '🌊', title: '오직 두 사람', author: '김영하', pages: 272, progress: 18, note: '2구간을 기다리고 있어요', state: '읽는 중' },
  { id: 'reading-3', icon: '🌙', title: '밝은 밤', author: '최은영', pages: 344, progress: 42, note: '꾸준히 읽고 있어요', state: '읽는 중' },
];

export const recommendedBooks = [
  { icon: '🦋', title: '작별하지 않는다', author: '한강', meta: '장편소설 · 문학동네', category: '소설' },
  { icon: '🌙', title: '밝은 밤', author: '최은영', meta: '장편소설 · 문학동네', category: '소설' },
  { icon: '🛍️', title: '달러구트 꿈 백화점', author: '이미예', meta: '판타지 · 팩토리나인', category: '판타지' },
];

export const searchResults = [
  { icon: '🌸', title: '채식주의자', action: '읽기 시작', author: '한강', meta: '장편소설 · 창비 · 2007', summary: '인간의 폭력성과 욕망을 섬세하게 그려낸 작품', category: '소설' },
  { icon: '🦋', title: '작별하지 않는다', action: '추가', author: '한강', meta: '장편소설 · 문학동네', summary: '기억과 애도의 시간을 깊게 따라가는 이야기', category: '소설' },
  { icon: '🌿', title: '소년이 온다', action: '추가', author: '한강', meta: '장편소설 · 창비', summary: '상처와 증언의 목소리를 따라가는 작품', category: '소설' },
  { icon: '☁️', title: '흰', action: '추가', author: '한강', meta: '시적 산문 · 문학동네', summary: '흰 것들에 기대어 삶과 죽음을 바라본 산문', category: '에세이' },
];

export const chatMessages = [
  { role: 'ai', content: "'어른이 된다는 것'이 단순히 나이를 먹는 일만은 아니라는 느낌이 들지 않으셨나요?" },
  { role: 'user', content: '네, 시간이 지나서 어른이 되는 게 아니라 사람들 사이에서 나를 어떻게 바라보는지가 더 중요하다는 느낌이었어요.' },
  { role: 'ai', content: '맞아요. 관계 속에서 스스로를 의식하게 되는 순간들이 조용히 쌓이면서 어른다움이 만들어지는 것처럼 보여요.' },
  { role: 'user', content: '큰 사건이 있는 건 아닌데, 평범한 순간을 현실적으로 바라보는 시선이 인상적이었어요.' },
  { role: 'ai', content: "그 담담한 시선이 오히려 더 깊게 다가오죠. 혹시 읽으면서 '나도 비슷하게 느낀 적 있다'고 생각한 부분이 있었나요?" },
  { role: 'user', content: '어른이 된다는 게 편해지는 게 아니라 오히려 더 많이 생각하게 되는 일이라는 건 공감됐어요.' },
  { role: 'ai', content: '좋아요. 그 감정이 이 책을 읽는 중요한 출발점이 될 수 있어요. 오늘의 한 줄 느낌을 남겨볼까요?' },
  { role: 'user', content: '어른이 된다는 건 정답을 아는 사람이 되는 게 아니라, 흔들리면서도 계속 살아가는 법을 배우는 일 같다.' },
];

export const communityPosts = [
  {
    user: '지은',
    role: '평론가',
    date: '2025.06.01',
    avatar: '지',
    book: { icon: '💜', title: '사랑받지 못하는 나를 위한 위로', author: '무라카미 류', rating: '4.0' },
    review: '"화려하지 않아도 괜찮다는 말을 이렇게 조용히 해주는 책은 흔치 않다"',
    traces: [
      { label: '18일 꾸준히', icon: 'calendar' },
      { label: '대화 23회', icon: 'quote' },
      { label: '하이라이트 9개', icon: 'pencil' },
    ],
    quote: '"사랑은 완성형이 아니라 진행형이다"',
    spoiler: '주인공이 마지막 장에서 관계를 끝내는 대신 자기 마음을 처음으로 직접 말하는 장면이 오래 남았어요.',
  },
  {
    user: '서윤',
    role: '독자',
    date: '2025.05.29',
    avatar: '서',
    book: { icon: '🦋', title: '작별하지 않는다', author: '한강', rating: '5.0' },
    review: '"읽고 나서 오래 남는 침묵이 있는 책이었다"',
    traces: [
      { label: '12일 꾸준히', icon: 'calendar' },
      { label: '대화 14회', icon: 'quote' },
      { label: '하이라이트 6개', icon: 'pencil' },
    ],
    quote: '"기억은 사라지는 것이 아니라 견디는 것이다"',
    spoiler: '후반부의 방문 장면에서 개인의 상실과 역사적 기억이 겹쳐지는 방식이 가장 강하게 다가왔어요.',
  },
];

export const reviewTimeline = [
  { date: '6/1', text: '읽다 보니 어른이 된다는 게 나이를 먹는 일보다 사람들 사이에서 나를 어떻게 바라보는지가 더 중요하다고 느꼈어요.' },
  { date: '6/3', text: '엄마와의 장면에서 내 이야기 같다는 말을 남겼어요.' },
  { date: '6/9', text: '다 읽고 나서는 어른이 된다는 게 성장만이 아니라 무언가를 포기하는 일이기도 하다고 느꼈어요.' },
];

export const reviewQuestions = ['가장 오래 남은 장면은?', '나와 닮았다고 느낀 부분은?', '이 책을 한 문장으로 남긴다면?'];

export const communitySearches = ['한강', '김영하', '정희진', '작별하지 않는다', '여성 서사', '에세이'];
