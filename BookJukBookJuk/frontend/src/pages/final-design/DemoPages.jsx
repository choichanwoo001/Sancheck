import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Html5Qrcode } from 'html5-qrcode';

import {
  BackButton,
  Header,
  Icon,
  MobileShell,
  PrimaryButton,
} from '../../components/final-design/FinalDesignComponents.jsx';
import { ReadingWidget } from '../../components/final-design/ReadingWidget.jsx';
import { DEMO_TIMING, demoReceiptQrPayload, nextDayWidgetMessage, widgetMessage } from '../../data/demoScript.js';
import {
  addShelfSyncBook,
  getDemoUser,
  setDemoUser,
  updateDemoSession,
} from '../../utils/demoStorage.js';

const SYNC_STEPS = ['영수증 확인 중…', '구매 정보 확인 중…', '책장에 추가 중…'];

function parseReceiptPayload(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function processReceipt(payload, navigate) {
  const user = getDemoUser();
  if (!user || user.memberId !== payload.memberId) {
    window.sessionStorage.setItem('bookjuk.pendingReceipt', JSON.stringify(payload));
    navigate('/signup');
    return;
  }
  runSyncFlow(payload, navigate);
}

function runSyncFlow(payload, navigate) {
  let step = 0;
  const overlay = document.createElement('div');
  overlay.className = 'fd-sync-overlay';
  overlay.innerHTML = `<div class="fd-sync-modal"><span class="fd-button-spinner"></span><p>${SYNC_STEPS[0]}</p></div>`;
  document.body.appendChild(overlay);

  const advance = () => {
    step += 1;
    if (step < SYNC_STEPS.length) {
      overlay.querySelector('p').textContent = SYNC_STEPS[step];
      setTimeout(advance, step === 1 ? DEMO_TIMING.syncReceiptMs : DEMO_TIMING.syncShelfMs);
      return;
    }
    payload.books?.forEach((book) => addShelfSyncBook(book.id));
    updateDemoSession({ lastPage: 0, chatTurns: 0, highlightCount: 0 });
    document.body.removeChild(overlay);
    const firstBook = payload.books?.[0];
    navigate(firstBook ? `/books/${firstBook.id}/home` : '/library');
  };

  setTimeout(advance, DEMO_TIMING.syncReceiptMs);
}

export function ScanPage() {
  const navigate = useNavigate();
  const scannerRef = useRef(null);
  const [error, setError] = useState('');
  const [scanning, setScanning] = useState(false);

  useEffect(() => {
    let scanner;
    const startScanner = async () => {
      try {
        scanner = new Html5Qrcode('qr-reader');
        scannerRef.current = scanner;
        await scanner.start(
          { facingMode: 'environment' },
          { fps: 10, qrbox: { width: 220, height: 220 } },
          (decoded) => {
            const payload = parseReceiptPayload(decoded);
            if (!payload?.memberId) {
              setError('인식할 수 없는 QR 코드예요.');
              return;
            }
            scanner.stop().catch(() => {});
            setScanning(false);
            processReceipt(payload, navigate);
          },
          () => {},
        );
        setScanning(true);
      } catch {
        setError('카메라를 사용할 수 없어요. 아래 데모 버튼을 이용해주세요.');
      }
    };
    startScanner();
    return () => {
      if (scannerRef.current?.isScanning) {
        scannerRef.current.stop().catch(() => {});
      }
    };
  }, [navigate]);

  const demoScan = () => {
    const payload = parseReceiptPayload(demoReceiptQrPayload);
    processReceipt(payload, navigate);
  };

  return (
    <MobileShell showTabBar={false} className="fd-scan-page">
      <Header title="QR 영수증 스캔" backTo="/library" />
      <main className="fd-scan-scroll">
        <p className="fd-scan-guide">결제 후 받은 QR 영수증을 스캔하면 구매한 책이 책장에 등록돼요.</p>
        <div className="fd-qr-reader-wrap">
          <div id="qr-reader" />
          {!scanning ? <div className="fd-qr-placeholder"><Icon name="search" size={32} /></div> : null}
        </div>
        {error ? <p className="fd-scan-error">{error}</p> : null}
        <PrimaryButton icon="sparkles" onClick={demoScan}>데모 영수증 스캔</PrimaryButton>
        <p className="fd-scan-hint">카메라가 안 되면 위 버튼으로 데모를 진행할 수 있어요.</p>
      </main>
    </MobileShell>
  );
}

export function SignupPage() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = (event) => {
    event.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setTimeout(() => {
      const pending = window.sessionStorage.getItem('bookjuk.pendingReceipt');
      const payload = pending ? parseReceiptPayload(pending) : parseReceiptPayload(demoReceiptQrPayload);
      setDemoUser({
        memberId: payload?.memberId || 'jiheon',
        name: name.trim(),
        email: email.trim(),
      });
      window.sessionStorage.removeItem('bookjuk.pendingReceipt');
      if (payload) {
        runSyncFlow(payload, navigate);
      } else {
        navigate('/library');
      }
      setLoading(false);
    }, 900);
  };

  const loginExisting = () => {
    setDemoUser({ memberId: 'jiheon', name: '지현', email: 'jiheon@demo.com' });
    const pending = window.sessionStorage.getItem('bookjuk.pendingReceipt');
    const payload = pending ? parseReceiptPayload(pending) : parseReceiptPayload(demoReceiptQrPayload);
    window.sessionStorage.removeItem('bookjuk.pendingReceipt');
    if (payload) runSyncFlow(payload, navigate);
    else navigate('/library');
  };

  return (
    <MobileShell showTabBar={false} className="fd-signup-page">
      <header className="fd-highlight-header">
        <BackButton onClick={() => navigate('/scan')} />
        <h1>회원가입</h1>
        <span aria-hidden="true" />
      </header>
      <main className="fd-signup-scroll">
        <section className="fd-prompt-card">
          <h2><Icon name="sparkles" /> 영수증을 연동하려면 가입이 필요해요</h2>
          <p>서점에서 구매한 책을 책장에 자동 등록하려면 계정을 만들어주세요.</p>
        </section>
        <form className="fd-signup-form" onSubmit={submit}>
          <label>
            이름
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="지현" required />
          </label>
          <label>
            이메일
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@email.com" />
          </label>
          <PrimaryButton icon="check" loading={loading}>가입하고 연동하기</PrimaryButton>
        </form>
        <button className="fd-signup-login-link" type="button" onClick={loginExisting}>
          이미 계정이 있어요
        </button>
      </main>
    </MobileShell>
  );
}

function PhoneWidgetDemoPage({ message, onWidgetClick }) {
  return (
    <div className="fd-phone-home">
      <div className="fd-phone-status-bar">
        <span>9:41</span>
        <span>5G ▮▮▮</span>
      </div>
      <div className="fd-phone-wallpaper" />
      <div className="fd-phone-apps">
        {['전화', '메시지', '카메라', '사진'].map((app) => (
          <div className="fd-phone-app" key={app}><span /><small>{app}</small></div>
        ))}
      </div>
      <ReadingWidget onClick={onWidgetClick} message={message} />
      <nav className="fd-phone-dock">
        {['전화', 'Safari', '메시지', '음악'].map((app) => (
          <div className="fd-phone-dock-app" key={app}><span /></div>
        ))}
      </nav>
      <Link className="fd-phone-back-to-app" to="/">앱으로 돌아가기</Link>
    </div>
  );
}

export function PhoneHomePage() {
  const navigate = useNavigate();

  const openLibraryFromWidget = () => {
    addShelfSyncBook(widgetMessage.bookId);
    navigate('/library');
  };

  return <PhoneWidgetDemoPage message={widgetMessage} onWidgetClick={openLibraryFromWidget} />;
}

export function NextDayPage() {
  const navigate = useNavigate();

  const openReadingFromWidget = () => {
    navigate(`/books/${nextDayWidgetMessage.bookId}/home`);
  };

  return <PhoneWidgetDemoPage message={nextDayWidgetMessage} onWidgetClick={openReadingFromWidget} />;
}
