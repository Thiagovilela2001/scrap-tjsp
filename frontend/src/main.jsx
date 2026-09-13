import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { TooltipProvider } from '@/components/ui/tooltip';
import './index.css';
import './mobile.css';
import './desktop-motion.css';
import './results.css';
import './results-inspector.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <TooltipProvider delay={400}><App /></TooltipProvider>
  </React.StrictMode>
);
