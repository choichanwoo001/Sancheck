export const DEMO_TIMING = {
  thinkBaseMs: 1200,
  thinkPerCharMs: 12,
  thinkMaxMs: 2800,
  thinkJitterMs: 200,
  streamChunkMs: 35,
  streamPauseMs: 180,
  saveMs: 750,
  syncReceiptMs: 800,
  syncShelfMs: 1200,
  staggerSectionMs: 400,
  staggerCardMs: 150,
  staggerKeywordMs: 120,
  feedSkeletonMs: 800,
  reviewDraftThinkMs: 1500,
  memoryRevealMs: 400,
};

export const chatGreeting = {
  ai: "첫 구간을 읽어보셨어요.\n'어른이 된다는 것'이 단순히 나이를 먹는 일만은 아니라는 느낌이 들지 않으셨나요?",
};

export const chatTurns = [
  {
    user: '네, 시간이 지나서 어른이 되는 게 아니라 사람들 사이에서 나를 어떻게 바라보는지가 더 중요하다는 느낌이었어요.',
    ai: '맞아요.\n관계 속에서 스스로를 의식하게 되는 순간들이 조용히 쌓이면서 어른다움이 만들어지는 것처럼 보여요.\n오늘 읽은 부분에서 가장 마음에 남은 장면이 있었나요?',
    thinkMs: 1800,
  },
  {
    user: '큰 사건이 있는 건 아닌데, 평범한 순간을 현실적으로 바라보는 시선이 인상적이었어요.',
    ai: "그 담담한 시선이 오히려 더 깊게 다가오죠.\n혹시 읽으면서 '나도 비슷하게 느낀 적 있다'고 생각한 부분이 있었나요?",
    thinkMs: 2100,
  },
  {
    user: '어른이 된다는 게 편해지는 게 아니라 오히려 더 많이 생각하게 되는 일이라는 건 공감됐어요.',
    ai: '좋아요.\n그 감정이 이 책을 읽는 중요한 출발점이 될 수 있어요.\n오늘의 한 줄 느낌을 남겨볼까요?',
    thinkMs: 1900,
  },
  {
    user: '어른이 된다는 건 정답을 아는 사람이 되는 게 아니라, 흔들리면서도 계속 살아가는 법을 배우는 일 같다.',
    ai: '그 한 줄이 오늘 읽은 범위를 잘 담고 있어요. 하이라이트로 저장해두면 나중에 리뷰를 쓸 때도 도움이 될 거예요.',
    thinkMs: 2200,
  },
];

export const summaryContent = {
  paigeSummary:
    "오늘 읽은 1구간에서는 '어른이 된다는 것'이 단순히 나이를 먹는 일이 아니라, 관계 속에서 자신을 돌아보고 스스로를 어떻게 바라보는지가 더 중요하다는 흐름이 드러나요. 평범한 순간을 현실적으로 바라보는 시선이 인상적이며, 어른다움은 정답을 아는 상태보다 흔들리면서도 계속 살아가는 과정에 가깝게 느껴집니다.",
  keywords: ['#자아', '#어른다움', '#관계', '#흔들림', '#자기이해'],
  memo: "취준하면서 자꾸 생각나는 문장.\n'어른답게'가 뭔지 모르겠다.",
  memoTags: ['공감', '인상적'],
};

export const reviewMemories = [
  {
    date: '6/1',
    text: '"읽다 보니 어른이 된다는 게 나이를 먹는 일보다 사람들 사이에서 나를 어떻게 바라보는지가 더 중요하다고 느꼈어요."',
  },
  {
    date: '6/3',
    text: '"엄마와의 장면에서 내 이야기 같다는 말을 남겼어요."',
  },
  {
    date: '6/9',
    text: '"다 읽고 나서는 어른이 된다는 게 성장만이 아니라 무언가를 포기하는 일이기도 하다고 느꼈어요."',
  },
];

export const reviewQuestions = [
  {
    label: 'Q1 · 대화 기반',
    text: "'어른아 어른답지'라고 했는데, 다 읽고 나서 그 생각이 달라진 게 있었나요?",
  },
  {
    label: 'Q2 · 대화 기반',
    text: '엄마 장면에서 본인 이야기 같다고 했잖아요. 그 감정을 리뷰에 한 문장으로 적는다면 어떻게 표현할 수 있을까요?',
  },
  {
    label: 'Q3 · 하이라이트 기반',
    quote: '"어른스럽다는 말을 들을수록 나는 점점 나로부터 멀어지는 것 같았다"',
    text: '이 문장이 왜 인상 깊었는지도 리뷰에 담아볼까요?',
    tone: 'purple',
  },
];

export const reviewDraftParagraphs = [
  '『어른이 된다는 것』은 성장이란 이름으로 어른다움을 강요받는 순간들을 조용하고 현실적으로 보여주는 책이다.',
  '읽는 내내 어른이 된다는 것이 더 단단해지는 일이 아니라, 오히려 나를 잃지 않기 위해 계속 흔들리고 질문하는 과정처럼 느껴졌다. 특히 관계 속에서 스스로를 바라보게 되는 장면들이 오랫동안 마음에 남았다.',
];

export const reviewDraftVariants = {
  shorter: [
    '『어른이 된다는 것』은 어른다움을 강요받는 순간들을 담담하게 보여주는 책이다.',
    '읽는 내내 정답을 아는 어른이 아니라, 흔들리며 질문하는 과정이 더 가깝게 느껴졌다.',
  ],
  emotional: [
    '『어른이 된다는 것』은 마음 깊은 곳의 불안을 조용히 어루만지는 책이다.',
    '관계 속에서 스스로를 잃어가는 순간들이 오래 남았고, 그 흔들림이 오히려 솔직한 어른다움처럼 느껴졌다.',
  ],
  honest: [
    '『어른이 된다는 것』은 어른이 되어야 한다는 압박을 있는 그대로 보여준다.',
    '나도 비슷하게 흔들렸고, 이 책은 그 흔들림을 부끄러운 게 아니라 살아가는 방식으로 말해준다.',
  ],
};

export const defaultUserReview =
  '어른이 된다는 건 성장만을 의미하지 않는다.\n이 책은 관계 속에서 스스로를 바라보게 만드는 순간들을 담담하게 보여준다.\n\n읽는 동안 나는 어른다움이란 정답을 아는 상태가 아니라, 흔들리면서도 계속 살아가는 법을 배워가는 과정일 수 있다고 느꼈다.';

export const demoReceiptQrPayload = JSON.stringify({
  v: 1,
  memberId: 'jiheon',
  memberName: '지현',
  books: [{ id: 'reading-1', isbn: '9788936434268', title: '어른이 된다는 것', author: '김혜진', pages: 224, icon: '🌱' }],
});

export const widgetMessage = {
  bookId: 'reading-1',
  variant: 'phoneHome',
  category: '산책',
  statusIcon: 'clock',
  statusLabel: '오늘 0분',
  headline: '산책과 같이\n시작해봐요',
  subtext: '어서 펼쳐봐요 📖',
  cta: '지금 읽으러 가기',
  mascot: 'default',
};

export const nextDayWidgetMessage = {
  bookId: 'reading-1',
  variant: 'nextDay',
  category: '산책',
  statusIcon: 'alertCircle',
  statusLabel: '2일째 미읽음',
  headline: '책이\n기다리고 있어요',
  subtext: '2구간 읽을 차례예요. 📖',
  cta: '지금 읽으러 가기',
  mascot: 'sad',
};

export function computeThinkDelay(text, overrideMs) {
  if (overrideMs) return overrideMs + Math.floor(Math.random() * DEMO_TIMING.thinkJitterMs);
  const base = DEMO_TIMING.thinkBaseMs + (text?.length || 0) * DEMO_TIMING.thinkPerCharMs;
  const jitter = Math.floor(Math.random() * DEMO_TIMING.thinkJitterMs * 2) - DEMO_TIMING.thinkJitterMs;
  return Math.min(DEMO_TIMING.thinkMaxMs, Math.max(900, base + jitter));
}

export function findChatTurn(userText, turnIndex) {
  if (chatTurns[turnIndex]) return chatTurns[turnIndex];
  const normalized = userText.trim();
  return chatTurns.find((turn) => turn.user === normalized) || {
    user: normalized,
    ai: '좋아요. 그 생각을 오늘의 기록에 남겨두고, 다음 질문을 이어갈게요.',
    thinkMs: computeThinkDelay('fallback'),
  };
}
