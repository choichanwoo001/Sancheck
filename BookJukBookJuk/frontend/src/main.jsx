import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './styles/tokens.css';
import './index.css';

['bookjuk.sectionProgress', 'bookjuk.demoSession', 'bookjuk.shelfSync'].forEach((key) => {
  window.localStorage.removeItem(key);
});

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
