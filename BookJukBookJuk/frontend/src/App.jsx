import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import './App.css';

import { NextDayPage, PhoneHomePage, ScanPage, SignupPage } from './pages/final-design/DemoPages.jsx';
import {
  AiReviewPage,
  ChatPage,
  CommunityPage,
  CommunitySearchPage,
  CompletionPage,
  HighlightPage,
  HomeCompletePage,
  HomePage,
  LibraryPage,
  SearchPage,
  SearchResultsPage,
  SummaryPage,
} from './pages/final-design/FinalDesignPages.jsx';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/books/:bookId/home" element={<HomePage />} />
        <Route path="/books/:bookId/home-complete" element={<HomeCompletePage />} />
        <Route path="/books/:bookId/chat" element={<ChatPage />} />
        <Route path="/books/:bookId/highlight" element={<HighlightPage />} />
        <Route path="/books/:bookId/summary" element={<SummaryPage />} />
        <Route path="/books/:bookId/review" element={<AiReviewPage />} />
        <Route path="/books/:bookId/completion" element={<CompletionPage />} />
        <Route path="/home-complete" element={<Navigate to="/books/reading-1/home-complete" replace />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/scan" element={<ScanPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/demo/phone-home" element={<PhoneHomePage />} />
        <Route path="/demo/next-day" element={<NextDayPage />} />
        <Route path="/chat/reading-1" element={<Navigate to="/books/reading-1/chat" replace />} />
        <Route path="/highlight/new" element={<Navigate to="/books/reading-1/highlight" replace />} />
        <Route path="/summary/today" element={<Navigate to="/books/reading-1/summary" replace />} />
        <Route path="/books/search" element={<SearchPage />} />
        <Route path="/books/search/results" element={<SearchResultsPage />} />
        <Route path="/community" element={<CommunityPage />} />
        <Route path="/community/search" element={<CommunitySearchPage />} />
        <Route path="/review/ai" element={<Navigate to="/books/reading-1/review" replace />} />
        <Route path="/completion" element={<Navigate to="/books/reading-1/completion" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
