import './styles/main.css';
import { renderApp } from './app';

document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('app');
  if (root) {
    root.appendChild(renderApp());
  }
});
