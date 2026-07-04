#!/usr/bin/env node
import { writeFileSync, mkdirSync, existsSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC_TTS_DIR = join(__dirname, '..', 'public', 'audio', 'tts');

// Load environment variables from .env manually
function loadEnv() {
  const envPath = join(__dirname, '..', '.env');
  if (!existsSync(envPath)) return {};
  const content = readFileSync(envPath, 'utf8');
  const env = {};
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const idx = trimmed.indexOf('=');
    if (idx < 0) continue;
    const key = trimmed.slice(0, idx).trim();
    const val = trimmed.slice(idx + 1).trim();
    env[key] = val;
  }
  return env;
}

const env = loadEnv();
const apiKey = env.VITE_OPENAI_API_KEY || process.env.VITE_OPENAI_API_KEY;
const voice = env.VITE_TTS_VOICE || process.env.VITE_TTS_VOICE || 'onyx';

if (!apiKey) {
  console.error('Error: VITE_OPENAI_API_KEY not found in .env or environment variables.');
  process.exit(1);
}

const PHRASES = [
  // Current guided scenario flow. Existing files are skipped, so this script is safe to rerun
  // whenever scenario copy changes.
  '준비되면 오케이 제스처를 취해주세요.',
  '정지했습니다. 직접 둘러보는 동안 책 표지를 인식할게요.',
  '다시 산책을 재개하고 싶으면 오케이 제스처 주세요',
  '왜 단 한 사람 책을 구매 리스트에 안담았나요?',
  '말씀하신 걸 보면 「단 한 사람」의 한 사람에게 깊게 집중하는 정서와 관계의 온도는 잘 맞았지만, 지금은 조금 더 현실에서 바로 붙잡을 수 있는 조언이 필요해 보여요. 그래서 그 감정선은 유지하면서 관계와 책임을 더 실용적으로 풀어낸 「어른이 된다는 것」을 추천할게요. 관심 있으신가요?',
  '좋아요. 원래 가려던 「오직 두 사람」와 추천한 「어른이 된다는 것」 좌표를 로봇에게 전달했어요.',
  '직접 보시니까 어떠세요?',
  '사용자님이 김영하 작가의 따뜻한 문체를 좋아할 줄 알았어요. 사실건가요?',
  '구매 리스트에 추가했어요. 다음 목적지로 이동할게요.',
  '원하는 현실적인 부분이 있는 책인가요?',
  '사용자님이 김창진 작가의 현실적인 측면을 좋아할 줄 알았어요. 사실건가요?',
  '구매 리스트에 추가했어요. 구매를 완료하셨으면 계산하기 버튼을 클릭해주세요.',
  '구매를 완료하셨으면 계산하기 버튼을 클릭해주세요.',
  '계산대에 도착했어요. 오른쪽 구매 리스트의 계산하기 버튼으로 결제를 진행하시면 됩니다.',

  // Legacy and fallback guidance still used by older branches or less common paths.
  '경로 보이게 해뒀어요. 시작하려면 "시작"이나 "오케이"라고 말해 주세요.',
  '책 1권 찾아뒀어요! 경로도 보이게 해뒀는데, 한번 보시고 시작하실 땐 "시작"이나 "오케이"라고 말해 주세요.',
  '책 2권 찾아뒀어요! 경로도 보이게 해뒀는데, 한번 보시고 시작하실 땐 "시작"이나 "오케이"라고 말해 주세요.',
  '책 3권 찾아뒀어요! 경로도 보이게 해뒀는데, 한번 보시고 시작하실 땐 "시작"이나 "오케이"라고 말해 주세요.',
  '책을 읽어보시고 다음 경로로 가고 싶으시면 "오케이"라고 말씀해 주세요.',
  '천천히 살펴보시고 출발하고 싶다면 "오케이"라고 말씀해 주세요.',
  '왜 이 책은 장바구니에 안 담으셨나요?',
  '좀 더 실용적인 책을 원하시는군요. 인간관계와 삶의 책임에 대한 현실적인 조언을 담은 에세이 「어른이 된다는 것」을 추천드려요. 괜찮으시면 "오케이"라고 말씀해 주세요.',
  '"단 한 사람" 책을 장바구니에 담으셨군요! 원래 목적지인 "오직 두 사람" 서가로 다시 출발하겠습니다.',
  '안내를 시작할게요.',
  '좋습니다. 다음 목적지로 안내를 계속할게요.',
  '좋습니다. 방문 목록에는 오직 두 사람과 어른이 된다는 것을 넣고, 먼저 오직 두 사람 좌표를 로봇에게 전달했어요.',
  '「오직 두 사람」 서가에 도착했어요. 두 사람의 만남과 이별을 따라가는 소설입니다.',
  '평점 4.4, 감정선이 섬세하다는 리뷰가 많아요.',
  '김영하 작가는 일상 속 관계를 담담하게 그리는 소설가예요.',
  '「단 한 사람」 서가에 도착했어요. 한 사람에게 집중하는 이야기로, 잔잔하지만 깊은 여운이 남아요.',
  '평점 4.6, 결말의 온기가 인상적이라는 평이 많아요.',
  '최진영 작가는 관계와 감정의 결을 섬세하게 풀어내는 작가예요.',
  '「어른이 된다는 것」 서가에 도착했어요. 어른이란 무엇인지, 관계와 책임을 돌아보는 에세이입니다.',
  '평점 4.5, 독자들은 공감과 위로를 느꼈다고 남겼어요.',
  '김창진 작가는 심리·관계를 다루는 에세이로 잘 알려져 있어요.',
  '「너무나 많은 여름이」 서가에 도착했어요. 여름과 관계, 상실과 회복을 담은 소설집입니다.',
  '평점 4.5, 여름의 감각과 슬픔이 잘 살아 있다는 리뷰가 많아요.',
  '김연수 작가는 계절과 기억을 통해 관계를 그리는 소설가예요.',
  '「어른이 된다는 것」이(가) 경로상 먼저 위치해 있네요! 「어른이 된다는 것」 서가에 들렀다가 원래 가려던 「오직 두 사람」 안내를 이어갈게요!',
  '「어른이 된다는 것」을(를) 경로에 추가하고, 원래 가려던 「오직 두 사람」 안내를 이어갈게요!',
  '아직 "오직 두 사람" 책이 장바구니에 담기지 않았습니다. 책 표지 인식이나 제스처로 책을 담으신 후 다시 "오케이"라고 말씀해주세요.',
  '우연한 책장의 책을 카메라로 충분히 살펴보신 뒤 다시 "오케이"라고 말씀해 주세요.',
  '데모 시나리오에서는 "오케이"라고 말씀하시거나 OK 사인으로 진행해 주세요.',
  '데모 시나리오에서는 안내에 따라 진행해 주세요.',
  '아라님이 김영하 작가의 따뜻한 문체를 좋아하실 줄 알았어요. 이 책을 장바구니에 담으시겠어요?',
  '현재 목록에서 로봇 목적지 좌표를 찾지 못했습니다. 목적지 좌표가 있는 책을 선택한 뒤 다시 안내를 시작해 주세요.',
  '계획 없이 바로 출발합니다. 화면에 보이는 추천이나 제가 말해드리는 추천에 집중해 주세요. 필요하면 "추천해줘"라고 말해 주세요. 마음에 들면 쇼핑리스트에 담을 수 있어요.',
  '현재 이 요청은 아직 연결되지 않았어요.',
  '취소할 확인 대기가 없어요.',
  '요청을 취소했어요.',
  '확인할 작업이 없어요.',
  '"어른이 된다는 것"에 관심을 보이셨는데 장바구니에 담지 않으셨네요. 어떤 점이 마음에 걸리셨는지 말씀해 주시면 그 책 기준으로 더 잘 맞는 책을 추천해드릴게요.'
];

function normalizeTextForTts(text) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]/g, '');
}

async function main() {
  mkdirSync(PUBLIC_TTS_DIR, { recursive: true });
  console.log(`TTS pre-generation starting... Saving to: ${PUBLIC_TTS_DIR}`);
  console.log(`Using voice: ${voice}`);

  let successCount = 0;

  for (const phrase of PHRASES) {
    const key = normalizeTextForTts(phrase);
    const destFile = join(PUBLIC_TTS_DIR, `${key}.mp3`);

    if (existsSync(destFile)) {
      console.log(`[Skip] Already exists: ${key}.mp3 ("${phrase.slice(0, 15)}...")`);
      successCount++;
      continue;
    }

    console.log(`[Download] Fetching TTS for: "${phrase}" -> key: ${key}`);
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort();
      }, 60000); // long Korean scenario lines can take a little longer

      const response = await fetch('https://api.openai.com/v1/audio/speech', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: 'tts-1',
          input: phrase,
          voice: voice,
          response_format: 'mp3',
        }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`OpenAI HTTP ${response.status}: ${await response.text()}`);
      }

      const buffer = Buffer.from(await response.arrayBuffer());
      writeFileSync(destFile, buffer);
      console.log(`[Success] Saved ${key}.mp3`);
      successCount++;

      // Rate limit safety sleep
      await new Promise((resolve) => setTimeout(resolve, 300));
    } catch (e) {
      console.error(`[Failed] for "${phrase}":`, e instanceof Error ? e.name === 'AbortError' ? 'Timeout' : e.message : e);
    }
  }

  console.log(`\nCompleted! Generated ${successCount}/${PHRASES.length} TTS assets.`);
  if (successCount < PHRASES.length) {
    process.exit(1);
  }
}

main();
